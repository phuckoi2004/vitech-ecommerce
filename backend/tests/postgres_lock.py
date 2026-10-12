"""One PostgreSQL test run at a time on TEST_DATABASE_URL.

The PostgreSQL suites TRUNCATE tables and seed fixed codes (for example the COD payment method). Two runs on the
same test database — two terminals, or another tool re-running the suite — deadlock on TRUNCATE and see each
other's rows. Every run therefore holds a session-level advisory lock on a dedicated connection; a second run waits
for the first instead of interfering. Session-level locks need a session-mode connection (Supabase pooler port
5432 or a direct connection), which is what these suites already use.
"""

from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

# Arbitrary constant shared by every VieTech PostgreSQL test run (pg_advisory_lock key).
TEST_DATABASE_LOCK_KEY = 704_202_610
WAIT_SECONDS = 900


class BusyTestDatabase(RuntimeError):
    """Another run kept the test database for longer than WAIT_SECONDS."""


@contextmanager
def exclusive_test_database(test_url: str, *, wait_seconds: int = WAIT_SECONDS):
    engine = create_engine(test_url, poolclass=NullPool)
    connection = engine.connect()
    try:
        acquired = connection.execute(text("select pg_try_advisory_lock(:key)"),
                                      {"key": TEST_DATABASE_LOCK_KEY}).scalar()
        if not acquired:
            print(f"Another PostgreSQL test run is using TEST_DATABASE_URL; waiting up to {wait_seconds}s...",
                  flush=True)
            # Supabase roles carry a default statement_timeout (about 2 minutes) that would cut the wait short.
            connection.execute(text(f"set statement_timeout = '{int(wait_seconds)}s'"))
            connection.execute(text(f"set lock_timeout = '{int(wait_seconds)}s'"))
            try:
                connection.execute(text("select pg_advisory_lock(:key)"), {"key": TEST_DATABASE_LOCK_KEY})
            except Exception as error:  # timeout: report without connection details
                raise BusyTestDatabase(
                    "Another PostgreSQL test run kept TEST_DATABASE_URL busy; run the suites one at a time"
                ) from error
            connection.execute(text("reset lock_timeout"))
            connection.execute(text("reset statement_timeout"))
        connection.commit()
        yield
    finally:
        try:
            connection.rollback()
            connection.execute(text("select pg_advisory_unlock_all()"))
            connection.commit()
        except Exception:
            pass  # closing the session (DISCARD ALL on the pooler) releases the lock as well
        finally:
            connection.close()
            engine.dispose()
