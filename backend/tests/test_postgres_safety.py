"""Pure safety tests: no application imports, dotenv, database or network access."""

import ast
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects.postgresql import dialect

from tests.postgres_safety import (
    UnsafePostgresTestDatabase,
    get_database_identity,
    require_separate_test_database,
)

MAIN_PROJECT = "abcdefghijklmnopqrst"
TEST_PROJECT = "zyxwvutsrqponmlkjihg"
MAIN_DIRECT = f"postgresql://postgres:main-secret@db.{MAIN_PROJECT}.supabase.co:5432/postgres"
SOURCE = Path(__file__).with_name("test_postgres_integration.py")


@pytest.mark.parametrize("main,test", [
    ("postgresql://alice:a@db.example.com/app", "postgresql://bob:b@db.example.com:5432/app"),
    ("postgresql://alice:a@DB.EXAMPLE.COM./app", "postgresql+psycopg://bob:b@db.example.com:5432/app?sslmode=require"),
    ("postgresql://a@localhost/app", "postgresql://b@127.0.0.1:5432/app"),
    ("postgresql://a@localhost/app", "postgresql://b@127.42.1.9:5432/app"),
    ("postgresql://a@[::1]/app", "postgresql://b@localhost:5432/app"),
    ("postgresql://a@[::ffff:127.0.0.1]/app", "postgresql://b@localhost/app"),
    ("postgresql://a@localhost.localdomain/app", "postgresql://b@localhost/app"),
    (MAIN_DIRECT, f"postgresql+psycopg://another:changed@DB.{MAIN_PROJECT.upper()}.SUPABASE.CO/postgres?sslmode=require"),
    (MAIN_DIRECT, f"postgresql://postgres@db.{MAIN_PROJECT}.supabase.co:6543/postgres"),
    (MAIN_DIRECT, f"postgresql://postgres.{MAIN_PROJECT}:other@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres"),
    (MAIN_DIRECT, f"postgresql://custom_role.{MAIN_PROJECT}@aws-1-eu-west-1.pooler.supabase.com:6543/postgres"),
    (f"postgresql://postgres.{MAIN_PROJECT}@aws-0-region.pooler.supabase.com:5432/postgres",
     f"postgresql+psycopg://custom_role.{MAIN_PROJECT}@aws-0-region.pooler.supabase.com:6543/postgres?sslmode=require"),
    (f"postgresql://postgres.{MAIN_PROJECT}@aws-0-region.pooler.supabase.com/postgres",
     f"postgresql://role.{MAIN_PROJECT}@gcp-1-region.pooler.supabase.com:6543/postgres"),
])
def test_same_database_variations_are_refused(main, test):
    with pytest.raises(UnsafePostgresTestDatabase, match="DATABASE_URL database"):
        require_separate_test_database(test, main)


@pytest.mark.parametrize("main,test", [
    ("postgresql://a@db.example.com/app", "postgresql://a@db-alias.example.com/app"),
    ("postgresql://a@db.example.com/app", "postgresql://a@db.example.com:6543/app"),
    ("postgresql://a@10.1.2.3/app", "postgresql://a@db.example.com/app"),
])
def test_unknown_host_or_port_aliases_with_same_database_name_fail_closed(main, test):
    with pytest.raises(UnsafePostgresTestDatabase, match="cannot be established offline"):
        require_separate_test_database(test, main)


@pytest.mark.parametrize("main,test", [
    ("postgresql://a@localhost/app", "postgresql://a@localhost/app_test"),
    ("postgresql://a@db.example.com/App", "postgresql://a@db.example.com/app"),
    ("postgresql://a@db.example.com/app", "postgresql://b@other.example.com/app_test"),
    (MAIN_DIRECT, f"postgresql://postgres@db.{TEST_PROJECT}.supabase.co/postgres"),
    (MAIN_DIRECT, f"postgresql://custom_role.{TEST_PROJECT}@aws-0-region.pooler.supabase.com:6543/postgres"),
    (f"postgresql://postgres.{MAIN_PROJECT}@aws-0-region.pooler.supabase.com/postgres",
     f"postgresql://postgres.{TEST_PROJECT}@aws-0-region.pooler.supabase.com/postgres"),
    (MAIN_DIRECT, f"postgresql://postgres.{MAIN_PROJECT}@aws-0-region.pooler.supabase.com/postgres_test"),
    (MAIN_DIRECT, f"postgresql://postgres@db.{MAIN_PROJECT}.supabase.co/postgres_test"),
    (f"postgresql://postgres.{MAIN_PROJECT}@aws-0-region.pooler.supabase.com:5432/postgres",
     f"postgresql://role.{MAIN_PROJECT}@aws-0-region.pooler.supabase.com:6543/postgres_test"),
    (MAIN_DIRECT, "postgresql://postgres@custom-db.example.com/postgres_test"),
    ("postgresql://postgres@custom-db.example.com/postgres_test", MAIN_DIRECT),
])
def test_explicitly_distinct_database_names_or_supabase_projects_are_allowed(main, test):
    identity = require_separate_test_database(test, main)
    assert identity == get_database_identity(test, setting="TEST_DATABASE_URL")


