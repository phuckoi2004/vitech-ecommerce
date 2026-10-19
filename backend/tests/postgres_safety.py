"""Offline guard for the destructive PostgreSQL integration-test fixture.

URL text alone does not establish a separate database: credentials, drivers,
SSL options, default ports and Supabase direct/pooler endpoints may differ while
targeting the same database. No DNS lookup or database connection is made here.

Supabase endpoint formats:
https://supabase.com/docs/guides/database/connecting-to-postgres
Supavisor supports separate databases and pools by user/database/mode:
https://supabase.com/docs/guides/troubleshooting/supavisor-faq-YyP5tI

Generic PostgreSQL URLs use their explicit database name. Different generic
hosts/ports with the same name are ambiguous and rejected, since aliases or a
proxy may still reach the main database. Custom proxy database-name aliases are
unsupported; the URL must name the actual dedicated test database.
An explicit distinct database name also establishes separation within the same
Supabase project: Supavisor uses the database name supplied in the URL.

require_test_database_target is the stricter gate every destructive entry point uses (the pg and api_engine
fixtures and postgres_test_lock). On top of that separation it requires the declared Supabase project
(TEST_DATABASE_PROJECT_REF, not a secret), never a protected (Production) project or the DATABASE_URL project
whatever the database name, Supabase session mode on port 5432, only allowlisted URL query parameters and no libpq
environment variable that could change the connection target; any other remote host is refused, while a local
(loopback) PostgreSQL needs no project ref. It checks configuration only: URLs prove what the configuration says,
not which server answers.
"""

import ipaddress
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

# tests/conftest.py imports this module before collecting application tests.
# Freeze explicit process opt-in before app.database can load backend/.env.
POSTGRES_TESTS_ENABLED = os.getenv("RUN_POSTGRES_TESTS") == "1"


class UnsafePostgresTestDatabase(ValueError):
    """A separate destructive-test target could not be established offline."""


@dataclass(frozen=True)
class PostgresDatabaseIdentity:
    host: str
    port: int
    database: str
    supabase_project: str | None = None


# libpq/driver query parameters can override the URL parts used for comparison.
# In particular, a shared Supabase pooler routes by its tenant-bearing username.
_ROUTING_QUERY_KEYS = frozenset({
    "host", "hostaddr", "port", "dbname", "database", "user", "username",
    "service", "servicefile",
})
_PROJECT_REF = r"[a-z0-9]{20}"
_DIRECT_SUPABASE_HOST = re.compile(rf"db\.({_PROJECT_REF})\.supabase\.co\Z")
_POOLER_USERNAME = re.compile(rf".+\.({_PROJECT_REF})\Z")
_HOST_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
_LOOPBACK_NAMES = frozenset({"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"})

# Supabase projects that are never a test target, whatever the other settings say (Production).
PROTECTED_PROJECT_REFS = frozenset({"stkvyiqosljeehbkqteb"})
TEST_PROJECT_SETTING = "TEST_DATABASE_PROJECT_REF"
_PROJECT_REF_FORMAT = re.compile(_PROJECT_REF)
# Session mode: the run lock is a session-level advisory lock (transaction-mode poolers break it).
_SUPABASE_SESSION_PORT = 5432
# libpq query parameters that cannot change which server, database or role is reached (``options`` can).
_ALLOWED_TEST_QUERY_KEYS = frozenset({
    "sslmode", "sslrootcert", "sslcert", "sslkey", "sslcrl", "channel_binding", "gssencmode",
    "connect_timeout", "application_name", "keepalives", "keepalives_idle", "keepalives_interval",
    "keepalives_count", "tcp_user_timeout",
})
# libpq applies these to every parameter the URL leaves out (PGHOSTADDR and PGOPTIONS can redirect a session).
LIBPQ_ROUTING_ENVIRONMENT = (
    "PGHOST", "PGHOSTADDR", "PGPORT", "PGDATABASE", "PGUSER", "PGOPTIONS", "PGSERVICE", "PGSERVICEFILE",
)


def _refuse(setting: str, reason: str) -> None:
    # Never include URLs, credentials or parser exceptions in failure output.
    raise UnsafePostgresTestDatabase(
        f"{setting}: {reason}; refusing PostgreSQL writes or TRUNCATE"
    ) from None


def _canonical_host(host: str, setting: str) -> str:
    host = host.lower().rstrip(".")
    if host in _LOOPBACK_NAMES:
        return "loopback"
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        # Reject socket/multi-host/hostaddr syntax and ambiguous numeric address
        # shortcuts instead of attempting to resolve them over the network.
        if not host or len(host) > 253 or all(c in "0123456789." for c in host):
            _refuse(setting, "missing or unsupported host")
        if any(not _HOST_LABEL.fullmatch(label) for label in host.split(".")):
            _refuse(setting, "missing or unsupported host")
        return host
    mapped = getattr(address, "ipv4_mapped", None)
    if address.is_loopback or (mapped is not None and mapped.is_loopback):
        return "loopback"
    return address.compressed


