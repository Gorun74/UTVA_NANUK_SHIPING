import os
from flask import current_app
from flask_login import UserMixin


class User(UserMixin):
    def __init__(self, username):
        self.id = username
        self.username = username


def _get_users():
    """Read credentials from Flask app config (set from env vars at startup)."""
    users = {}
    try:
        u1 = current_app.config.get("USER1_NAME", "").strip()
        p1 = current_app.config.get("USER1_PASS", "").strip()
        u2 = current_app.config.get("USER2_NAME", "").strip()
        p2 = current_app.config.get("USER2_PASS", "").strip()
    except RuntimeError:
        # Outside app context — fall back to env
        u1 = os.environ.get("USER1_NAME", "admin")
        p1 = os.environ.get("USER1_PASS", "admin")
        u2 = os.environ.get("USER2_NAME", "")
        p2 = os.environ.get("USER2_PASS", "")

    if u1:
        users[u1] = p1
    if u2:
        users[u2] = p2
    return users


def validate_user(username: str, password: str):
    users = _get_users()
    if username in users and users[username] == password:
        return User(username)
    return None


def load_user(user_id: str):
    users = _get_users()
    if user_id in users:
        return User(user_id)
    return None
