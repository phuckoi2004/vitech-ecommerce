"""Pure safety tests: no application imports, dotenv, database or network access."""

import ast
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from sqlalchemy.dialects.postgresql import dialect

from tests.postgres_safety import (
    LIBPQ_ROUTING_ENVIRONMENT,
    PROTECTED_PROJECT_REFS,
    UnsafePostgresTestDatabase,
    get_database_identity,
    require_separate_test_database,
    require_test_database_target,
)

MAIN_PROJECT = "abcdefghijklmnopqrst"
TEST_PROJECT = "zyxwvutsrqponmlkjihg"
MAIN_DIRECT = f"postgresql://postgres:main-secret@db.{MAIN_PROJECT}.supabase.co:5432/postgres"
SOURCE = Path(__file__).with_name("test_postgres_integration.py")
API_CONFTEST = Path(__file__).parent / "api" / "conftest.py"
LOCK_SOURCE = Path(__file__).with_name("conftest.py")
FIXTURES = [pytest.param(SOURCE, "pg", id="pg"), pytest.param(API_CONFTEST, "api_engine", id="api_engine")]

# require_test_database_target: the declared test project stands for Staging; PRODUCTION is the protected project.
PRODUCTION = "stkvyiqosljeehbkqteb"
POOLER = "aws-0-ap-southeast-1.pooler.supabase.com"
PRODUCTION_DIRECT = f"postgresql://postgres:prod-main-s3cret@db.{PRODUCTION}.supabase.co:5432/postgres"
PRODUCTION_POOLER = f"postgresql://postgres.{PRODUCTION}:prod-pool-s3cret@{POOLER}:5432/postgres"
STAGING_POOLER = f"postgresql://postgres.{TEST_PROJECT}:stage-pool-s3cret@{POOLER}:5432/postgres"
STAGING_DIRECT = f"postgresql://postgres:stage-direct-s3cret@db.{TEST_PROJECT}.supabase.co:5432/postgres"
LOCAL_MAIN = "postgresql://app:local-main-s3cret@localhost/app"
LOCAL_TEST = "postgresql://app:local-test-s3cret@127.0.0.1:5432/app_test"
# Nothing of these may appear in a refusal: passwords, hosts, roles, URLs or project refs.
SENSITIVE = ("s3cret", POOLER, "supabase.co", "postgresql", "@", "postgres.", PRODUCTION, TEST_PROJECT,
             MAIN_PROJECT, "aaaaaaaaaaaaaaaaaaaa", "custom-db", "10.1.2.3", "127.0.0.1", "localhost")


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


class LockRecorder:
    """Stands in for pytest's request: records when the run lock fixture is taken."""

    def __init__(self, calls):
        self.calls = calls

    def getfixturevalue(self, name):
        self.calls.append(name)


def load_fixture_function(name, namespace, source=SOURCE):
    """Compile only the production function, avoiding its app/.env imports."""
    tree = ast.parse(source.read_text(encoding="utf-8"))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
    function.decorator_list = []
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), namespace)
    return namespace[name]


@pytest.mark.parametrize("source,name", FIXTURES)
@pytest.mark.parametrize("main,test,project,environ", [
    (None, "postgresql://a@localhost/app_test", None, {}),
    ("broken-main-secret", "postgresql://a@localhost/app_test", None, {}),
    ("postgresql://first@localhost/app", "postgresql://second@127.0.0.1:5432/app", None, {}),
    (MAIN_DIRECT, f"postgresql://postgres.{MAIN_PROJECT}@aws-0-region.pooler.supabase.com:6543/postgres", None, {}),
    ("postgresql://a@localhost/app", None, None, {}),
    (PRODUCTION_DIRECT, STAGING_POOLER, None, {}),  # no declared project
    (LOCAL_MAIN, PRODUCTION_POOLER, PRODUCTION, {}),  # the protected project
    (PRODUCTION_DIRECT, STAGING_POOLER, TEST_PROJECT, {"PGHOSTADDR": "10.9.8.7"}),  # libpq could redirect it
])
def test_fixture_refuses_unsafe_targets_before_creating_any_test_engine(source, name, main, test, project, environ):
    calls = []
    namespace = {
        "POSTGRES_TESTS_ENABLED": True,
        "pytest": pytest,
        "os": SimpleNamespace(environ=environ),
        "_setting": {"DATABASE_URL": main, "TEST_DATABASE_URL": test, "TEST_DATABASE_PROJECT_REF": project}.get,
        "UnsafePostgresTestDatabase": UnsafePostgresTestDatabase,
        "require_test_database_target": require_test_database_target,
        "create_engine": lambda *args, **kwargs: calls.append("create_engine"),
        "_truncate": lambda *args: calls.append("truncate"),
    }
    fixture = load_fixture_function(name, namespace, source)
    with pytest.raises(pytest.fail.Exception, match="refusing PostgreSQL writes or TRUNCATE"):
        next(fixture(LockRecorder(calls)))
    assert calls == []


