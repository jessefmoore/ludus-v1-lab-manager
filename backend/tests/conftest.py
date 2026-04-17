"""Root conftest: ensure APP_ENV=testing and test defaults before any app module is imported."""

import os

os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("ADMIN_EMAIL", "test@example.com")
os.environ.setdefault("ADMIN_PASSWORD", "test-password-1234")
os.environ.setdefault("LUDUS_DEFAULT_URL", "https://ludus.test:8080")
os.environ.setdefault("LUDUS_DEFAULT_API_KEY", "test-api-key")
