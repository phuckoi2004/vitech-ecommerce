"""Migration reconciliation checks using the script graph and PostgreSQL SQL only.

No engine, database URL or Alembic env.py is loaded. Graph traversal includes
databases that already applied the old local branch with skipped ancestors.
"""

import ast
from collections import Counter
from io import StringIO
from pathlib import Path
import re

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory


BACKEND = Path(__file__).resolve().parents[1]
VERSIONS = BACKEND / "alembic" / "versions"
LOCAL_HEAD = "61f7b0a38d92"
REMOTE_HEAD = "b81569bc34b0"
MERGE_HEAD = "c6a4e2b8d901"
# Head after the merge: drops the unused Stage 4 OtpChallenges table (decision 11/10/2026).
OTP_HEAD = "3d9f987f3c6f"
WORKFLOW_HEAD = "7e4c9b2d1a60"
CATEGORY_IMAGE_HEAD = "6f8a2c4d9b10"
HEAD = "71a4d9c8e620"
COUPON_REVISION = "213feab4a632"
STATUS_REVISION = "dd773e03e503"
TRANSACTION_TYPE_REVISION = "9b10f42fc70d"
DOMAIN_REVISIONS = {
    "763f153af842", "d3326a8fbc5c", "4c2d9e7a1f53", "8b7e3d1c5a29",
    "5d1f9a3c7e64", "e2b8c4f6a913", "a7c3e9d1f285", "c8d2f4a6b1e3",
    "d4f7b2e9a6c1", "f3b8d1a5c7e2", "e6a2d9c4b8f1", "a9f4c2e7b513",
    REMOTE_HEAD,
}


def scripts():
    config = Config()
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    return ScriptDirectory.from_config(config)


def upgrade_path(start):
    # implicit_base matches Alembic's upgrade planner when the target joins
    # multiple branches. Reversing gives the order that upgrades will execute.
    return list(reversed(list(scripts().iterate_revisions(MERGE_HEAD, start, implicit_base=True))))


def render(operation):
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output},
    )
    with context.begin_transaction():
        with Operations.context(context):
            operation()
    return output.getvalue()


def revision_identifiers():
    identifiers = []
    for path in VERSIONS.glob("*.py"):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "revision":
                identifiers.append((path.name, ast.literal_eval(node.value)))
                break
            if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "revision"
                                                   for target in node.targets):
                identifiers.append((path.name, ast.literal_eval(node.value)))
                break
        else:
            raise AssertionError(f"Migration has no literal revision identifier: {path.name}")
    return identifiers


def test_unique_revision_ids_and_one_complete_canonical_graph():
    identifiers = revision_identifiers()
    counts = Counter(revision for _, revision in identifiers)
    duplicates = {revision: [name for name, identifier in identifiers if identifier == revision]
                  for revision, count in counts.items() if count > 1}
    assert duplicates == {}, f"Duplicate Alembic revision identifiers: {duplicates}"
    assert len(identifiers) == 25
    graph = scripts()
    assert graph.get_heads() == [HEAD]
    assert graph.get_revision(HEAD).down_revision == CATEGORY_IMAGE_HEAD
    assert graph.get_revision(CATEGORY_IMAGE_HEAD).down_revision == WORKFLOW_HEAD
    assert graph.get_revision(WORKFLOW_HEAD).down_revision == OTP_HEAD
    assert graph.get_revision(OTP_HEAD).down_revision == MERGE_HEAD
    assert graph.get_bases() == ["2cb2e7418b06"]
    assert {revision.revision for revision in graph.walk_revisions()} == set(counts)
    assert graph.get_revision(MERGE_HEAD).down_revision == (LOCAL_HEAD, REMOTE_HEAD)
    assert graph.get_revision(LOCAL_HEAD).down_revision == COUPON_REVISION
    assert graph.get_revision(COUPON_REVISION).down_revision == TRANSACTION_TYPE_REVISION
    assert graph.get_revision(TRANSACTION_TYPE_REVISION).down_revision == STATUS_REVISION
    assert graph.get_revision(STATUS_REVISION).down_revision == "b5d3a7c912e4"
    assert Path(graph.get_revision("b5d3a7c912e4").path).name == "b5d3a7c912e4_remove_legacy_admin_role.py"
    assert Path(graph.get_revision(COUPON_REVISION).path).name == "213feab4a632_coupon_code_case_insensitive_unique.py"


