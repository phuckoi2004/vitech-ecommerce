"""Merge Stage 4 and Auth histories and reconcile checks skipped by old stamps.

Revision ID: c6a4e2b8d901
Revises: 61f7b0a38d92, b81569bc34b0

The original local 213feab4a632 descended directly from b5d3a7c912e4. In the
canonical incoming history it descends from dd773e03e503 and 9b10f42fc70d.
A database already stamped with the local 213feab4a632 or 61f7b0a38d92 can
therefore skip those ancestors without having their AccountStatus/TransactionType
DDL. Reconcile both named checks after joining the two heads, under bounded
locks, without rewriting application data or silently replacing unknown checks.

The accepted definitions below are frozen copies, keeping historical migrations
independent of application code and of later edits to other revision modules.
Downgrade retains the checks: dd773e03e503 and 9b10f42fc70d own their removal.
SePay remains the last business DDL migration; this compatibility merge is the
new graph head.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "c6a4e2b8d901"
down_revision: Union[str, Sequence[str], None] = ("61f7b0a38d92", "b81569bc34b0")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ACCOUNT_STATUS_CHECK_DEFINITIONS = (
    'CHECK ((("AccountStatus")::text = ANY ((ARRAY[\'Active\'::character varying, \'Locked\'::character varying])::text[])))',
    'CHECK ((("AccountStatus")::text = ANY ((ARRAY[\'Locked\'::character varying, \'Active\'::character varying])::text[])))',
    'CHECK ((("AccountStatus")::text = ANY (ARRAY[\'Active\'::text, \'Locked\'::text])))',
    'CHECK ((("AccountStatus")::text = ANY (ARRAY[\'Locked\'::text, \'Active\'::text])))',
)


def _guarded_account_status_sql(action: str) -> str:
    accepted = ",\n                ".join(
        "'" + definition.replace("'", "''") + "'" for definition in _ACCOUNT_STATUS_CHECK_DEFINITIONS
    )
    return f"""
DO $account_status$
DECLARE
    constraint_exists boolean;
    constraint_kind "char";
    constraint_validated boolean;
    existing_definition text;
BEGIN
    SELECT c.contype, c.convalidated,
           regexp_replace(pg_get_constraintdef(c.oid), ' NOT VALID$', '')
      INTO constraint_kind, constraint_validated, existing_definition
      FROM pg_catalog.pg_constraint AS c
     WHERE c.conrelid = 'public."Users"'::regclass
       AND c.conname = 'CK_Users_AccountStatus_Valid';
    constraint_exists := FOUND;

    IF constraint_exists AND (
        constraint_kind IS DISTINCT FROM 'c'
        OR existing_definition IS NULL
        OR existing_definition NOT IN (
                {accepted}
        )
    ) THEN
        RAISE EXCEPTION 'CK_Users_AccountStatus_Valid has an unexpected definition; review it before migrating';
    END IF;

    {action}
END;
$account_status$;
"""


def _lock_users() -> None:
    # The transaction lock prevents concurrent changes between validation and DDL.
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute('LOCK TABLE public."Users" IN ACCESS EXCLUSIVE MODE')


def _upgrade_account_status() -> None:
    op.execute(_guarded_account_status_sql("""
    IF EXISTS (
        SELECT 1 FROM public."Users"
         WHERE "AccountStatus" IS NULL OR "AccountStatus" NOT IN ('Active', 'Locked')
    ) THEN
        RAISE EXCEPTION 'Users contains invalid AccountStatus values; correct data explicitly before migrating';
    END IF;

    IF NOT constraint_exists THEN
        ALTER TABLE public."Users" ADD CONSTRAINT "CK_Users_AccountStatus_Valid"
            CHECK ("AccountStatus" IN ('Active', 'Locked'));
    ELSIF NOT constraint_validated THEN
        ALTER TABLE public."Users" VALIDATE CONSTRAINT "CK_Users_AccountStatus_Valid";
    END IF;
"""))


_TRANSACTION_TYPE_CHECK_DEFINITIONS = (
    'CHECK ((("TransactionType")::text = ANY ((ARRAY[\'Payment\'::character varying, \'Refund\'::character varying])::text[])))',
    'CHECK ((("TransactionType")::text = ANY ((ARRAY[\'Refund\'::character varying, \'Payment\'::character varying])::text[])))',
    'CHECK ((("TransactionType")::text = ANY (ARRAY[\'Payment\'::text, \'Refund\'::text])))',
    'CHECK ((("TransactionType")::text = ANY (ARRAY[\'Refund\'::text, \'Payment\'::text])))',
)


def _guarded_transaction_type_sql(action: str) -> str:
    accepted = ",\n                ".join(
        "'" + definition.replace("'", "''") + "'" for definition in _TRANSACTION_TYPE_CHECK_DEFINITIONS
    )
    return f"""
DO $transaction_type$
DECLARE
    constraint_exists boolean;
    constraint_kind "char";
    constraint_validated boolean;
    existing_definition text;
BEGIN
    SELECT c.contype, c.convalidated,
           regexp_replace(pg_get_constraintdef(c.oid), ' NOT VALID$', '')
      INTO constraint_kind, constraint_validated, existing_definition
      FROM pg_catalog.pg_constraint AS c
     WHERE c.conrelid = 'public."PaymentTransactions"'::regclass
       AND c.conname = 'CK_PaymentTransactions_TransactionType_Valid';
    constraint_exists := FOUND;

    IF constraint_exists AND (
        constraint_kind IS DISTINCT FROM 'c'
        OR existing_definition IS NULL
        OR existing_definition NOT IN (
                {accepted}
        )
    ) THEN
        RAISE EXCEPTION 'CK_PaymentTransactions_TransactionType_Valid has an unexpected definition; review it before migrating';
    END IF;

    {action}
END;
$transaction_type$;
"""


def _lock_payments() -> None:
    # The transaction lock prevents concurrent changes between validation and DDL.
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute('LOCK TABLE public."PaymentTransactions" IN ACCESS EXCLUSIVE MODE')


def _upgrade_transaction_type() -> None:
    op.execute(_guarded_transaction_type_sql("""
    IF EXISTS (
        SELECT 1 FROM public."PaymentTransactions"
         WHERE "TransactionType" IS NULL OR "TransactionType" NOT IN ('Payment', 'Refund')
    ) THEN
        RAISE EXCEPTION 'PaymentTransactions contains invalid TransactionType values; correct data explicitly before migrating';
    END IF;

    IF NOT constraint_exists THEN
        ALTER TABLE public."PaymentTransactions" ADD CONSTRAINT "CK_PaymentTransactions_TransactionType_Valid"
            CHECK ("TransactionType" IN ('Payment', 'Refund'));
    ELSIF NOT constraint_validated THEN
        ALTER TABLE public."PaymentTransactions" VALIDATE CONSTRAINT "CK_PaymentTransactions_TransactionType_Valid";
    END IF;
"""))


def upgrade() -> None:
    # Acquire both bounded locks before inspecting either table or constraint.
    _lock_users()
    _lock_payments()
    _upgrade_account_status()
    _upgrade_transaction_type()


def downgrade() -> None:
    # Both constraints belong to canonical ancestors, not this merge revision.
    pass
