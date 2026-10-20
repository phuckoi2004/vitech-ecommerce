"""Backend settings files, read before anything uses os.environ (app.database, alembic/env.py).

- backend/.env.local (development overrides, gitignored) is read first, then backend/.env. A variable already set in
  the process environment always wins and a file never replaces an existing value (same as load_dotenv
  override=False), so app.core.config and app.core.storage see the .env.local values too.
- DATABASE_URL is never exported from these files. backend/.env holds the team's shared database. A developer who
  keeps a separate local database creates backend/.env.local: then, in development and test (APP_ENV, "development"
  when unset, as in app.core.config), DATABASE_URL comes from the process environment or .env.local only, and a
  missing or shared value in .env.local stops the app instead of falling back to backend/.env. Without .env.local, and
  in production, backend/.env (or the process environment) provides it.
Error messages name files and settings only, never a value.
"""

import os
from functools import lru_cache
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_DIR / ".env"
LOCAL_ENV_FILE = BACKEND_DIR / ".env.local"
LOCAL_PROFILES = frozenset({"development", "test"})


class EnvironmentConfigError(RuntimeError):
    """DATABASE_URL missing, or backend/.env.local missing it or pointing at the shared database."""


def _read(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return {key: value.strip() for key, value in dotenv_values(path).items() if value is not None}


@lru_cache(maxsize=1)
def load_environment() -> None:
    """Export the settings of .env.local, then .env, except DATABASE_URL, without replacing existing variables."""
    for values in (_read(LOCAL_ENV_FILE), _read(ENV_FILE)):
        for key, value in values.items():
            if key != "DATABASE_URL":
                os.environ.setdefault(key, value)


def app_env() -> str:
    load_environment()
    return (os.environ.get("APP_ENV") or "development").strip().lower()


def database_url() -> str:
    """DATABASE_URL for the app and Alembic; raises EnvironmentConfigError instead of falling back."""
    load_environment()
    shared = _read(ENV_FILE).get("DATABASE_URL", "")
    explicit = (os.environ.get("DATABASE_URL") or "").strip()
    profile = app_env()
    if profile not in LOCAL_PROFILES or not LOCAL_ENV_FILE.exists():
        if not explicit and not shared:
            raise EnvironmentConfigError(f"DATABASE_URL chưa được cấu hình trong {ENV_FILE} hoặc biến môi trường")
        return explicit or shared
    # A local database is configured. A process variable that only repeats backend/.env (for example exported there
    # by another load_dotenv) is not a local choice: this developer's machine never uses the shared database.
    if explicit and not _same_database(explicit, shared):
        return explicit
    local = _read(LOCAL_ENV_FILE).get("DATABASE_URL", "")
    if not local:
        raise EnvironmentConfigError(
            f"APP_ENV={profile} cần DATABASE_URL trong {LOCAL_ENV_FILE} hoặc biến môi trường; "
            f"không dùng DATABASE_URL của {ENV_FILE}"
        )
    if _same_database(local, shared):
        raise EnvironmentConfigError(f"DATABASE_URL trong {LOCAL_ENV_FILE} trỏ cùng database với {ENV_FILE}")
    return local


def _same_database(first: str, second: str) -> bool:
    """Same server, port, database and role (password and query ignored); unparsable URLs compare as text."""
    if not first or not second:
        return False
    try:
        a, b = make_url(first), make_url(second)
    except Exception:  # noqa: BLE001 - malformed URLs: never echo them, compare verbatim
        return first == second
    return ((a.host or "").lower(), a.port or 5432, a.database, a.username) == (
        (b.host or "").lower(), b.port or 5432, b.database, b.username)