def test_old_local_head_receives_all_domain_migrations_then_repair_merge():
    path = upgrade_path(LOCAL_HEAD)
    assert {revision.revision for revision in path} == DOMAIN_REVISIONS | {MERGE_HEAD}
    assert path[0].revision == "763f153af842"
    assert path[-1].revision == MERGE_HEAD
    # These canonical ancestors can be absent on a database whose old local
    # coupon revision originally depended directly on b5d3a7c912e4. Alembic
    # will skip them, so the new merge upgrade must independently repair both.
    assert not {STATUS_REVISION, TRANSACTION_TYPE_REVISION} & {revision.revision for revision in path}
    repair_sql = render(path[-1].module.upgrade)
    assert 'ADD CONSTRAINT "CK_Users_AccountStatus_Valid"' in repair_sql
    assert 'ADD CONSTRAINT "CK_PaymentTransactions_TransactionType_Valid"' in repair_sql


def test_remote_head_receives_local_validation_then_merge_only():
    assert [revision.revision for revision in upgrade_path(REMOTE_HEAD)] == [LOCAL_HEAD, MERGE_HEAD]


def test_existing_coupon_revision_receives_both_branches_without_replaying_coupon_ddl():
    path = upgrade_path(COUPON_REVISION)
    assert {revision.revision for revision in path} == DOMAIN_REVISIONS | {LOCAL_HEAD, MERGE_HEAD}
    assert path[-1].revision == MERGE_HEAD
    assert COUPON_REVISION not in {revision.revision for revision in path}
    assert not {STATUS_REVISION, TRANSACTION_TYPE_REVISION} & {revision.revision for revision in path}


def test_fresh_database_visits_every_revision_once_in_parent_order():
    path = upgrade_path("base")
    assert len(path) == 21
    seen = set()
    for revision in path:
        parents = revision.down_revision
        if parents:
            parents = (parents,) if isinstance(parents, str) else parents
            assert set(parents) <= seen
        assert revision.revision not in seen
        seen.add(revision.revision)
    assert path[0].revision == "2cb2e7418b06"
    assert path[-1].revision == MERGE_HEAD


def test_head_drops_otp_challenges_and_downgrade_recreates_it_without_touching_users():
    module = scripts().get_revision(OTP_HEAD).module
    upgrade_sql = render(module.upgrade)
    assert 'DROP INDEX "IX_OtpChallenges_UserId_Purpose_CreatedAt"' in upgrade_sql
    assert 'DROP TABLE "OtpChallenges"' in upgrade_sql
    downgrade_sql = render(module.downgrade)
    assert 'CREATE TABLE "OtpChallenges"' in downgrade_sql
    assert 'ENABLE ROW LEVEL SECURITY' in downgrade_sql
    assert 'UPDATE "Users"' not in downgrade_sql


def test_category_image_migration_adds_only_an_optional_column():
    module = scripts().get_revision(CATEGORY_IMAGE_HEAD).module
    sql = render(module.upgrade)
    assert 'ALTER TABLE "Categories" ADD COLUMN "ImageUrl" VARCHAR(500)' in sql
    assert 'NOT NULL' not in sql
    assert not re.search(r'\b(?:UPDATE|DELETE|INSERT|DROP)\b', sql)
    assert 'DROP COLUMN "ImageUrl"' in render(module.downgrade)


