"""ContentService (đợt 5.5): tin tức (Draft/Published/Hidden) và banner (IsActive + khung hiển thị).

Fake trong bộ nhớ: UNIQUE Slug, khóa dòng chỉ được giả lập (IntegrityError, db.locks); không chứng minh truy vấn hay
concurrency thật của PostgreSQL.
"""

import unittest
import uuid
from datetime import datetime, timedelta

from pydantic import ValidationError

import app.schemas
from app.models import Banner, NewsArticle
from app.schemas import BannerCreate, BannerUpdate, NewsArticleCreate, NewsArticleUpdate
from app.services import BusinessRuleError, ConflictError, NotFoundError, PermissionDeniedError

from tests.fakes import NOW, Factory, FakeSession, InMemoryDB, content_service
from tests.test_chat import bypass


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self):
        return self.now


class ContentTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = InMemoryDB()
        self.session = FakeSession(self.db)
        self.f = Factory(self.db)
        self.clock = Clock()
        self.svc = content_service(self.db, self.session, clock=self.clock)
        self.admin = self.f.user("Admin")
        self.staff = self.f.user("Staff")
        self.customer = self.f.user()

    def a(self, user):
        return self.f.actor(user)

    def article(self, slug="ra-mat-iphone", title="Ra mắt iPhone", content="Nội dung", **extra):
        data = NewsArticleCreate(Title=title, Slug=slug, Content=content, **extra)
        return self.svc.create_article(self.a(self.admin), data)

    def published(self, slug, at=None):
        if at is not None:
            self.clock.now = at
        article = self.article(slug=slug)
        return self.svc.publish_article(self.a(self.admin), article.NewsArticleId)

    def banner(self, title="Khuyến mãi", image="https://cdn.vietech.vn/b.jpg", **extra):
        return self.svc.create_banner(self.a(self.admin), BannerCreate(Title=title, ImageUrl=image, **extra))

    def assert_error(self, error, code, call):
        with self.assertRaises(error) as ctx:
            call()
        self.assertEqual(ctx.exception.code, code)
        return ctx.exception


