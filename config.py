import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class Config:
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))

    database_path = os.getenv("DATABASE_PATH", os.path.join(BASE_DIR, "database", "society.db"))
    if not os.path.isabs(database_path):
        database_path = os.path.join(BASE_DIR, database_path)

    SQLALCHEMY_DATABASE_URI = f"sqlite:///{database_path}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    flask_env = os.getenv("FLASK_ENV", "development")
    secret_key = os.getenv("SECRET_KEY")

    if flask_env == "production" and (not secret_key or secret_key.startswith("change-this")):
        raise RuntimeError("CRITICAL: SECRET_KEY must be properly set in production environment!")

    SECRET_KEY = secret_key or "society-maintenance-secret-key-2026-dev"

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = (flask_env == "production")
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)