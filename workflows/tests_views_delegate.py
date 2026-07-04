from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class DelegateAddRemoveUUIDTests(TestCase):
    def setUp(self):
        self.actor = User.objects.create_user(
            username="actor",
            email="actor@test.com",
        )
        self.delegate = User.objects.create_user(
            username="delegate",
            email="delegate@test.com",
            first_name="Del",
            last_name="Egate",
            is_mp=True,
        )
        self.client.force_login(self.actor)

    def test_delegate_add_stores_uuid_string_in_session(self):
        response = self.client.post(
            reverse("delegate_add"),
            {"user_id": str(self.delegate.pk), "role": "Delegate"},
        )

        self.assertEqual(response.status_code, 200)

        delegates = self.client.session.get("workflow_delegates", [])
        self.assertEqual(len(delegates), 1)
        self.assertEqual(delegates[0]["user_id"], str(self.delegate.pk))
        self.assertIsInstance(delegates[0]["user_id"], str)
        self.assertEqual(delegates[0]["delegation_role"], "Delegate")

    def test_delegate_add_prevents_duplicate_uuid_delegate(self):
        payload = {"user_id": str(self.delegate.pk), "role": "Delegate"}

        first = self.client.post(reverse("delegate_add"), payload)
        second = self.client.post(reverse("delegate_add"), payload)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 400)
        self.assertContains(second, "already been added", status_code=400)

        delegates = self.client.session.get("workflow_delegates", [])
        self.assertEqual(len(delegates), 1)
        self.assertEqual(delegates[0]["user_id"], str(self.delegate.pk))

    def test_delegate_remove_removes_uuid_delegate_from_session(self):
        self.client.post(
            reverse("delegate_add"),
            {"user_id": str(self.delegate.pk), "role": "Delegate"},
        )

        response = self.client.delete(
            reverse("delegate_remove", args=[str(self.delegate.pk)])
        )

        self.assertEqual(response.status_code, 200)

        delegates = self.client.session.get("workflow_delegates", [])
        self.assertEqual(delegates, [])
