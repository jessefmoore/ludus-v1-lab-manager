"""Root conftest: ensure APP_ENV=testing before any app module is imported."""

import os

os.environ.setdefault("APP_ENV", "testing")
