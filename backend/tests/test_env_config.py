"""app.core.env: which DATABASE_URL the app and Alembic use. Fake files and URLs only; nothing connects."""

import os

import pytest

from app.core import env

SHARED = "postgresql://shared_user:shared_pw@shared-db.example.test:5432/shared"
LOCAL = "postgresql://postgres:local_pw@127.0.0.1:5432/vietech_dev"
OTHER = "postgresql://other:other_pw@127.0.0.1:5432/other_db"


@pytest.fixture
def files(tmp_path, monkeypatch):
    """Point app.core.env at temporary .env/.env.local and a clean process environment for one test."""
    for name in list(os.environ):
        if name in {"DATABASE_URL", "APP_ENV"} or name.startswith("SEPAY_"):
            monkeypatch.delenv(name)
    monkeypatch.setattr(env, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(env, "LOCAL_ENV_FILE", tmp_path / ".env.local")
    env.load_environment.cache_clear()
    yield tmp_path
    env.load_environment.cache_clear()


def write(folder, shared=None, local=None):
    if shared is not None:
        (folder / ".env").write_text(shared, encoding="utf-8")
    if local is not None:
        (folder / ".env.local").write_text(local, encoding="utf-8")


@pytest.mark.parametrize("app_env", ["development", None])
def test_without_env_local_the_shared_database_of_env_is_used(files, app_env):
    write(files, shared=f"DATABASE_URL={SHARED}\n" + (f"APP_ENV={app_env}\n" if app_env else ""))
    assert env.database_url() == SHARED
    assert "DATABASE_URL" not in os.environ  # never exported from the files


def test_env_local_database_replaces_the_shared_one(files):
    write(files, shared=f"DATABASE_URL={SHARED}\nAPP_ENV=development\n", local=f"DATABASE_URL={LOCAL}\n")
    assert env.database_url() == LOCAL


@pytest.mark.parametrize("local", ["SEPAY_BANK=MSB\n", f"DATABASE_URL={SHARED.replace('shared_pw', 'x')}\n"])
def test_env_local_without_its_own_database_never_falls_back_to_env(files, local):
    write(files, shared=f"DATABASE_URL={SHARED}\n", local=local)
    with pytest.raises(env.EnvironmentConfigError) as caught:
        env.database_url()
    assert "pw" not in str(caught.value) and "shared-db" not in str(caught.value)  # names files, never values


def test_process_variable_wins_unless_it_only_repeats_env(files, monkeypatch):
    write(files, shared=f"DATABASE_URL={SHARED}\n", local=f"DATABASE_URL={LOCAL}\n")
    monkeypatch.setenv("DATABASE_URL", OTHER)
    assert env.database_url() == OTHER
    monkeypatch.setenv("DATABASE_URL", SHARED)  # e.g. exported by another load_dotenv of backend/.env
    assert env.database_url() == LOCAL


def test_production_uses_env_even_with_env_local(files):
    write(files, shared=f"DATABASE_URL={SHARED}\nAPP_ENV=development\n", local=f"APP_ENV=production\nDATABASE_URL={LOCAL}\n")
    assert env.database_url() == SHARED


def test_missing_database_url_is_reported(files):
    write(files, shared="APP_ENV=development\n")
    with pytest.raises(env.EnvironmentConfigError):
        env.database_url()


def test_other_settings_process_then_env_local_then_env(files, monkeypatch):
    write(files, shared="SEPAY_BANK=FROM_ENV\nSEPAY_ACCOUNT_NAME=FROM_ENV\nSEPAY_PAYMENT_CODE_PREFIX=FROMENV\n",
          local="SEPAY_ACCOUNT_NAME=FROM_LOCAL\n")
    monkeypatch.setenv("SEPAY_BANK", "FROM_PROCESS")
    env.load_environment()
    assert (os.environ["SEPAY_BANK"], os.environ["SEPAY_ACCOUNT_NAME"], os.environ["SEPAY_PAYMENT_CODE_PREFIX"]) == (
        "FROM_PROCESS", "FROM_LOCAL", "FROMENV")