@pytest.mark.parametrize("source,name", FIXTURES)
def test_disabled_fixture_does_not_read_settings_or_create_an_engine(source, name):
    def forbidden(*args, **kwargs):
        pytest.fail("disabled fixture reached settings, engine or truncate")

    namespace = {
        "POSTGRES_TESTS_ENABLED": False, "pytest": pytest, "os": SimpleNamespace(environ=None),
        "_setting": forbidden, "create_engine": forbidden, "_truncate": forbidden,
        "require_test_database_target": forbidden,
    }
    fixture = load_fixture_function(name, namespace, source)
    with pytest.raises(pytest.skip.Exception, match="RUN_POSTGRES_TESTS=1"):
        next(fixture(LockRecorder([])))


@pytest.mark.parametrize("source,name", FIXTURES)
@pytest.mark.parametrize("main,test,project", [
    ("postgresql://a@localhost/app", "postgresql://a@localhost/app_test", None),
    (PRODUCTION_DIRECT, STAGING_POOLER, TEST_PROJECT),
])
def test_fixture_reaches_engine_creation_only_after_separation_is_checked(source, name, main, test, project):
    calls = []

    class ReachedEngine(Exception):
        pass

    def check(*args, **kwargs):
        calls.append("guard")
        return require_test_database_target(*args, **kwargs)

    def create(*args, **kwargs):
        calls.append("engine")
        raise ReachedEngine

    namespace = {
        "POSTGRES_TESTS_ENABLED": True, "pytest": pytest, "os": SimpleNamespace(environ={}),
        "_setting": {"DATABASE_URL": main, "TEST_DATABASE_URL": test, "TEST_DATABASE_PROJECT_REF": project}.get,
        "UnsafePostgresTestDatabase": UnsafePostgresTestDatabase,
        "require_test_database_target": check, "create_engine": create,
    }
    fixture = load_fixture_function(name, namespace, source)
    with pytest.raises(ReachedEngine):
        next(fixture(LockRecorder(calls)))
    # The run lock (a connection to the test database) is only taken after the offline guard passed.
    assert calls == ["guard", "postgres_test_lock", "engine"]


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


# ------------------------------------------------------------------------------------- require_test_database_target


def target(test, main=PRODUCTION_DIRECT, project=TEST_PROJECT, environ=None):
    return require_test_database_target(test, main, expected_project=project, environ=environ or {})


def test_production_is_a_protected_project():
    assert PRODUCTION in PROTECTED_PROJECT_REFS


@pytest.mark.parametrize("test,main,project,environ", [
    (STAGING_POOLER, PRODUCTION_DIRECT, TEST_PROJECT, {}),
    (STAGING_DIRECT, PRODUCTION_DIRECT, TEST_PROJECT, {}),
    (f"{STAGING_POOLER}?sslmode=require&application_name=vietech-tests&connect_timeout=10",
     PRODUCTION_DIRECT, TEST_PROJECT, {}),
    (STAGING_POOLER, LOCAL_MAIN, f"  {TEST_PROJECT}\n", {}),
    (STAGING_POOLER, PRODUCTION_DIRECT, TEST_PROJECT, {"PGHOST": "", "PGUSER": "   ", "PGSSLMODE": "require"}),
    (LOCAL_TEST, LOCAL_MAIN, None, {}),
    (LOCAL_TEST, LOCAL_MAIN, "   ", {}),
])
def test_target_allows_the_declared_supabase_project_or_a_local_database(test, main, project, environ):
    assert target(test, main, project, environ) == get_database_identity(test, setting="TEST_DATABASE_URL")


