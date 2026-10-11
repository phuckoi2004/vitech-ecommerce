"""Product images use the same public visibility boundary as product details."""

import unittest
import uuid

from app.models import ProductImage
from app.services import NotFoundError, ProductImageService

from tests.fakes import Factory, FakeProductRepo, FakeRepo, FakeSession, InMemoryDB, fixed_clock


class FakeImageRepository(FakeRepo):
    model = ProductImage

    def list_by_product(self, product_id):
        return self._rows(lambda image: image.ProductId == product_id)


class ProductImageVisibilityTest(unittest.TestCase):
    def setUp(self):
        self.db = InMemoryDB()
        self.factory = Factory(self.db)
        self.service = ProductImageService(FakeSession(self.db), clock=fixed_clock)
        self.service.products = FakeProductRepo(self.db)
        self.service.images = FakeImageRepository(self.db)
        self.variant = self.factory.variant()
        self.product = self.variant.product
        self.image = self.db.add(ProductImage(ProductId=self.product.ProductId,
                                             ImageUrl="https://cdn.example.com/product.jpg"))

    def test_public_images_of_active_product_remain_visible(self):
        self.assertEqual([image.ProductImageId for image in self.service.list_images(self.product.ProductId)],
                         [self.image.ProductImageId])

    def test_public_cannot_read_images_of_hidden_or_deleted_product(self):
        for values in ({"Status": "Inactive"}, {"Status": "Active", "IsDeleted": True}):
            for name, value in values.items():
                setattr(self.product, name, value)
            with self.subTest(values=values), self.assertRaises(NotFoundError):
                self.service.list_images(self.product.ProductId)

    def test_public_cannot_read_images_of_missing_product(self):
        with self.assertRaises(NotFoundError):
            self.service.list_images(uuid.uuid4())
