import os
import tempfile
import unittest

_tmp_dir = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_dir.name}/test.db"
os.environ["AUTH_SECRET_KEY"] = "test-secret"

from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402


class AuthFlowTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        _tmp_dir.cleanup()

    def setUp(self):
        self.client = TestClient(app)

    def test_signup_requires_verification_before_search(self):
        response = self.client.post("/api/auth/signup", json={"email": "person@example.com", "password": "supersecret1"})
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.json()["is_verified"])

        login = self.client.post("/api/auth/login", json={"email": "person@example.com", "password": "supersecret1"})
        self.assertEqual(login.status_code, 200)

        me = self.client.get("/api/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["email"], "person@example.com")

        search = self.client.post("/api/search", files={"resume": ("cv.txt", b"Java developer", "text/plain")})
        self.assertEqual(search.status_code, 403)

    def test_duplicate_signup_rejected(self):
        self.client.post("/api/auth/signup", json={"email": "dup@example.com", "password": "supersecret1"})
        second = self.client.post("/api/auth/signup", json={"email": "dup@example.com", "password": "supersecret1"})
        self.assertEqual(second.status_code, 409)

    def test_wrong_password_rejected(self):
        self.client.post("/api/auth/signup", json={"email": "wrong@example.com", "password": "supersecret1"})
        login = self.client.post("/api/auth/login", json={"email": "wrong@example.com", "password": "nope12345"})
        self.assertEqual(login.status_code, 401)

    def test_unauthenticated_me_rejected(self):
        response = self.client.get("/api/auth/me")
        self.assertEqual(response.status_code, 401)

    def test_verify_email_flow(self):
        from backend import security
        from backend.database import SessionLocal
        from backend.models import User

        self.client.post("/api/auth/signup", json={"email": "verify@example.com", "password": "supersecret1"})
        db = SessionLocal()
        user = db.query(User).filter(User.email == "verify@example.com").first()
        token = security.create_email_token(user.id, "verify_email")
        db.close()

        response = self.client.post("/api/auth/verify-email", params={"token": token})
        self.assertEqual(response.status_code, 200)

        self.client.post("/api/auth/login", json={"email": "verify@example.com", "password": "supersecret1"})
        me = self.client.get("/api/auth/me")
        self.assertTrue(me.json()["is_verified"])

    def test_invalid_verification_token_rejected(self):
        response = self.client.post("/api/auth/verify-email", params={"token": "not-a-real-token"})
        self.assertEqual(response.status_code, 400)

    def test_forgot_password_does_not_leak_existence(self):
        self.client.post("/api/auth/signup", json={"email": "leaktest@example.com", "password": "supersecret1"})
        known = self.client.post("/api/auth/forgot-password", json={"email": "leaktest@example.com"})
        unknown = self.client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"})
        self.assertEqual(known.status_code, 200)
        self.assertEqual(unknown.status_code, 200)
        self.assertEqual(known.json()["message"], unknown.json()["message"])

    def test_reset_password_with_token(self):
        from backend import security
        from backend.database import SessionLocal
        from backend.models import User

        self.client.post("/api/auth/signup", json={"email": "reset@example.com", "password": "supersecret1"})
        db = SessionLocal()
        user = db.query(User).filter(User.email == "reset@example.com").first()
        token = security.create_email_token(user.id, "reset_password")
        db.close()

        response = self.client.post("/api/auth/reset-password", json={"token": token, "password": "newpassword1"})
        self.assertEqual(response.status_code, 200)

        old_login = self.client.post("/api/auth/login", json={"email": "reset@example.com", "password": "supersecret1"})
        self.assertEqual(old_login.status_code, 401)
        new_login = self.client.post("/api/auth/login", json={"email": "reset@example.com", "password": "newpassword1"})
        self.assertEqual(new_login.status_code, 200)


if __name__ == "__main__":
    unittest.main()
