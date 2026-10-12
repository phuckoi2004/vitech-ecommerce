"""Role permissions. Resource ownership is checked by each service.

Every admin function has the same five actions (`<function>:view|create|update|delete|export`).
Staff permissions mirror the role checks of the Stage 4 services (decision of 11/10/2026), plus
Staff read access to statistics. Workflow approvals (purchase approval, refund confirmation,
warranty/return approval, article publishing) stay Admin-only inside the services. They are fixed
in code: there is no screen or API that changes them.
"""

from types import MappingProxyType


_PROFILE = frozenset({"profile:read", "profile:update"})
_CUSTOMER = _PROFILE | frozenset({
    "customer.portal", "catalog:read", "wishlist:manage", "cart:manage",
    "orders:create", "orders:read_own", "orders:cancel_own",
    "services:create_own", "services:read_own", "reviews:write_own", "chat:customer",
})

ACTIONS = ("view", "create", "update", "delete", "export")
# Matrix rows, in display order (B-number = report table).
ADMIN_FUNCTIONS = (
    "products",          # B3.9–3.11 (delete: hide)
    "categories",        # B3.12
    "brands",            # B3.13
    "promotions",        # B3.14, including coupons
    "suppliers",         # B3.16
    "purchases",         # B3.17 (update: edit/resubmit, approve/reject Admin-only; delete: cancel)
    "purchase_history",  # B3.18
    "inventory",         # B3.19 (update: alert threshold)
    "shipping_methods",  # B3.21 (shipping options customers choose)
    "orders",            # B3.25–3.26, 3.29 (update: status, cancel)
    "payment_methods",   # B3.23
    "refunds",           # B3.22, 3.28 (create: perform a refund; manual confirmation Admin-only)
    "warranties",        # B3.27
    "returns",           # B3.28
    "revenue_reports",   # B3.30
    "order_reports",     # B3.31
    "reviews",           # B3.33–3.34 (delete: soft delete with reason)
    "news",              # B3.35
    "banners",           # B3.36
    "chat",              # B3.37 (create: take and reply)
)
_ALL_FUNCTIONS = frozenset(f"{name}:{action}" for name in ADMIN_FUNCTIONS for action in ACTIONS)

# Account management stays Admin-only (B3.8).
_ACCOUNTS = frozenset({"users:read", "users:manage", "users:export"})


def _grant(name: str, *actions: str) -> set[str]:
    return {f"{name}:{action}" for action in actions}


# Exports belong to Admin (decision 09/10/2026). Reviews, news and banners are Admin-only (Stage 4).
_STAFF_DEFAULT = frozenset(set().union(
    _grant("products", "view"), _grant("categories", "view"), _grant("brands", "view"),
    _grant("suppliers", "view"), _grant("purchases", "view", "create", "update", "delete"),
    _grant("purchase_history", "view"), _grant("inventory", "view"),
    _grant("shipping_methods", "view"), _grant("orders", "view", "update"),
    _grant("payment_methods", "view"), _grant("refunds", "view", "create"),
    _grant("warranties", "view", "update"), _grant("returns", "view", "update"),
    _grant("revenue_reports", "view"), _grant("order_reports", "view"),
    _grant("chat", "view", "create"),
))

ROLE_PERMISSIONS = MappingProxyType({
    "Customer": _CUSTOMER,
    "Staff": _PROFILE | {"admin.portal"} | _STAFF_DEFAULT,
    "Admin": _PROFILE | {"admin.portal"} | _ALL_FUNCTIONS | _ACCOUNTS,
})


def permissions_for(role: str) -> list[str]:
    """Return a stable menu/API permission list; unknown roles have no access."""
    return sorted(ROLE_PERMISSIONS.get(role, frozenset()))


def permission_list(role: str) -> list[str]:
    return permissions_for(role)


def has_permission(role: str, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, frozenset())