@pytest.mark.parametrize("custom", [
    "postgresql://postgres@custom-db.example.com/postgres",
])
def test_mixed_custom_alias_and_supabase_endpoints_with_same_name_are_uncertain(custom):
    for main, test in [(MAIN_DIRECT, custom), (custom, MAIN_DIRECT)]:
        with pytest.raises(UnsafePostgresTestDatabase, match="project identity cannot be established offline"):
            require_separate_test_database(test, main)


@pytest.mark.parametrize("invalid", [
    None, "", "   ", "not-a-url-with-main-secret", "postgresql://a@localhost:invalid/app",
    "postgresql://a@localhost:0/app", "postgresql://a@localhost:65536/app",
    "mysql://a@localhost/app", "postgresql:///app", "postgresql://a@localhost",
    "postgresql://a@127.1/app", "postgresql://a@host1,host2/app",
    "postgresql://a@db.example.com/app?hostaddr=127.0.0.1",
    "postgresql://a@aws-0-region.pooler.supabase.com/postgres",
    "postgresql://postgres.not-a-project@aws-0-region.pooler.supabase.com/postgres",
    f"postgresql://postgres.{MAIN_PROJECT}@project.supabase.co/postgres",
    f"postgresql://postgres@db.{MAIN_PROJECT}.supabase.co:6432/postgres",
])
def test_missing_invalid_or_uncertain_main_url_is_refused(invalid):
    with pytest.raises(UnsafePostgresTestDatabase, match="DATABASE_URL:") as caught:
        require_separate_test_database("postgresql://a@localhost/app_test", invalid)
    assert "main-secret" not in str(caught.value)


@pytest.mark.parametrize("invalid", [None, "", "postgresql:///app_test", "invalid-test-secret"])
def test_missing_invalid_or_uncertain_test_url_is_refused(invalid):
    with pytest.raises(UnsafePostgresTestDatabase, match="TEST_DATABASE_URL:") as caught:
        require_separate_test_database(invalid, "postgresql://a@localhost/app")
    assert "test-secret" not in str(caught.value)


@pytest.mark.parametrize("option", [
    "host=main.example.com", "hostaddr=127.0.0.1", "port=5432", "dbname=app",
    "database=app", "user=postgres", "username=postgres", "service=production",
    "servicefile=/tmp/pg-service.conf", "Host=main.example.com", "host=a&host=b",
])
@pytest.mark.parametrize("setting", ["DATABASE_URL", "TEST_DATABASE_URL"])
def test_connection_routing_query_options_cannot_override_guarded_identity(option, setting):
    with pytest.raises(UnsafePostgresTestDatabase, match="routing query parameters"):
        get_database_identity(f"postgresql://user:secret@localhost/app_test?{option}", setting=setting)


def test_credentials_do_not_form_part_of_generic_database_identity():
    assert get_database_identity("postgresql://first:a@localhost/app", setting="first") == \
        get_database_identity("postgresql+psycopg://second:b@127.0.0.1:5432/app?sslmode=verify-full",
                              setting="second")