class ArticleTest(ContentTestBase):
    def test_admin_creates_draft_with_server_fields(self):
        result = self.article(title="  Ra mắt iPhone  ", slug=" ra-mat-iphone ", content=" Bài viết ", Summary="  ",
                              ThumbnailUrl="https://cdn.vietech.vn/t.jpg")
        self.assertEqual((result.Status, result.PublishedAt, result.CreatedByUserId, result.CreatedAt),
                         ("Draft", None, self.admin.UserId, NOW))
        self.assertEqual((result.Title, result.Slug, result.Content, result.Summary),
                         ("Ra mắt iPhone", "ra-mat-iphone", "Bài viết", None))
        self.assertEqual(self.session.commits, 1)

    def test_client_cannot_set_status_or_admin_fields(self):
        with self.assertRaises(ValidationError):
            NewsArticleCreate(Title="T", Slug="s", Content="C", Status="Published")
        with self.assertRaises(ValidationError):
            NewsArticleUpdate(Status="Published")
        base = {"Title": "T", "Slug": "s", "Content": "C"}
        for extra in ({"Status": "Published"}, {"PublishedAt": NOW}, {"CreatedByUserId": self.staff.UserId}):
            with self.subTest(extra=extra):
                self.assert_error(BusinessRuleError, "article_field_not_allowed",
                                  lambda e=extra: self.svc.create_article(self.a(self.admin), bypass({**base, **e})))
        article = self.article()
        self.assert_error(BusinessRuleError, "article_field_not_allowed", lambda: self.svc.update_article(
            self.a(self.admin), article.NewsArticleId, bypass({"Status": "Published"})))
        self.assertEqual(self.db.get(NewsArticle, article.NewsArticleId).Status, "Draft")
        self.assertEqual(len(self.db.rows(NewsArticle)), 1)

    def test_input_validation(self):
        cases = [
            ({"Title": "  "}, "article_title_required"),
            ({"Content": " \n "}, "article_content_required"),
            ({"Slug": "   "}, "invalid_slug"),
            ({"Slug": "ra mat"}, "invalid_slug"),
            ({"ThumbnailUrl": "http://cdn.vietech.vn/t.jpg"}, "invalid_thumbnail_url"),
            ({"ThumbnailUrl": "javascript:alert(1)"}, "invalid_thumbnail_url"),
        ]
        for change, code in cases:
            with self.subTest(code=code, change=change):
                values = {"Title": "T", "Slug": "s", "Content": "C", **change}
                self.assert_error(BusinessRuleError, code,
                                  lambda v=values: self.svc.create_article(self.a(self.admin), NewsArticleCreate(**v)))
        with self.assertRaises(ValidationError):
            NewsArticleCreate(Title="T" * 256, Slug="s", Content="C")
        self.assertEqual(self.db.rows(NewsArticle), [])

    def test_slug_must_be_unique_including_database_race(self):
        first = self.article()
        error = self.assert_error(ConflictError, "news_article_slug_exists", lambda: self.article(title="Khác"))
        self.assertIn("Slug bài viết đã tồn tại", str(error))  # Service kiểm tra trước, không chờ UNIQUE của database
        other = self.article(slug="bai-khac")
        self.assert_error(ConflictError, "news_article_slug_exists", lambda: self.svc.update_article(
            self.a(self.admin), other.NewsArticleId, NewsArticleUpdate(Slug="ra-mat-iphone")))
        self.svc.articles.exists_by_slug = lambda slug, exclude_id=None: False  # yêu cầu đồng thời chưa commit
        rollbacks = self.session.rollbacks
        self.assert_error(ConflictError, "news_article_slug_exists", lambda: self.article(title="Trùng"))
        self.assertEqual(self.session.rollbacks, rollbacks + 1)
        self.assertEqual(sorted(a.Slug for a in self.db.rows(NewsArticle)), ["bai-khac", "ra-mat-iphone"])
        self.assertEqual(self.db.get(NewsArticle, first.NewsArticleId).Title, "Ra mắt iPhone")

    def test_publish_hide_and_republish(self):
        article = self.article()
        rid = article.NewsArticleId
        self.clock.now = NOW + timedelta(hours=1)
        published = self.svc.publish_article(self.a(self.admin), rid)
        self.assertEqual((published.Status, published.PublishedAt), ("Published", NOW + timedelta(hours=1)))
        self.assert_error(BusinessRuleError, "invalid_article_transition",
                          lambda: self.svc.publish_article(self.a(self.admin), rid))
        self.clock.now = NOW + timedelta(days=1)
        hidden = self.svc.hide_article(self.a(self.admin), rid)
        self.assertEqual((hidden.Status, hidden.PublishedAt), ("Hidden", NOW + timedelta(hours=1)))
        self.assert_error(BusinessRuleError, "invalid_article_transition",
                          lambda: self.svc.hide_article(self.a(self.admin), rid))
        again = self.svc.publish_article(self.a(self.admin), rid)
        self.assertEqual((again.Status, again.PublishedAt), ("Published", NOW + timedelta(hours=1)))  # giữ lần đăng đầu
        draft = self.article(slug="nhap")
        self.assert_error(BusinessRuleError, "invalid_article_transition",
                          lambda: self.svc.hide_article(self.a(self.admin), draft.NewsArticleId))

    def test_update_content_keeps_status_and_published_at(self):
        article = self.published("tin-moi")
        updated = self.svc.update_article(self.a(self.admin), article.NewsArticleId,
                                          NewsArticleUpdate(Title="Tiêu đề mới", Summary=" Tóm tắt ", ThumbnailUrl=None))
        self.assertEqual((updated.Title, updated.Summary, updated.ThumbnailUrl, updated.Status, updated.PublishedAt),
                         ("Tiêu đề mới", "Tóm tắt", None, "Published", NOW))
        self.assert_error(BusinessRuleError, "nothing_to_update", lambda: self.svc.update_article(
            self.a(self.admin), article.NewsArticleId, NewsArticleUpdate()))
        with self.assertRaises(ValidationError):
            NewsArticleUpdate(Title=None)  # cột NOT NULL
        same = self.svc.update_article(self.a(self.admin), article.NewsArticleId, NewsArticleUpdate(Slug="tin-moi"))
        self.assertEqual(same.Slug, "tin-moi")  # giữ nguyên slug của chính nó không bị coi là trùng

    def test_public_sees_only_published_articles(self):
        old = self.published("cu", at=NOW)
        new = self.published("moi", at=NOW + timedelta(days=2))
        hidden = self.published("an", at=NOW + timedelta(days=1))
        self.svc.hide_article(self.a(self.admin), hidden.NewsArticleId)
        draft = self.article(slug="nhap")
        page = self.svc.list_published_articles()
        self.assertEqual([a.Slug for a in page.Items], ["moi", "cu"])
        self.assertEqual(page.Total, 2)
        self.assertFalse(hasattr(page.Items[0], "Content"))
        self.assertEqual(self.svc.get_published_article("moi").NewsArticleId, new.NewsArticleId)
        for slug in ("an", "nhap", "khong-co", None):
            with self.subTest(slug=slug):
                self.assert_error(NotFoundError, "news_article_not_found", lambda s=slug: self.svc.get_published_article(s))
        second_page = self.svc.list_published_articles(page=2, page_size=1)
        self.assertEqual([a.Slug for a in second_page.Items], ["cu"])
        self.assert_error(BusinessRuleError, "invalid_pagination", lambda: self.svc.list_published_articles(page=0))
        self.assertEqual(old.Status, "Published")
        self.assertEqual(self.db.get(NewsArticle, draft.NewsArticleId).Status, "Draft")

    def test_admin_lists_and_reads_every_status(self):
        self.article(slug="nhap")
        self.published("dang")
        admin = self.a(self.admin)
        self.assertEqual(self.svc.admin_list_articles(admin).Total, 2)
        self.assertEqual([a.Slug for a in self.svc.admin_list_articles(admin, status="Draft").Items], ["nhap"])
        self.assert_error(BusinessRuleError, "invalid_article_status",
                          lambda: self.svc.admin_list_articles(admin, status="Archived"))
        draft = self.db.rows(NewsArticle)[0]
        self.assertEqual(self.svc.admin_get_article(admin, draft.NewsArticleId).CreatedByUserId, self.admin.UserId)

    def test_missing_article_is_not_found(self):
        missing = uuid.uuid4()
        admin = self.a(self.admin)
        for call in (lambda: self.svc.admin_get_article(admin, missing),
                     lambda: self.svc.update_article(admin, missing, NewsArticleUpdate(Title="x")),
                     lambda: self.svc.publish_article(admin, missing),
                     lambda: self.svc.hide_article(admin, missing)):
            self.assert_error(NotFoundError, "news_article_not_found", call)

    def test_only_admin_manages_articles(self):
        article = self.article()
        rid = article.NewsArticleId
        calls = [
            lambda a: self.svc.create_article(a, NewsArticleCreate(Title="T", Slug="x", Content="C")),
            lambda a: self.svc.update_article(a, rid, NewsArticleUpdate(Title="x")),
            lambda a: self.svc.publish_article(a, rid),
            lambda a: self.svc.hide_article(a, rid),
            lambda a: self.svc.admin_list_articles(a),
            lambda a: self.svc.admin_get_article(a, rid),
        ]
        for user in (self.staff, self.customer):
            for index, call in enumerate(calls):
                with self.subTest(role=user.Role, call=index):
                    self.assert_error(PermissionDeniedError, "permission_denied", lambda c=call, u=user: c(self.a(u)))
        self.assert_error(PermissionDeniedError, "authentication_required", lambda: self.svc.publish_article(None, rid))
        self.assertEqual((self.db.get(NewsArticle, rid).Status, len(self.db.rows(NewsArticle))), ("Draft", 1))

    def test_status_change_locks_the_row(self):
        article = self.article()
        self.db.locks.clear()
        self.svc.publish_article(self.a(self.admin), article.NewsArticleId)
        self.assertEqual(self.db.locks, [("NewsArticle", article.NewsArticleId)])


