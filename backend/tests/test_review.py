"""ReviewService (đợt 5.2): tạo khi đơn Delivered, sửa trong 7 ngày, Admin kiểm duyệt, chỉ số sản phẩm.

Fake trong bộ nhớ: khóa dòng/UNIQUE chỉ được giả lập (db.locks, IntegrityError); không chứng minh concurrency thật
của PostgreSQL.
"""

import unittest
import uuid
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

from pydantic import ValidationError

from app.models import Product, Review, ReviewImage
from app.schemas import ReviewCreate, ReviewDeleteRequest, ReviewImageCreate, ReviewUpdate
from app.services import BusinessRuleError, ConflictError, NotFoundError, PermissionDeniedError

from tests.fakes import NOW, FakeSession, Factory, InMemoryDB, review_service


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self):
        return self.now


class ReviewTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = InMemoryDB()
        self.session = FakeSession(self.db)
        self.f = Factory(self.db)
        self.clock = Clock()
        self.svc = review_service(self.db, self.session, clock=self.clock)
        self.customer = self.f.user()
        self.other = self.f.user()
        self.staff = self.f.user("Staff")
        self.admin = self.f.user("Admin")
        self.cod = self.f.payment_method("COD")
        self.phone = self.f.variant()
        self.case = self.f.variant()
        self.product = self.phone.product
        self.order = self.f.order(self.customer, self.cod, status="Delivered", payment_status="Paid",
                                  lines=((self.phone, 1), (self.case, 1)))
        self.item = self.item_of(self.order, self.phone)

    @staticmethod
    def item_of(order, variant):
        return next(i for i in order.items if i.ProductVariantId == variant.ProductVariantId)

    def delivered_item(self, customer=None, variant=None, status="Delivered"):
        order = self.f.order(customer or self.customer, self.cod, status=status, lines=((variant or self.phone, 1),))
        return order.items[0]

    def create(self, item=None, rating=5, content="Máy tốt", by=None, images=()):
        data = ReviewCreate(OrderItemId=(item or self.item).OrderItemId, Rating=rating, Content=content,
                            Images=[ReviewImageCreate(ImageUrl=u) for u in images])
        return self.svc.create_review(self.f.actor(by or self.customer), data)

    def update(self, review_id, by=None, **values):
        return self.svc.update_review(self.f.actor(by or self.customer), review_id, ReviewUpdate(**values))

    def hide(self, review_id, by=None, reason=" Spam "):
        return self.svc.moderate_review(self.f.actor(by or self.admin), review_id, ReviewDeleteRequest(DeleteReason=reason))

    def stats(self, product=None):
        product = product or self.product
        return product.ReviewCount, product.AverageRating

    def reviews(self):
        return self.db.rows(Review)


