"""Actor và kiểm tra role dùng chung."""

import dataclasses
import unittest
import uuid

from app.services import ADMIN_ONLY, ANY_ROLE, STAFF_OR_ADMIN, Actor, PermissionDeniedError, has_role, require_role


class ActorTest(unittest.TestCase):
    def test_only_three_business_roles_are_accepted(self):
        for role in ("Customer", "Staff", "Admin"):
            Actor(uuid.uuid4(), role)
        for role in ("SuperAdmin", "admin", "", "Root"):
            with self.subTest(role=role), self.assertRaises(ValueError):
                Actor(uuid.uuid4(), role)

    def test_user_id_must_be_uuid(self):
        with self.assertRaises(TypeError):
            Actor(str(uuid.uuid4()), "Admin")

    def test_actor_is_immutable(self):
        actor = Actor(uuid.uuid4(), "Staff")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            actor.role = "Admin"

    def test_require_role(self):
        require_role(Actor(uuid.uuid4(), "Staff"), *STAFF_OR_ADMIN)
        require_role(Actor(uuid.uuid4(), "Admin"), *ADMIN_ONLY)
        with self.assertRaises(PermissionDeniedError):
            require_role(Actor(uuid.uuid4(), "Staff"), *ADMIN_ONLY)
        with self.assertRaises(PermissionDeniedError):
            require_role(Actor(uuid.uuid4(), "Customer"), *STAFF_OR_ADMIN)

    def test_raw_user_id_or_dict_is_not_accepted_as_actor(self):
        for fake in (uuid.uuid4(), {"user_id": uuid.uuid4(), "role": "Admin"}, "Admin"):
            with self.subTest(fake=fake), self.assertRaises(TypeError):
                require_role(fake, *ADMIN_ONLY)

    def test_anonymous_caller_is_denied(self):
        with self.assertRaises(PermissionDeniedError) as ctx:
            require_role(None, *ANY_ROLE)
        self.assertEqual(ctx.exception.code, "authentication_required")

    def test_has_role(self):
        self.assertFalse(has_role(None, *STAFF_OR_ADMIN))
        self.assertTrue(has_role(Actor(uuid.uuid4(), "Staff"), *STAFF_OR_ADMIN))
        self.assertFalse(has_role(Actor(uuid.uuid4(), "Customer"), *STAFF_OR_ADMIN))
        with self.assertRaises(TypeError):
            has_role(uuid.uuid4(), *STAFF_OR_ADMIN)


if __name__ == "__main__":
    unittest.main()
