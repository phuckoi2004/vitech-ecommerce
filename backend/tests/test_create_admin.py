"""Bootstrap guard uses a fake database and never writes to the live project."""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.cli import create_admin


def test_bootstrap_refuses_to_create_another_admin(monkeypatch, capsys):
    answers = iter(("admin@example.com", "0912345678", "Initial Admin"))
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    monkeypatch.setattr(create_admin.getpass, "getpass", lambda _: "Password1!")
    db = MagicMock()
    db.__enter__.return_value = db
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    db.scalar.return_value = uuid.uuid4()
    monkeypatch.setattr(create_admin, "SessionLocal", lambda: db)
    repository = MagicMock()
    monkeypatch.setattr(create_admin, "UserRepository", repository)

    assert create_admin.main() == 1

    db.commit.assert_not_called()
    repository.assert_not_called()
    message = capsys.readouterr().err
    assert "Hệ thống đã có Admin" in message
    assert "Password1!" not in message
