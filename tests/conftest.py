import os

# Isolated SQLite database for API-level tests. Environment is set before app import.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["SEED_DEMO_DATA"] = "false"
os.environ["USE_CELERY"] = "false"
