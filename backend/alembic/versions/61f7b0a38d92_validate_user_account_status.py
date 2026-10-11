"""Require Active or Locked account status, including on freshly migrated databases.

Revision ID: 61f7b0a38d92
Revises: 213feab4a632

An existing, matching CK_Users_AccountStatus_Valid is adopted without recreating it.
Unknown definitions and invalid data require explicit review; no user data is rewritten.
Downgrade removes this named check even if it existed before this revision. It refuses
to remove an unexpected definition and leaves all user data unchanged.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "61f7b0a38d92"
down_revision: Union[str, Sequence[str], None] = "213feab4a632"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Exact PostgreSQL-decompiled forms of IN/ANY for a varchar column. Do not strip
# casts or whitespace inside literals: that could make an incorrect check look valid.
_KNOWN_CHECK_DEFINITIONS = (
    'CHECK ((("AccountStatus")::text = ANY ((ARRAY[\'Active\'::character varying, \'Locked\'::character varying])::text[])))',
    'CHECK ((("AccountStatus")::text = ANY ((ARRAY[\'Locked\'::character varying, \'Active\'::character varying])::text[])))',
    'CHECK ((("AccountStatus")::text = ANY (ARRAY[\'Active\'::text, \'Locked\'::text])))',
    'CHECK ((("AccountStatus")::text = ANY (ARRAY[\'Locked\'::text, \'Active\'::text])))',
)


def _guarded_sql(action: str) -> str:
    accepted = ",\n                ".join(
        "'" + definition.replace("'", "''") + "'" for definition in _KNOWN_CHECK_DEFINITIONS
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


def upgrade() -> None:
    _lock_users()
    op.execute(_guarded_sql("""
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


def downgrade() -> None:
    _lock_users()
    op.execute(_guarded_sql("""
    IF constraint_exists THEN
        ALTER TABLE public."Users" DROP CONSTRAINT "CK_Users_AccountStatus_Valid";
    END IF;
"""))
