"""Freeze destructive-test opt-in before test collection imports app/database."""

# This import must stay independent of application modules and dotenv.
from tests.postgres_safety import POSTGRES_TESTS_ENABLED  # noqa: F401

import os
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def postgres_test_lock():
    """Exclusive use of TEST_DATABASE_URL for this run (tests/postgres_lock.py).

    Request it with ``request.getfixturevalue`` only after the offline database guard has passed; the guard
    (require_test_database_target) runs again here before the first connection is opened.
    """
    from dotenv import dotenv_values

    from tests.postgres_lock import BusyTestDatabase, exclusive_test_database
    from tests.postgres_safety import UnsafePostgresTestDatabase, require_test_database_target

    env = dotenv_values(Path(__file__).resolve().parents[1] / ".env")
    test_url = (os.getenv("TEST_DATABASE_URL") or env.get("TEST_DATABASE_URL") or "").strip()
    main_url = (os.getenv("DATABASE_URL") or env.get("DATABASE_URL") or "").strip()
    expected = (os.getenv("TEST_DATABASE_PROJECT_REF") or env.get("TEST_DATABASE_PROJECT_REF") or "").strip()
    try:
        require_test_database_target(test_url, main_url, expected_project=expected, environ=os.environ)
        with exclusive_test_database(test_url):
            yield
    except (UnsafePostgresTestDatabase, BusyTestDatabase) as error:
        pytest.fail(str(error), pytrace=False)
