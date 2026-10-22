"""Verify the PostgreSQL migration offline; never loads Alembic's database environment."""

from io import StringIO

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex

from app.models import Message
from tests.test_migration_graph import scripts


def test_ai_migration_indexes_match_models_and_do_not_modify_history():
    module = scripts().get_revision("d7a1e5c9b304").module
    output = StringIO()
    context = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output})
    with Operations.context(context):
        module.upgrade()
    sql = output.getvalue()
    assert sql.count("CREATE UNIQUE INDEX") == 3
    assert "DELETE" not in sql and "UPDATE" not in sql and "ALTER TABLE" not in sql
    for index in Message.__table__.indexes:
        if index.name.startswith("UX_Messages_Ai"):
            assert str(CreateIndex(index).compile(dialect=postgresql.dialect())).strip() + ";" in sql
    output.seek(0)
    output.truncate(0)
    with Operations.context(context):
        module.downgrade()
    assert output.getvalue().count("DROP INDEX") == 3