REFUSALS = [
    *[pytest.param(STAGING_POOLER, PRODUCTION_DIRECT, missing, {}, "TEST_DATABASE_PROJECT_REF: is required",
                   id=f"project-missing-{index}") for index, missing in enumerate((None, "", "   "))],
    *[pytest.param(STAGING_POOLER, PRODUCTION_DIRECT, malformed, {}, "must be a 20-character lowercase",
                   id=f"project-malformed-{index}")
      for index, malformed in enumerate((TEST_PROJECT.upper(), TEST_PROJECT[:-1], TEST_PROJECT + "a",
                                         "zyxwvutsrq-ponmlkjih", "zyxwvutsrq ponmlkjih", "zyxwvutsrqponmlkjihé"))],
    pytest.param(STAGING_POOLER, PRODUCTION_DIRECT, PRODUCTION, {}, "names a protected project",
                 id="project-is-production"),
    pytest.param(PRODUCTION_POOLER, LOCAL_MAIN, PRODUCTION, {}, "names a protected project",
                 id="production-while-database-url-is-local"),
    pytest.param(PRODUCTION_POOLER, LOCAL_MAIN, TEST_PROJECT, {}, "targets a protected project",
                 id="pooler-url-is-production"),
    pytest.param(f"postgresql://postgres:direct-s3cret@db.{PRODUCTION}.supabase.co:5432/postgres", LOCAL_MAIN,
                 TEST_PROJECT, {}, "targets a protected project", id="direct-url-is-production"),
    pytest.param(f"postgresql://postgres.{MAIN_PROJECT}:other-s3cret@{POOLER}:5432/postgres_test", MAIN_DIRECT,
                 MAIN_PROJECT, {}, "targets the DATABASE_URL Supabase project", id="same-project-other-database"),
    pytest.param(STAGING_POOLER, STAGING_DIRECT, TEST_PROJECT, {}, "targets the DATABASE_URL database",
                 id="same-database-as-database-url"),
    pytest.param(STAGING_POOLER, PRODUCTION_DIRECT, "aaaaaaaaaaaaaaaaaaaa", {},
                 "does not belong to TEST_DATABASE_PROJECT_REF", id="project-mismatch"),
    pytest.param(LOCAL_TEST, LOCAL_MAIN, TEST_PROJECT, {}, "is set but TEST_DATABASE_URL is not a Supabase database",
                 id="local-database-with-project"),
    pytest.param("postgresql://app:remote-s3cret@custom-db.example.com/app_test", LOCAL_MAIN, None, {},
                 "only a Supabase project or a local", id="remote-host"),
    pytest.param("postgresql://app:remote-s3cret@10.1.2.3/app_test", LOCAL_MAIN, None, {},
                 "only a Supabase project or a local", id="remote-address"),
    pytest.param(STAGING_POOLER.replace(":5432/", ":6543/"), PRODUCTION_DIRECT, TEST_PROJECT, {},
                 "session mode on port 5432", id="pooler-transaction-mode"),
    pytest.param(STAGING_DIRECT.replace(":5432/", ":6543/"), PRODUCTION_DIRECT, TEST_PROJECT, {},
                 "session mode on port 5432", id="direct-host-port-6543"),
    *[pytest.param(f"{STAGING_POOLER}?{query}", PRODUCTION_DIRECT, TEST_PROJECT, {},
                   "unsupported connection query parameters", id=f"query-{index}")
      for index, query in enumerate((f"options=reference%3D{PRODUCTION}", "options=-c%20search_path%3Dpublic",
                                     "sslmode=require&options=x", "password=qs-s3cret", "foo=bar"))],
    *[pytest.param(STAGING_POOLER, PRODUCTION_DIRECT, TEST_PROJECT, {name: "routing-s3cret"},
                   "libpq connection variables are set", id=f"environment-{name}")
      for name in LIBPQ_ROUTING_ENVIRONMENT],
]