def test_shared_guard_upgrades_adopt_matching_checks_reject_bad_definitions_and_validate_data():
    graph = scripts()
    cases = (
        (STATUS_REVISION, "Users", "AccountStatus", ("Active", "Locked")),
        (TRANSACTION_TYPE_REVISION, "PaymentTransactions", "TransactionType", ("Payment", "Refund")),
    )
    for revision, table, column, allowed in cases:
        sql = render(graph.get_revision(revision).module.upgrade)
        constraint = f"CK_{table}_{column}_Valid"
        assert "SET LOCAL lock_timeout = '5s'" in sql
        assert f'LOCK TABLE public."{table}" IN ACCESS EXCLUSIVE MODE' in sql
        assert sql.index("LOCK TABLE") < sql.index("FROM pg_catalog.pg_constraint")
        assert f"c.conrelid = 'public.\"{table}\"'::regclass" in sql
        assert f"c.conname = '{constraint}'" in sql
        assert "constraint_kind IS DISTINCT FROM 'c'" in sql
        assert "existing_definition IS NULL" in sql
        assert "existing_definition NOT IN" in sql
        assert "unexpected definition" in sql
        assert "regexp_replace(pg_get_constraintdef(c.oid), ' NOT VALID$', '')" in sql
        assert f'WHERE "{column}" IS NULL OR "{column}" NOT IN' in sql
        assert "IF NOT constraint_exists THEN" in sql
        assert "ELSIF NOT constraint_validated THEN" in sql
        assert f'VALIDATE CONSTRAINT "{constraint}"' in sql
        assert sql.index(f'invalid {column} values') < sql.index("ADD CONSTRAINT")
        for value in allowed:
            assert f"''{value}''::character varying" in sql
        assert not re.search(r'\b(?:UPDATE|DELETE|INSERT|DROP)\b', sql)
        assert ':existing_definition' not in sql


def test_repair_merge_guards_both_checks_and_downgrade_retains_shared_guards():
    module = scripts().get_revision(MERGE_HEAD).module
    sql = render(module.upgrade)
    for table, column in (("Users", "AccountStatus"), ("PaymentTransactions", "TransactionType")):
        constraint = f"CK_{table}_{column}_Valid"
        assert f'LOCK TABLE public."{table}" IN ACCESS EXCLUSIVE MODE' in sql
        assert f'ADD CONSTRAINT "{constraint}"' in sql
        assert f'VALIDATE CONSTRAINT "{constraint}"' in sql
    assert sql.count("constraint_kind IS DISTINCT FROM 'c'") == 2
    assert sql.count("existing_definition NOT IN") == 2
    assert not re.search(r'\b(?:UPDATE|DELETE|INSERT|DROP)\b', sql)
    assert not re.search(r'\b(?:ALTER|UPDATE|DELETE|INSERT|DROP|LOCK)\b', render(module.downgrade))


def test_shared_owner_downgrades_verify_definition_before_removing_only_their_check():
    graph = scripts()
    for revision, constraint in (
        (STATUS_REVISION, "CK_Users_AccountStatus_Valid"),
        (TRANSACTION_TYPE_REVISION, "CK_PaymentTransactions_TransactionType_Valid"),
    ):
        sql = render(graph.get_revision(revision).module.downgrade)
        assert "SET LOCAL lock_timeout = '5s'" in sql
        assert "IF constraint_exists THEN" in sql
        assert "unexpected definition" in sql
        assert f'DROP CONSTRAINT "{constraint}"' in sql
        assert sql.index("existing_definition NOT IN") < sql.index("DROP CONSTRAINT")
        assert sql.count("DROP CONSTRAINT") == 1
        assert not re.search(r'\b(?:UPDATE|DELETE|INSERT)\b', sql)


def test_retained_role_migration_preserves_accounts_while_converting_legacy_admin_role():
    sql = render(scripts().get_revision("b5d3a7c912e4").module.upgrade)
    assert 'UPDATE public."Users" SET "Role" = \'Admin\' WHERE "Role" = \'SuperAdmin\'' in sql
    assert sql.index('LOCK TABLE public."Users"') < sql.index('UPDATE public."Users"')
    assert sql.index('UPDATE public."Users"') < sql.index('DROP CONSTRAINT')
    assert 'CHECK ("Role" IN (\'Customer\', \'Staff\', \'Admin\'))' in sql
    assert not re.search(r'\b(?:DELETE|INSERT)\b', sql)