class CreateReviewTest(ReviewTestBase):
    def test_valid_review_on_delivered_order(self):
        result = self.create(rating=4, content="  Pin tốt  ", images=("https://cdn.x/a.jpg", "https://cdn.x/b.jpg"))
        self.assertEqual((result.ProductId, result.Rating, result.Content), (self.product.ProductId, 4, "Pin tốt"))
        [review] = self.reviews()
        self.assertEqual((review.UserId, review.OrderItemId, review.IsDeleted, review.CreatedAt),
                         (self.customer.UserId, self.item.OrderItemId, False, NOW))
        self.assertEqual([(i.ImageUrl, i.DisplayOrder) for i in result.Images],
                         [("https://cdn.x/a.jpg", 0), ("https://cdn.x/b.jpg", 1)])
        self.assertEqual(self.stats(), (1, Decimal("4.00")))
        self.assertIn(("Product", self.product.ProductId), self.db.locks)

    def test_only_delivered_orders_can_be_reviewed(self):
        for status in ("Pending", "Confirmed", "Processing", "Shipping", "Completed", "Cancelled"):
            with self.subTest(status=status), self.assertRaises(BusinessRuleError) as ctx:
                self.create(self.delivered_item(status=status))
            self.assertEqual(ctx.exception.code, "review_order_not_delivered")
        self.assertEqual((self.reviews(), self.stats()), ([], (0, Decimal("0"))))

    def test_customer_must_own_the_order_item(self):
        with self.assertRaises(NotFoundError):
            self.create(self.delivered_item(customer=self.other))
        with self.assertRaises(NotFoundError) as ctx:
            self.svc.create_review(self.f.actor(self.customer),
                                   ReviewCreate(OrderItemId=uuid.uuid4(), Rating=5, Content="x"))
        self.assertEqual(ctx.exception.code, "order_item_not_found")
        with self.assertRaises(NotFoundError):  # dòng đơn của khách khác, dù đơn đó đã giao
            self.create(by=self.other)
        self.assertEqual(self.reviews(), [])

    def test_only_customers_create_reviews(self):
        for who in (self.staff, self.admin):
            with self.subTest(role=who.Role), self.assertRaises(PermissionDeniedError):
                self.create(by=who)
        with self.assertRaises(PermissionDeniedError):
            self.svc.create_review(None, ReviewCreate(OrderItemId=self.item.OrderItemId, Rating=5, Content="x"))

    def test_client_cannot_choose_owner_product_or_order(self):
        for extra in ({"UserId": str(self.other.UserId)}, {"ProductId": str(self.case.product.ProductId)},
                      {"OrderId": str(self.order.OrderId)}):
            with self.subTest(extra=extra), self.assertRaises(ValidationError):
                ReviewCreate(OrderItemId=self.item.OrderItemId, Rating=5, Content="x", **extra)
        bypass = SimpleNamespace(model_dump=lambda exclude_unset=True: {
            "OrderItemId": self.item.OrderItemId, "Rating": 5, "Content": "x", "ProductId": self.case.product.ProductId})
        with self.assertRaises(BusinessRuleError) as ctx:
            self.svc.create_review(self.f.actor(self.customer), bypass)
        self.assertEqual(ctx.exception.code, "review_field_not_allowed")
        # Sản phẩm luôn suy ra từ dòng đơn: review dòng ốp lưng gắn đúng sản phẩm ốp lưng.
        result = self.create(self.item_of(self.order, self.case))
        self.assertEqual(result.ProductId, self.case.product.ProductId)

    def test_rating_and_content_validation(self):
        for rating in (0, 6):
            with self.subTest(rating=rating), self.assertRaises(ValidationError):
                ReviewCreate(OrderItemId=self.item.OrderItemId, Rating=rating, Content="x")
        for rating in (0, 6, -1, True, 4.5, "5", None):
            bypass = SimpleNamespace(model_dump=lambda exclude_unset=True, r=rating: {
                "OrderItemId": self.item.OrderItemId, "Rating": r, "Content": "x"})
            with self.subTest(rating=rating), self.assertRaises(BusinessRuleError) as ctx:
                self.svc.create_review(self.f.actor(self.customer), bypass)
            self.assertEqual(ctx.exception.code, "invalid_rating")
        for rating in (1, 5):  # biên hợp lệ
            with self.subTest(rating=rating):
                self.assertEqual(self.create(self.delivered_item(), rating=rating).Rating, rating)
        with self.assertRaises(BusinessRuleError) as ctx:
            self.create(content="   ")
        self.assertEqual(ctx.exception.code, "review_content_required")

    def test_one_review_per_order_item_even_after_moderation(self):
        first = self.create()
        with self.assertRaises(ConflictError) as ctx:
            self.create(rating=1)
        self.assertEqual(ctx.exception.code, "review_exists")
        self.assertIn("đã được đánh giá", str(ctx.exception))  # Service tự chặn trước khi tới UNIQUE của database
        self.hide(first.ReviewId)
        with self.assertRaises(ConflictError):  # review đã ẩn vẫn chiếm OrderItem (UNIQUE gồm cả review ẩn)
            self.create(rating=1)
        self.assertEqual(len(self.reviews()), 1)

    def test_concurrent_duplicate_is_stopped_by_unique_constraint(self):
        """Yêu cầu khác vừa commit review cho cùng OrderItem sau khi yêu cầu này kiểm tra: UNIQUE chặn, rollback."""
        self.svc.reviews.exists_by_order_item = lambda order_item_id: False  # lần kiểm tra chưa thấy bản ghi kia
        self.db.add(Review(UserId=self.customer.UserId, ProductId=self.product.ProductId, OrderItemId=self.item.OrderItemId,
                           Rating=2, Content="bản ghi của yêu cầu đồng thời", IsDeleted=False, CreatedAt=NOW))
        rollbacks = self.session.rollbacks
        with self.assertRaises(ConflictError) as ctx:
            self.create(rating=5, images=("https://cdn.x/a.jpg",))
        self.assertEqual(ctx.exception.code, "review_exists")  # IntegrityError 23505 → ConflictError
        self.assertEqual((len(self.reviews()), self.db.rows(ReviewImage), self.session.rollbacks), (1, [], rollbacks + 1))


