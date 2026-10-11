"""Freeze destructive-test opt-in before test collection imports app/database."""

# This import must stay independent of application modules and dotenv.
from tests.postgres_safety import POSTGRES_TESTS_ENABLED  # noqa: F401
