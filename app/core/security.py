import secrets
from typing import Final

import bcrypt


TOKEN_PREFIX: Final[str] = "Bearer "


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return bcrypt.hashpw(token.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_token(token: str, token_hash: str) -> bool:
    return bcrypt.checkpw(token.encode("utf-8"), token_hash.encode("utf-8"))


def get_bearer_token(auth_header: str | None) -> str | None:
    if not auth_header:
        return None
    if not auth_header.startswith(TOKEN_PREFIX):
        return None
    return auth_header.removeprefix(TOKEN_PREFIX).strip()
