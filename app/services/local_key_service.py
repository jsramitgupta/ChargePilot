import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def _fernet() -> Fernet:
    derived_key = base64.urlsafe_b64encode(
        hashlib.sha256(settings.encryption_key.encode("utf-8")).digest()
    )
    return Fernet(derived_key)


def encrypt_local_key(local_key: str) -> str:
    if not local_key:
        raise ValueError("A local key is required.")
    if local_key.startswith("gAAAA"):
        decrypt_local_key(local_key)
        return local_key
    return _fernet().encrypt(local_key.encode("utf-8")).decode("ascii")


def decrypt_local_key(stored_key: str) -> str:
    if not stored_key.startswith("gAAAA"):
        return stored_key
    try:
        return _fernet().decrypt(stored_key.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise RuntimeError("Could not decrypt the device local key; check the configured encryption key.") from exc


def encrypt_endpoint_enrollment_code(code: str) -> str:
    if not code:
        raise ValueError("An endpoint enrollment code is required.")
    return _fernet().encrypt(code.encode("utf-8")).decode("ascii")


def decrypt_endpoint_enrollment_code(encrypted_code: str) -> str:
    try:
        return _fernet().decrypt(encrypted_code.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise RuntimeError("Could not decrypt the endpoint enrollment code; check the configured encryption key.") from exc