class EditReviewTest(ReviewTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.review = self.create(rating=5, content="Ban đầu")

    def test_owner_edits_within_window(self):
        self.clock.now = NOW + timedelta(days=3)
        result = self.update(self.review.ReviewId, Rating=3, Content="  Đã dùng 3 ngày  ")
        self.assertEqual((result.Rating, result.Content), (3, "Đã dùng 3 ngày"))
        self.assertEqual(self.stats(), (1, Decimal("3.00")))
        review = self.db.get(Review, self.review.ReviewId)
        self.assertEqual((review.UserId, review.ProductId, review.OrderItemId),
                         (self.customer.UserId, self.product.ProductId, self.item.OrderItemId))

    def test_content_only_edit_keeps_rating_stats(self):
        self.update(self.review.ReviewId, Content="Sửa chữ")
        self.assertEqual(self.stats(), (1, Decimal("5.00")))

    def test_other_users_cannot_edit(self):
        with self.assertRaises(NotFoundError) as ctx:
            self.update(self.review.ReviewId, by=self.other, Rating=1)
        self.assertEqual(ctx.exception.code, "review_not_found")
        for who in (self.staff, self.admin):
            with self.subTest(role=who.Role), self.assertRaises(PermissionDeniedError):
                self.update(self.review.ReviewId, by=who, Rating=1)
        self.assertEqual((self.db.get(Review, self.review.ReviewId).Rating, self.stats()), (5, (1, Decimal("5.00"))))

    def test_seven_day_window_boundaries(self):
        deadline = NOW + timedelta(days=7)
        self.clock.now = deadline - timedelta(microseconds=1)  # ngay trước hạn
        self.assertEqual(self.update(self.review.ReviewId, Rating=4).Rating, 4)
        for moment in (deadline, deadline + timedelta(seconds=1)):  # đúng tại hạn và sau hạn: hết hạn
            self.clock.now = moment
            with self.subTest(moment=moment), self.assertRaises(BusinessRuleError) as ctx:
                self.update(self.review.ReviewId, Rating=1)
            self.assertEqual(ctx.exception.code, "review_edit_window_expired")
        self.assertEqual((self.db.get(Review, self.review.ReviewId).Rating, self.stats()), (4, (1, Decimal("4.00"))))

    def test_hidden_review_cannot_be_edited_or_restored(self):
        self.hide(self.review.ReviewId)
        with self.assertRaises(BusinessRuleError) as ctx:
            self.update(self.review.ReviewId, Rating=5, Content="Khôi phục?")
        self.assertEqual(ctx.exception.code, "review_hidden")
        review = self.db.get(Review, self.review.ReviewId)
        self.assertEqual((review.IsDeleted, review.Content, self.stats()), (True, "Ban đầu", (0, Decimal("0.00"))))

    def test_owner_product_order_cannot_be_changed(self):
        for extra in ({"UserId": str(self.other.UserId)}, {"ProductId": str(uuid.uuid4())},
                      {"OrderId": str(uuid.uuid4())}, {"OrderItemId": str(uuid.uuid4())}):
            with self.subTest(extra=extra), self.assertRaises(ValidationError):
                ReviewUpdate(Rating=4, **extra)
            bypass = SimpleNamespace(model_dump=lambda exclude_unset=True, e=extra: {"Rating": 4, **e})
            with self.subTest(extra=extra, bypass=True), self.assertRaises(BusinessRuleError) as ctx:
                self.svc.update_review(self.f.actor(self.customer), self.review.ReviewId, bypass)
            self.assertEqual(ctx.exception.code, "review_field_not_allowed")
        with self.assertRaises(BusinessRuleError) as ctx:
            self.update(self.review.ReviewId)
        self.assertEqual(ctx.exception.code, "nothing_to_update")
        review = self.db.get(Review, self.review.ReviewId)
        self.assertEqual((review.UserId, review.Rating), (self.customer.UserId, 5))

    def test_locks_product_before_review(self):
        self.db.locks.clear()
        self.update(self.review.ReviewId, Rating=2)
        self.assertLess(self.db.locks.index(("Product", self.product.ProductId)),
                        self.db.locks.index(("Review", self.review.ReviewId)))


class ModerationTest(ReviewTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.five = self.create(rating=5)
        self.three = self.create(self.delivered_item(customer=self.other), rating=3, by=self.other)

    def test_admin_hides_review_with_audit_and_stats_exclude_it(self):
        self.assertEqual(self.stats(), (2, Decimal("4.00")))
        self.clock.now = NOW + timedelta(hours=2)
        result = self.hide(self.five.ReviewId)
        self.assertEqual((result.IsDeleted, result.DeletedByUserId, result.DeletedAt, result.DeleteReason),
                         (True, self.admin.UserId, NOW + timedelta(hours=2), "Spam"))
        self.assertEqual(self.stats(), (1, Decimal("3.00")))
        self.assertIsNotNone(self.db.get(Review, self.five.ReviewId))  # không xóa dòng
        public = self.svc.list_product_reviews(self.product.ProductId)
        self.assertEqual(([r.ReviewId for r in public.Items], public.Total), ([self.three.ReviewId], 1))
        admin_view = self.svc.admin_list_product_reviews(self.f.actor(self.admin), self.product.ProductId)
        self.assertEqual(admin_view.Total, 2)
        self.assertEqual(self.svc.list_my_reviews(self.f.actor(self.customer)).Total, 0)

    def test_customer_and_staff_cannot_moderate(self):
        for who in (self.customer, self.staff, self.other):
            with self.subTest(role=who.Role), self.assertRaises(PermissionDeniedError):
                self.hide(self.five.ReviewId, by=who)
        with self.assertRaises(PermissionDeniedError):
            self.svc.moderate_review(None, self.five.ReviewId, ReviewDeleteRequest())
        self.assertFalse(self.db.get(Review, self.five.ReviewId).IsDeleted)
        self.assertFalse(hasattr(self.svc, "delete_review"))  # không có nghiệp vụ khách hàng tự xóa

    def test_repeated_moderation_does_not_count_twice(self):
        self.hide(self.five.ReviewId)
        first = self.db.get(Review, self.five.ReviewId)
        audit = (first.DeletedByUserId, first.DeletedAt, first.DeleteReason)
        self.clock.now = NOW + timedelta(days=1)
        with self.assertRaises(BusinessRuleError) as ctx:
            self.hide(self.five.ReviewId, reason="Lần 2")
        self.assertEqual(ctx.exception.code, "review_already_hidden")
        self.assertEqual((first.DeletedByUserId, first.DeletedAt, first.DeleteReason), audit)
        self.assertEqual(self.stats(), (1, Decimal("3.00")))

    def test_moderation_failure_rolls_back(self):
        def broken(product_id):
            raise RuntimeError("không tính được chỉ số")

        self.svc.reviews.rating_summary = broken
        with self.assertRaises(RuntimeError):
            self.hide(self.five.ReviewId)
        review = self.db.get(Review, self.five.ReviewId)
        self.assertEqual((review.IsDeleted, review.DeletedByUserId, review.DeletedAt), (False, None, None))
        self.assertEqual(self.stats(), (2, Decimal("4.00")))

    def test_unknown_review(self):
        with self.assertRaises(NotFoundError):
            self.hide(uuid.uuid4())
        with self.assertRaises(NotFoundError):
            self.svc.admin_get_review(self.f.actor(self.admin), uuid.uuid4())
        with self.assertRaises(PermissionDeniedError):
            self.svc.admin_get_review(self.f.actor(self.staff), self.five.ReviewId)


class ProductStatsTest(ReviewTestBase):
    def test_average_over_many_reviews_with_rounding(self):
        for rating, expected in ((5, (1, "5.00")), (4, (2, "4.50")), (4, (3, "4.33")), (5, (4, "4.50"))):
            self.create(self.delivered_item(), rating=rating)
            self.assertEqual(self.stats(), (expected[0], Decimal(expected[1])))
        product_two = self.f.variant()
        for rating in (5, 5, 4):  # 14/3 = 4.666… → 4.67 (ROUND_HALF_UP)
            self.create(self.delivered_item(variant=product_two), rating=rating)
        self.assertEqual(self.stats(product_two.product), (3, Decimal("4.67")))
        self.assertEqual(self.stats(), (4, Decimal("4.50")))  # sản phẩm khác không bị ảnh hưởng

    def test_no_visible_review_resets_to_zero(self):
        review = self.create(rating=2)
        self.hide(review.ReviewId)
        self.assertEqual(self.stats(), (0, Decimal("0.00")))

    def test_stats_are_recomputed_from_data_not_incremented(self):
        """Giả lập số liệu bị lệch (ví dụ ghi đè bởi thao tác đồng thời cũ): lần cập nhật sau tính lại đúng từ dữ liệu."""
        self.create(rating=5)
        product = self.db.get(Product, self.product.ProductId)
        product.ReviewCount, product.AverageRating = 99, Decimal("1.00")
        self.create(self.delivered_item(), rating=3)
        self.assertEqual(self.stats(), (2, Decimal("4.00")))

    def test_sequential_concurrent_like_creates_on_same_product_are_consistent(self):
        """Các yêu cầu cùng sản phẩm được tuần tự hóa bằng khóa Product; mỗi lần tính lại thấy đủ review đã commit."""
        customers = [self.f.user() for _ in range(5)]
        for index, who in enumerate(customers):
            self.create(self.delivered_item(customer=who), rating=index + 1, by=who)  # 1..5
        self.assertEqual(self.stats(), (5, Decimal("3.00")))
        self.assertEqual(sum(1 for name, key in self.db.locks if (name, key) == ("Product", self.product.ProductId)), 5)


class IntegrityTest(ReviewTestBase):
    def test_failure_while_saving_images_leaves_nothing(self):
        def broken(values):
            raise RuntimeError("lưu ảnh lỗi")

        self.svc.images.create = broken
        with self.assertRaises(RuntimeError):
            self.create(images=("https://cdn.x/a.jpg",))
        self.assertEqual((self.reviews(), self.stats()), ([], (0, Decimal("0"))))

    def test_public_listing_filters_and_validation(self):
        self.create(rating=5)
        self.create(self.delivered_item(), rating=3)
        self.assertEqual(self.svc.list_product_reviews(self.product.ProductId, rating=3).Total, 1)
        with self.assertRaises(BusinessRuleError) as ctx:
            self.svc.list_product_reviews(self.product.ProductId, rating=6)
        self.assertEqual(ctx.exception.code, "invalid_rating")
        with self.assertRaises(BusinessRuleError) as ctx:
            self.svc.list_product_reviews(self.product.ProductId, page=0)
        self.assertEqual(ctx.exception.code, "invalid_pagination")
        with self.assertRaises(PermissionDeniedError):
            self.svc.list_my_reviews(self.f.actor(self.staff))
        with self.assertRaises(PermissionDeniedError):
            self.svc.admin_list_product_reviews(self.f.actor(self.customer), self.product.ProductId)


if __name__ == "__main__":
    unittest.main()
