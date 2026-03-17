import os
from dotenv import load_dotenv

load_dotenv()


def _fix_db_url(url: str) -> str:
    """Railway sets DATABASE_URL as postgres://...; SQLAlchemy needs postgresql://..."""
    if url and url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://"):]
    return url


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    DATABASE_URL = _fix_db_url(os.environ.get("DATABASE_URL", "sqlite:///nanuk.db"))
    IMAGE_ROOT = os.environ.get("IMAGE_ROOT", "")

    USER1_NAME = os.environ.get("USER1_NAME", "admin")
    USER1_PASS = os.environ.get("USER1_PASS", "admin")
    USER2_NAME = os.environ.get("USER2_NAME", "")
    USER2_PASS = os.environ.get("USER2_PASS", "")

    # SQLAlchemy
    SQLALCHEMY_TRACK_MODIFICATIONS = False