def get_database_identity(value: str | None, *, setting: str) -> PostgresDatabaseIdentity:
    """Parse an explicit PostgreSQL target or refuse an uncertain/overridden URL."""
    if not isinstance(value, str) or not value.strip():
        _refuse(setting, "an explicit database URL is required")
    try:
        url = make_url(value.strip())
        backend, host, port, database = url.get_backend_name(), url.host, url.port, url.database
    except (ArgumentError, TypeError, ValueError):
        _refuse(setting, "invalid database URL")
    if backend != "postgresql":
        _refuse(setting, "a PostgreSQL URL is required")
    if _ROUTING_QUERY_KEYS.intersection(key.lower() for key in url.query):
        _refuse(setting, "connection-routing query parameters are unsupported")
    if not host or not database or "\x00" in database:
        _refuse(setting, "explicit host and database name are required")
    host = _canonical_host(host, setting)
    port = 5432 if port is None else port
    if not 1 <= port <= 65535:
        _refuse(setting, "invalid PostgreSQL port")

    project = None
    direct = _DIRECT_SUPABASE_HOST.fullmatch(host)
    if direct:
        project = direct.group(1)
    elif host.endswith(".pooler.supabase.com"):
        tenant = _POOLER_USERNAME.fullmatch((url.username or "").lower())
        if tenant is None:
            _refuse(setting, "Supabase pooler project identity is missing or invalid")
        project = tenant.group(1)
    elif host.endswith(".supabase.co") or host.endswith(".supabase.com"):
        _refuse(setting, "unsupported Supabase endpoint identity")
    if project is not None and port not in (5432, 6543):
        _refuse(setting, "unsupported Supabase PostgreSQL port")
    return PostgresDatabaseIdentity(host, port, database, project)


def require_separate_test_database(
    test_url: str | None, main_url: str | None
) -> PostgresDatabaseIdentity:
    """Allow only an established separate target, before creating a test engine.

    Credentials and connection-driver/SSL differences never establish separation.
    Distinct explicit PostgreSQL database names, or distinct recognized Supabase
    projects, do. Unknown host aliases with the same database name fail closed,
    including mixed custom/Supabase endpoints that cannot be compared offline.
    """
    main = get_database_identity(main_url, setting="DATABASE_URL")
    test = get_database_identity(test_url, setting="TEST_DATABASE_URL")
    if test.database != main.database:
        return test
    if main.supabase_project is not None and test.supabase_project is not None:
        if main.supabase_project != test.supabase_project:
            return test
        _refuse("TEST_DATABASE_URL", "it targets the DATABASE_URL database")
    if main.supabase_project is not None or test.supabase_project is not None:
        _refuse("TEST_DATABASE_URL", "a separate Supabase project identity cannot be established offline")
    if (test.host, test.port) == (main.host, main.port):
        _refuse("TEST_DATABASE_URL", "it targets the DATABASE_URL database")
    _refuse("TEST_DATABASE_URL", "a separate database identity cannot be established offline")


def require_test_database_target(
    test_url: str | None,
    main_url: str | None,
    *,
    expected_project: str | None,
    environ: Mapping[str, str],
) -> PostgresDatabaseIdentity:
    """Allow only the approved test database, before any test engine, lock connection or write.

    ``expected_project`` is TEST_DATABASE_PROJECT_REF; ``environ`` is the process environment libpq will read.
    Refusals name the setting and the reason only, never a URL, host, role, password or project ref.
    """
    test = require_separate_test_database(test_url, main_url)
    main = get_database_identity(main_url, setting="DATABASE_URL")

    routing = [name for name in LIBPQ_ROUTING_ENVIRONMENT if (environ.get(name) or "").strip()]
    if routing:
        _refuse("environment", f"libpq connection variables are set ({', '.join(routing)})")
    unsupported = sorted({key.lower() for key in make_url(test_url.strip()).query} - _ALLOWED_TEST_QUERY_KEYS)
    if unsupported:
        _refuse("TEST_DATABASE_URL", f"unsupported connection query parameters ({', '.join(unsupported)})")

    expected = (expected_project or "").strip()
    if test.supabase_project is None:
        if expected:
            _refuse(TEST_PROJECT_SETTING, "is set but TEST_DATABASE_URL is not a Supabase database")
        if test.host != "loopback":
            _refuse("TEST_DATABASE_URL", "only a Supabase project or a local (loopback) PostgreSQL is allowed")
        return test

    if not expected:
        _refuse(TEST_PROJECT_SETTING, "is required for a Supabase test database")
    if not _PROJECT_REF_FORMAT.fullmatch(expected):
        _refuse(TEST_PROJECT_SETTING, "must be a 20-character lowercase Supabase project ref")
    if expected in PROTECTED_PROJECT_REFS:
        _refuse(TEST_PROJECT_SETTING, "names a protected project")
    if test.supabase_project in PROTECTED_PROJECT_REFS:
        _refuse("TEST_DATABASE_URL", "it targets a protected project")
    if test.supabase_project == main.supabase_project:
        _refuse("TEST_DATABASE_URL", "it targets the DATABASE_URL Supabase project, whatever the database name")
    if test.supabase_project != expected:
        _refuse("TEST_DATABASE_URL", f"it does not belong to {TEST_PROJECT_SETTING}")
    if test.port != _SUPABASE_SESSION_PORT:
        _refuse("TEST_DATABASE_URL", f"a Supabase test database must use session mode on port {_SUPABASE_SESSION_PORT}")
    return test
