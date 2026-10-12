"""Stage 7 structure guard: every business domain keeps HTTP tests for success and each required error class.

Runs offline by parsing tests/api (AST, not text search), so docstrings or comments never count. It checks that each
test group really calls the matching assertion helper with the matching status; it does not replace running the
API tests themselves, which need PostgreSQL (tests/api/conftest.py).
"""

import ast
from pathlib import Path

API_TESTS = Path(__file__).parent / "api"
DOMAINS = ("auth", "user", "product", "cart", "order", "payment", "promotion", "purchase", "review", "warranty",
           "return", "chat", "content")
# Business rules answer 400 with a code; avatar rules answer 413/415.
BUSINESS_STATUSES = {400, 413, 415}


def _helper_calls(function: ast.FunctionDef):
    """(helper name, status) for each expect*/step call; status is the int literal passed, if any."""
    for node in ast.walk(function):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        name = node.func.id
        literals = [arg.value for arg in node.args if isinstance(arg, ast.Constant) and isinstance(arg.value, int)]
        literals += [kw.value.value for kw in node.keywords
                     if kw.arg == "status" and isinstance(kw.value, ast.Constant)]
        yield name, (literals[0] if literals else None)


def _checks(prefix: str, calls) -> bool:
    calls = list(calls)
    if prefix == "test_401_":
        return any(name == "expect_unauthorized" for name, _ in calls)
    if prefix == "test_403_":
        return any(name == "expect_forbidden" for name, _ in calls)
    if prefix == "test_422_":
        return any(name == "expect_validation" for name, _ in calls)
    if prefix in ("test_404_", "test_409_"):
        wanted = int(prefix[5:8])
        return any(name in ("expect", "step") and status == wanted for name, status in calls)
    if prefix == "test_business_rule":
        return any(name in ("expect", "step") and status in BUSINESS_STATUSES for name, status in calls)
    return any(name in ("expect", "step") and status in (200, 201, 204) for name, status in calls)  # success


def _module(domain: str) -> ast.Module:
    path = API_TESTS / f"test_{domain}_api.py"
    assert path.exists(), f"missing API tests for {domain}"
    return ast.parse(path.read_text(encoding="utf-8"))


def test_every_domain_has_success_and_each_error_class():
    prefixes = ("test_success_", "test_401_", "test_403_", "test_404_", "test_409_", "test_422_", "test_business_rule")
    gaps = {}
    for domain in DOMAINS:
        tests = [node for node in _module(domain).body
                 if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")]
        for prefix in prefixes:
            group = [test for test in tests if test.name.startswith(prefix)]
            if not any(_checks(prefix, _helper_calls(test)) for test in group):
                gaps.setdefault(domain, []).append(prefix)
    assert not gaps, f"API test matrix incomplete: {gaps}"


def test_api_tests_are_postgres_opt_in():
    for domain in DOMAINS:
        marked = [node for node in _module(domain).body if isinstance(node, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets)
                  and isinstance(node.value, ast.Name) and node.value.id == "requires_postgres"]
        assert marked, f"test_{domain}_api.py must assign pytestmark = requires_postgres"


def test_guard_ignores_docstrings_and_comments():
    fake = ast.parse('def test_404_fake(api):\n    """expect(r, 404) expect_unauthorized"""\n'
                     '    # expect(r, 404)\n    pass\n').body[0]
    assert not _checks("test_404_", _helper_calls(fake))