def load_fixture_function(name, namespace):
    """Compile only the production function, avoiding its app/.env imports."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
    function.decorator_list = []
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace[name]


@pytest.mark.parametrize("main,test", [
    (None, "postgresql://a@localhost/app_test"),
    ("broken-main-secret", "postgresql://a@localhost/app_test"),
    ("postgresql://first@localhost/app", "postgresql://second@127.0.0.1:5432/app"),
    (MAIN_DIRECT, f"postgresql://postgres.{MAIN_PROJECT}@aws-0-region.pooler.supabase.com:6543/postgres"),
    ("postgresql://a@localhost/app", None),
])
def test_fixture_refuses_unsafe_targets_before_creating_any_test_engine(main, test):
    calls = []
    namespace = {
        "POSTGRES_TESTS_ENABLED": True,
        "pytest": pytest,
        "_setting": {"DATABASE_URL": main, "TEST_DATABASE_URL": test}.get,
        "UnsafePostgresTestDatabase": UnsafePostgresTestDatabase,
        "require_separate_test_database": require_separate_test_database,
        "create_engine": lambda *args, **kwargs: calls.append("create_engine"),
        "_truncate": lambda *args: calls.append("truncate"),
    }
    fixture = load_fixture_function("pg", namespace)
    with pytest.raises(pytest.fail.Exception, match="refusing PostgreSQL writes or TRUNCATE"):
        next(fixture())
    assert calls == []


def test_disabled_fixture_does_not_read_settings_or_create_an_engine():
    def forbidden(*args, **kwargs):
        pytest.fail("disabled fixture reached settings, engine or truncate")

    namespace = {
        "POSTGRES_TESTS_ENABLED": False, "pytest": pytest,
        "_setting": forbidden, "create_engine": forbidden, "_truncate": forbidden,
    }
    fixture = load_fixture_function("pg", namespace)
    with pytest.raises(pytest.skip.Exception, match="RUN_POSTGRES_TESTS=1"):
        next(fixture())


def test_fixture_reaches_engine_creation_only_after_separation_is_checked():
    calls = []

    class ReachedEngine(Exception):
        pass

    def check(*args):
        calls.append("guard")
        return require_separate_test_database(*args)

    def create(*args, **kwargs):
        calls.append("engine")
        raise ReachedEngine

    namespace = {
        "POSTGRES_TESTS_ENABLED": True, "pytest": pytest,
        "_setting": {"DATABASE_URL": "postgresql://a@localhost/app",
                     "TEST_DATABASE_URL": "postgresql://a@localhost/app_test"}.get,
        "UnsafePostgresTestDatabase": UnsafePostgresTestDatabase,
        "require_separate_test_database": check, "create_engine": create,
    }
    fixture = load_fixture_function("pg", namespace)
    with pytest.raises(ReachedEngine):
        next(fixture())
    assert calls == ["guard", "engine"]


def test_truncate_quotes_names_and_qualifies_the_public_schema():
    statements = []

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): return False

        def execute(self, sql):
            statements.append(str(sql))
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: ['Users', 'odd"table']))

    fake_engine = SimpleNamespace(dialect=dialect(), begin=Connection)
    truncate = load_fixture_function("_truncate", {"text": lambda value: value})
    truncate(fake_engine)
    assert "schemaname = 'public'" in statements[0]
    assert "tablename <> 'alembic_version'" in statements[0]
    assert statements[1] == 'TRUNCATE TABLE "public"."Users", "public"."odd""table" RESTART IDENTITY CASCADE'


def test_conftest_freezes_the_shared_opt_in_before_application_test_imports():
    tree = ast.parse(Path(__file__).with_name("conftest.py").read_text(encoding="utf-8"))
    imports = [node for node in tree.body if isinstance(node, ast.ImportFrom)]
    assert any(node.module == "tests.postgres_safety" and
               any(name.name == "POSTGRES_TESTS_ENABLED" for name in node.names) for node in imports)
    assert not any((node.module or "").startswith("app") for node in imports)


@pytest.mark.parametrize("enabled", [False, True])
def test_process_opt_in_is_frozen_before_later_dotenv_environment_changes(enabled):
    # A fresh process imports the actual conftest/helper before simulating a
    # subsequent app import that changes os.environ from dotenv. No .env is read.
    task_env = os.environ.copy()
    task_env.pop("RUN_POSTGRES_TESTS", None)
    if enabled:
        task_env["RUN_POSTGRES_TESTS"] = "1"
    probe = (
        "import os; from tests import conftest; "
        "before = conftest.POSTGRES_TESTS_ENABLED; "
        "os.environ['RUN_POSTGRES_TESTS'] = '0' if before else '1'; "
        "from tests.postgres_safety import POSTGRES_TESTS_ENABLED; "
        "print(before, POSTGRES_TESTS_ENABLED)"
    )
    result = subprocess.run([sys.executable, "-c", probe], env=task_env,
                            cwd=SOURCE.parents[1], text=True, capture_output=True, check=True)
    assert result.stdout.strip() == ("True True" if enabled else "False False")
