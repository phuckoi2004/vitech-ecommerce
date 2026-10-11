"""Require Payment or Refund transaction type, adopting an existing matching check.

Revision ID: 9b10f42fc70d
Revises: dd773e03e503

The canonical history owns this check. Reconciliation may encounter a matching
constraint created before its revision was recorded. Adopt only an exact known
PostgreSQL definition, validate it if needed, and never rewrite application data.
Unexpected definitions and invalid data require explicit review.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "9b10f42fc70d"
down_revision: Union[str, Sequence[str], None] = "dd773e03e503"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Exact PostgreSQL-decompiled forms of IN/ANY for a varchar column. Do not strip
# casts or whitespace inside literals: that could make an incorrect check look valid.
_KNOWN_CHECK_DEFINITIONS = (
    'CHECK ((("TransactionType")::text = ANY ((ARRAY[\'Payment\'::character varying, \'Refund\'::character varying])::text[])))',
    'CHECK ((("TransactionType")::text = ANY ((ARRAY[\'Refund\'::character varying, \'Payment\'::character varying])::text[])))',
    'CHECK ((("TransactionType")::text = ANY (ARRAY[\'Payment\'::text, \'Refund\'::text])))',
    'CHECK ((("TransactionType")::text = ANY (ARRAY[\'Refund\'::text, \'Payment\'::text])))',
)


def _guarded_sql(action: str) -> str:
    accepted = ",\n                ".join(
        "'" + definition.replace("'", "''") + "'" for definition in _KNOWN_CHECK_DEFINITIONS
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


def _lock_table() -> None:
    # The transaction lock prevents concurrent changes between validation and DDL.
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute('LOCK TABLE public."PaymentTransactions" IN ACCESS EXCLUSIVE MODE')


def upgrade() -> None:
    _lock_table()
    op.execute(_guarded_sql("""
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


def downgrade() -> None:
    _lock_table()
    op.execute(_guarded_sql("""
    IF constraint_exists THEN
        ALTER TABLE public."PaymentTransactions" DROP CONSTRAINT "CK_PaymentTransactions_TransactionType_Valid";
    END IF;
"""))