@pytest.mark.parametrize("test,main,project,environ,reason", REFUSALS)
def test_target_refuses_without_revealing_connection_details(test, main, project, environ, reason):
    with pytest.raises(UnsafePostgresTestDatabase, match="refusing PostgreSQL writes or TRUNCATE") as caught:
        target(test, main, project, environ)
    message = str(caught.value)
    assert reason in message
    assert not [secret for secret in SENSITIVE if secret in message], message


# ------------------------------------------------------------------------------------- postgres_test_lock


class BusyTestDatabase(RuntimeError):
    pass


def run_lock_fixture(monkeypatch, settings, environ=None):
    """postgres_test_lock with stand-ins for dotenv and the lock: no .env is read and no connection is opened."""
    for name in ("TEST_DATABASE_URL", "DATABASE_URL", "TEST_DATABASE_PROJECT_REF", *LIBPQ_ROUTING_ENVIRONMENT):
        monkeypatch.delenv(name, raising=False)
    for name, value in (environ or {}).items():
        monkeypatch.setenv(name, value)
    locked = []

    @contextmanager
    def exclusive_test_database(test_url):
        locked.append(test_url)
        yield

    dotenv = ModuleType("dotenv")
    dotenv.dotenv_values = lambda path: dict(settings)
    lock = ModuleType("tests.postgres_lock")
    lock.BusyTestDatabase, lock.exclusive_test_database = BusyTestDatabase, exclusive_test_database
    monkeypatch.setitem(sys.modules, "dotenv", dotenv)
    monkeypatch.setitem(sys.modules, "tests.postgres_lock", lock)
    namespace = {"os": os, "Path": Path, "pytest": pytest, "__file__": str(LOCK_SOURCE)}  # the stand-in reads nothing
    fixture = load_fixture_function("postgres_test_lock", namespace, LOCK_SOURCE)
    return fixture(), locked


APPROVED_SETTINGS = {"TEST_DATABASE_URL": STAGING_POOLER, "DATABASE_URL": PRODUCTION_DIRECT,
                     "TEST_DATABASE_PROJECT_REF": TEST_PROJECT}


@pytest.mark.parametrize("settings,environ,reason", [
    ({"TEST_DATABASE_URL": STAGING_POOLER, "DATABASE_URL": PRODUCTION_DIRECT}, None,
     "TEST_DATABASE_PROJECT_REF: is required"),
    ({"TEST_DATABASE_URL": PRODUCTION_POOLER, "DATABASE_URL": LOCAL_MAIN, "TEST_DATABASE_PROJECT_REF": PRODUCTION},
     None, "names a protected project"),
    (APPROVED_SETTINGS, {"PGOPTIONS": "-c search_path=public"}, "libpq connection variables are set"),
])
def test_run_lock_refuses_an_unapproved_target_before_connecting(monkeypatch, settings, environ, reason):
    lock_fixture, locked = run_lock_fixture(monkeypatch, settings, environ)
    with pytest.raises(pytest.fail.Exception, match=reason):
        next(lock_fixture)
    assert locked == []


def test_run_lock_is_taken_only_after_the_target_check(monkeypatch):
    lock_fixture, locked = run_lock_fixture(monkeypatch, APPROVED_SETTINGS)
    next(lock_fixture)
    assert locked == [STAGING_POOLER]
    lock_fixture.close()


@pytest.mark.parametrize("source,name,first_connection", [
    (SOURCE, "pg", "postgres_test_lock"),
    (API_CONFTEST, "api_engine", "postgres_test_lock"),
    (LOCK_SOURCE, "postgres_test_lock", "exclusive_test_database"),
])
def test_every_destructive_entry_point_checks_the_target_before_connecting(source, name, first_connection):
    tree = ast.parse(source.read_text(encoding="utf-8"))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
    calls = [node for node in ast.walk(function) if isinstance(node, ast.Call)]

    def first_line(predicate):
        return min(call.lineno for call in calls if predicate(call))

    assert not [call for call in calls if ast.unparse(call.func) == "require_separate_test_database"]
    guard = first_line(lambda call: ast.unparse(call.func) == "require_test_database_target")
    assert guard < first_line(lambda call: first_connection in ast.unparse(call))
    if name != "postgres_test_lock":
        assert guard < first_line(lambda call: ast.unparse(call.func) == "create_engine")
