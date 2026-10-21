"""API tests — Content: news articles and banners (Admin manages, the public sees published/active items)."""

from datetime import datetime, timedelta, timezone

from .support import (
    expect,
    expect_forbidden,
    expect_unauthorized,
    expect_validation,
    random_id,
    requires_postgres,
    tag,
)

pytestmark = requires_postgres


def article(api, admin, slug=None):
    return api.client.post("/admin/news", headers=admin.headers, json={
        "Title": "Ra mắt điện thoại mới", "Slug": slug or f"ra-mat-{tag()}", "Content": "Nội dung bài viết"})


def banner(api, person, **overrides):
    return api.client.post("/admin/banners", headers=person.headers, json={
        "Title": "Khuyến mãi", "ImageUrl": "https://cdn.example.com/banner.jpg", **overrides})


def test_success_news_and_banners(api, admin):
    client = api.client
    created = expect(article(api, admin), 201)
    slug, article_id = created["Slug"], created["NewsArticleId"]
    expect(client.get(f"/news/{slug}"), 404)  # drafts are not public
    expect(client.post(f"/admin/news/{article_id}/publish", headers=admin.headers), 200)
    assert expect(client.get(f"/news/{slug}"), 200)["Title"] == "Ra mắt điện thoại mới"
    assert slug in [a["Slug"] for a in expect(client.get("/news"), 200)["Items"]]
    expect(client.post(f"/admin/news/{article_id}/hide", headers=admin.headers), 200)
    expect(client.get(f"/news/{slug}"), 404)

    shown = expect(banner(api, admin), 201)
    assert shown["BannerId"] in [b["BannerId"] for b in expect(client.get("/banners"), 200)]
    expect(client.post(f"/admin/banners/{shown['BannerId']}/deactivate", headers=admin.headers), 200)
    assert shown["BannerId"] not in [b["BannerId"] for b in expect(client.get("/banners"), 200)]


def test_401_without_token(api):
    expect_unauthorized(api.client.post("/admin/news", json={"Title": "x", "Slug": "x", "Content": "x"}))
    expect_unauthorized(api.client.post("/admin/banners", json={"Title": "x", "ImageUrl": "https://a.example/x.jpg"}))
    expect_unauthorized(api.client.get("/admin/news"))


def test_403_customers_are_denied_while_internal_roles_manage_content(api, admin, staff, customer):
    article_id = expect(article(api, admin), 201)["NewsArticleId"]
    expect(article(api, staff), 201)
    expect(api.client.post(f"/admin/news/{article_id}/publish", headers=staff.headers), 200)
    expect(banner(api, staff), 201)
    expect_forbidden(api.client.get("/admin/news", headers=customer.headers))


def test_404_unknown_content(api, admin):
    expect(api.client.get("/news/khong-ton-tai"), 404)
    expect(api.client.post(f"/admin/news/{random_id()}/publish", headers=admin.headers), 404)
    expect(api.client.patch(f"/admin/banners/{random_id()}", headers=admin.headers, json={"Title": "x"}), 404)


def test_409_duplicate_article_slug(api, admin):
    slug = f"bai-viet-{tag()}"
    expect(article(api, admin, slug), 201)
    expect(article(api, admin, slug), 409, "news_article_slug_exists")


def test_422_validation(api, admin):
    expect_validation(api.client.post("/admin/news", headers=admin.headers, json={"Title": "x", "Slug": "x"}),
                      "Content")
    expect_validation(api.client.post("/admin/banners", headers=admin.headers, json={"Title": "x"}), "ImageUrl")
    expect_validation(banner(api, admin, DisplayOrder="first"), "DisplayOrder")
    expect_validation(banner(api, admin, StartDate="ngày mai"), "StartDate")
    now = datetime.now(timezone.utc)
    expect_validation(banner(api, admin, StartDate=now.isoformat(),
                             EndDate=(now - timedelta(days=1)).isoformat()))  # period checked by the schema


def test_business_rules_content(api, admin):
    article_id = expect(article(api, admin), 201)["NewsArticleId"]
    expect(api.client.post(f"/admin/news/{article_id}/publish", headers=admin.headers), 200)
    expect(api.client.post(f"/admin/news/{article_id}/publish", headers=admin.headers), 400,
           "invalid_article_transition")
    expect(article(api, admin, "Có Dấu Và Khoảng Trắng"), 400, "invalid_slug")
    shown = expect(banner(api, admin), 201)
    expect(api.client.post(f"/admin/banners/{shown['BannerId']}/activate", headers=admin.headers), 400,
           "banner_status_unchanged")
