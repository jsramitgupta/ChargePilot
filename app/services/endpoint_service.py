from app.core.security import get_bearer_token


def validate_endpoint_auth(authorization: str | None) -> bool:
    token = get_bearer_token(authorization)
    return token == "test-endpoint-token"
