"""Root conftest — runs before pytest-django configures Django.

Guarantees a throwaway encryption key so the suite never depends on a developer
having one exported. The SQLite decision lives in settings.py, which checks
whether pytest is loaded.
"""

import os

from cryptography.fernet import Fernet

os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEYS", Fernet.generate_key().decode())
