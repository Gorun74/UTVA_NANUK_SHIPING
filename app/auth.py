from flask_login import UserMixin
from app.config import Config


class User(UserMixin):
    def __init__(self, username):
        self.id = username
        self.username = username


def _get_users():
    users = {}
    if Config.USER1_NAME:
        users[Config.USER1_NAME] = Config.USER1_PASS
    if Config.USER2_NAME:
        users[Config.USER2_NAME] = Config.USER2_PASS
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
