"""Model enforcement and real Alembic offline rendering never connect to a database."""

import importlib.util
import re
from io import StringIO
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

from app.models import User


BACKEND = Path(__file__).resolve().parents[1]
REVISION = "61f7b0a38d92"
spec = importlib.util.spec_from_file_location(
    "account_status_migration",
    BACKEND / "alembic" / "versions" / f"{REVISION}_validate_user_account_status.py",
)
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def render(operation):
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output},
    )
    with context.begin_transaction():
        with Operations.context(context):
            operation()
    return output.getvalue()


def test_status_revision_extends_the_existing_chain_and_model_uses_the_same_name():
    scripts = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
    assert len(scripts.get_heads()) == 1
    assert REVISION in {version.revision for version in scripts.walk_revisions()}
    assert scripts.get_revision(REVISION).down_revision == "213feab4a632"
    checks = {constraint.name: str(constraint.sqltext)
              for constraint in User.__table__.constraints if hasattr(constraint, "sqltext")}
    assert checks["CK_Users_AccountStatus_Valid"] == '"AccountStatus" IN (\'Active\', \'Locked\')'


def test_offline_upgrade_guards_existing_checks_and_bad_data_without_rewriting_users():
    sql = render(migration.upgrade)
    # Offline rendering must preserve PostgreSQL casts and the DO block, not emit binds.
    expected_live_definition = (
        'CHECK ((("AccountStatus")::text = ANY ((ARRAY[\'Active\'::character varying, '
        '\'Locked\'::character varying])::text[])))'
    )
    assert expected_live_definition.replace("'", "''") in sql
    assert 'DO $account_status$' in sql and 'END;\n$account_status$;' in sql and '::regclass' in sql
    assert "constraint_kind IS DISTINCT FROM 'c'" in sql
    assert "existing_definition NOT IN" in sql and "unexpected definition" in sql
    assert "regexp_replace(pg_get_constraintdef(c.oid), ' NOT VALID$', '')" in sql
    assert 'c.conrelid = \'public."Users"\'::regclass' in sql
    assert "c.conname = 'CK_Users_AccountStatus_Valid'" in sql
    assert sql.index('LOCK TABLE public."Users"') < sql.index('FROM pg_catalog.pg_constraint')
    assert sql.index('invalid AccountStatus values') < sql.index('ADD CONSTRAINT')
    assert "IF NOT constraint_exists THEN" in sql
    assert "ELSIF NOT constraint_validated THEN" in sql
    assert 'VALIDATE CONSTRAINT "CK_Users_AccountStatus_Valid"' in sql
    assert not re.search(r'\b(?:UPDATE|DELETE|INSERT|DROP)\b', sql)
    assert ':existing_definition' not in sql


def test_offline_downgrade_removes_only_the_guarded_named_check_without_changing_users():
    sql = render(migration.downgrade)
    assert 'DROP CONSTRAINT "CK_Users_AccountStatus_Valid"' in sql
    assert "IF constraint_exists THEN" in sql and "unexpected definition" in sql
    assert sql.index('existing_definition NOT IN') < sql.index('DROP CONSTRAINT')
    assert not re.search(r'\b(?:UPDATE|DELETE|INSERT)\b', sql)