class BannerTest(ContentTestBase):
    def test_admin_creates_banner_active_by_default(self):
        result = self.banner(LinkUrl="/khuyen-mai/thang-10", DisplayOrder=2,
                             StartDate=NOW, EndDate=NOW + timedelta(days=7))
        self.assertEqual((result.IsActive, result.CreatedByUserId, result.CreatedAt, result.DisplayOrder, result.LinkUrl),
                         (True, self.admin.UserId, NOW, 2, "/khuyen-mai/thang-10"))
        self.assertEqual(self.banner(title="Mặc định").DisplayOrder, 0)

    def test_client_cannot_set_active_or_admin_fields(self):
        with self.assertRaises(ValidationError):
            BannerCreate(Title="T", ImageUrl="https://cdn.vietech.vn/b.jpg", IsActive=False)
        with self.assertRaises(ValidationError):
            BannerUpdate(IsActive=True)
        base = {"Title": "T", "ImageUrl": "https://cdn.vietech.vn/b.jpg"}
        for extra in ({"IsActive": False}, {"CreatedByUserId": self.staff.UserId}, {"CreatedAt": NOW}):
            with self.subTest(extra=extra):
                self.assert_error(BusinessRuleError, "banner_field_not_allowed",
                                  lambda e=extra: self.svc.create_banner(self.a(self.admin), bypass({**base, **e})))
        self.assertEqual(self.db.rows(Banner), [])

    def test_url_and_order_validation(self):
        cases = [
            ({"ImageUrl": "http://cdn.vietech.vn/b.jpg"}, "invalid_banner_image_url"),
            ({"ImageUrl": "data:image/png;base64,AAAA"}, "invalid_banner_image_url"),
            ({"LinkUrl": "javascript:alert(1)"}, "invalid_banner_link_url"),
            ({"LinkUrl": "//evil.example/x"}, "invalid_banner_link_url"),
            ({"LinkUrl": "http://vietech.vn"}, "invalid_banner_link_url"),
            ({"LinkUrl": "/khuyen mai"}, "invalid_banner_link_url"),
            ({"Title": "  "}, "banner_title_required"),
        ]
        for change, code in cases:
            with self.subTest(code=code, change=change):
                values = {"Title": "T", "ImageUrl": "https://cdn.vietech.vn/b.jpg", **change}
                self.assert_error(BusinessRuleError, code,
                                  lambda v=values: self.svc.create_banner(self.a(self.admin), BannerCreate(**v)))
        self.assert_error(BusinessRuleError, "invalid_display_order", lambda: self.svc.create_banner(
            self.a(self.admin), bypass({"Title": "T", "ImageUrl": "https://cdn.vietech.vn/b.jpg", "DisplayOrder": True})))
        self.assertEqual(self.banner(LinkUrl="https://vietech.vn/sale").LinkUrl, "https://vietech.vn/sale")
        self.assertEqual(len(self.db.rows(Banner)), 1)

    def test_display_period_is_validated_against_stored_values(self):
        with self.assertRaises(ValidationError):
            BannerCreate(Title="T", ImageUrl="https://cdn.vietech.vn/b.jpg", StartDate=NOW, EndDate=NOW - timedelta(1))
        self.assert_error(BusinessRuleError, "invalid_banner_period", lambda: self.banner(StartDate=datetime(2026, 10, 9)))
        self.assert_error(BusinessRuleError, "invalid_banner_period", lambda: self.svc.create_banner(
            self.a(self.admin), bypass({"Title": "T", "ImageUrl": "https://cdn.vietech.vn/b.jpg",
                                        "StartDate": NOW, "EndDate": NOW - timedelta(days=1)})))
        banner = self.banner(StartDate=NOW, EndDate=NOW + timedelta(days=7))
        self.assert_error(BusinessRuleError, "invalid_banner_period", lambda: self.svc.update_banner(
            self.a(self.admin), banner.BannerId, BannerUpdate(EndDate=NOW - timedelta(days=1))))
        stored = self.db.get(Banner, banner.BannerId)
        self.assertEqual(stored.EndDate, NOW + timedelta(days=7))
        same_moment = self.svc.update_banner(self.a(self.admin), banner.BannerId, BannerUpdate(EndDate=NOW))
        self.assertEqual(same_moment.EndDate, NOW)  # EndDate = StartDate hợp lệ (CHECK >=)
        cleared = self.svc.update_banner(self.a(self.admin), banner.BannerId, BannerUpdate(StartDate=None, EndDate=None))
        self.assertEqual((cleared.StartDate, cleared.EndDate), (None, None))
        self.assert_error(BusinessRuleError, "nothing_to_update",
                          lambda: self.svc.update_banner(self.a(self.admin), banner.BannerId, BannerUpdate()))

    def test_public_sees_only_active_banners_inside_their_window(self):
        always = self.banner(title="Luôn", DisplayOrder=3)
        window = self.banner(title="Khung", DisplayOrder=1, StartDate=NOW + timedelta(hours=1),
                             EndDate=NOW + timedelta(hours=2))
        self.banner(title="Hết hạn", EndDate=NOW - timedelta(seconds=1))
        inactive = self.banner(title="Đã ngừng", DisplayOrder=0)
        self.svc.deactivate_banner(self.a(self.admin), inactive.BannerId)
        cases = [
            (NOW, ["Luôn"]),
            (NOW + timedelta(hours=1), ["Khung", "Luôn"]),  # đúng thời điểm bắt đầu: hiển thị
            (NOW + timedelta(hours=2), ["Khung", "Luôn"]),  # đúng thời điểm kết thúc: hiển thị
            (NOW + timedelta(hours=2, seconds=1), ["Luôn"]),
        ]
        for at, expected in cases:
            with self.subTest(at=at):
                self.clock.now = at
                self.assertEqual([b.Title for b in self.svc.list_display_banners()], expected)
        self.assertEqual(always.IsActive, True)
        self.assertEqual(window.DisplayOrder, 1)

    def test_activate_and_deactivate(self):
        banner = self.banner()
        rid = banner.BannerId
        self.assertEqual(self.svc.deactivate_banner(self.a(self.admin), rid).IsActive, False)
        self.assert_error(BusinessRuleError, "banner_status_unchanged",
                          lambda: self.svc.deactivate_banner(self.a(self.admin), rid))
        self.assertEqual(self.svc.activate_banner(self.a(self.admin), rid).IsActive, True)
        self.assert_error(BusinessRuleError, "banner_status_unchanged",
                          lambda: self.svc.activate_banner(self.a(self.admin), rid))
        self.assertEqual([b.BannerId for b in self.svc.admin_list_banners(self.a(self.admin), is_active=True)], [rid])
        self.assertEqual(self.svc.admin_list_banners(self.a(self.admin), is_active=False), [])

    def test_missing_banner_and_permissions(self):
        missing = uuid.uuid4()
        admin = self.a(self.admin)
        for call in (lambda: self.svc.admin_get_banner(admin, missing),
                     lambda: self.svc.update_banner(admin, missing, BannerUpdate(Title="x")),
                     lambda: self.svc.activate_banner(admin, missing),
                     lambda: self.svc.deactivate_banner(admin, missing)):
            self.assert_error(NotFoundError, "banner_not_found", call)
        rid = self.banner().BannerId
        calls = [
            lambda a: self.svc.create_banner(a, BannerCreate(Title="T", ImageUrl="https://cdn.vietech.vn/b.jpg")),
            lambda a: self.svc.update_banner(a, rid, BannerUpdate(Title="x")),
            lambda a: self.svc.activate_banner(a, rid),
            lambda a: self.svc.deactivate_banner(a, rid),
            lambda a: self.svc.admin_list_banners(a),
            lambda a: self.svc.admin_get_banner(a, rid),
        ]
        for user in (self.staff, self.customer):
            for index, call in enumerate(calls):
                with self.subTest(role=user.Role, call=index):
                    self.assert_error(PermissionDeniedError, "permission_denied", lambda c=call, u=user: c(self.a(u)))
        self.assertEqual((len(self.db.rows(Banner)), self.db.get(Banner, rid).Title), (1, "Khuyến mãi"))

    def test_failure_rolls_back_banner_update(self):
        banner = self.banner()

        def fail(*args, **kwargs):
            raise RuntimeError("lỗi giữa chừng")

        original_flush = self.svc.banners.flush
        self.svc.banners.flush = fail
        with self.assertRaises(RuntimeError):
            self.svc.update_banner(self.a(self.admin), banner.BannerId, BannerUpdate(Title="Mới", DisplayOrder=5))
        self.svc.banners.flush = original_flush
        stored = self.db.get(Banner, banner.BannerId)
        self.assertEqual((stored.Title, stored.DisplayOrder), ("Khuyến mãi", 0))
        self.assertEqual(self.session.events[-1], "rollback")


class ContentSchemaTest(unittest.TestCase):
    def test_content_schemas_exported_without_status_inputs(self):
        self.assertIn("AdminNewsArticleSummary", app.schemas.__all__)
        self.assertNotIn("Status", NewsArticleCreate.model_fields)
        self.assertNotIn("Status", NewsArticleUpdate.model_fields)
        self.assertNotIn("IsActive", BannerCreate.model_fields)
        self.assertNotIn("IsActive", BannerUpdate.model_fields)


if __name__ == "__main__":
    unittest.main()
