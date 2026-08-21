"""WebSocket $connect handler — verifies Cognito access tokens and stores connections."""
import base64
import json
import os
import time

import boto3
from botocore.exceptions import ClientError

WS_CONNECTIONS_TABLE = os.environ.get("WS_CONNECTIONS_TABLE", "ws-connections")
USER_POOL_ID = os.environ.get("USER_POOL_ID", "")
USER_POOL_CLIENT_ID = os.environ.get("USER_POOL_CLIENT_ID", "")
REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}"

dynamodb = boto3.resource("dynamodb", region_name=REGION)
cognito = boto3.client("cognito-idp", region_name=REGION)


def _decode_verified_claims(token: str) -> dict:
    """Decode claims only after Cognito has cryptographically verified the token."""
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Malformed JWT")
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    claims = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
    if not isinstance(claims, dict):
        raise ValueError("Malformed JWT claims")
    return claims


def _validate_cognito_token(token: str) -> dict | None:
    """Verify a Cognito access token and return trusted identity claims."""
    if not token or not USER_POOL_ID or not USER_POOL_CLIENT_ID:
        return None
    try:
        # GetUser rejects tokens with an invalid signature, expiry, or token type.
        user = cognito.get_user(AccessToken=token)
        claims = _decode_verified_claims(token)
        if (
            claims.get("iss") != ISSUER
            or claims.get("client_id") != USER_POOL_CLIENT_ID
            or claims.get("token_use") != "access"
            or claims.get("exp", 0) < time.time()
        ):
            return None

        attributes = {
            item["Name"]: item["Value"]
            for item in user.get("UserAttributes", [])
            if "Name" in item and "Value" in item
        }
        return {
            "sub": claims.get("sub", user.get("Username", "unknown")),
            "email": attributes.get("email", claims.get("sub", "unknown")),
        }
    except (ClientError, ValueError, TypeError, json.JSONDecodeError):
        return None


def handler(event, context):
    connection_id = event["requestContext"]["connectionId"]
    query_params = event.get("queryStringParameters") or {}
    token = query_params.get("token", "")

    claims = _validate_cognito_token(token)
    if claims is None:
        return {"statusCode": 401, "body": "Unauthorized"}

    dynamodb.Table(WS_CONNECTIONS_TABLE).put_item(Item={
        "connection_id": connection_id,
        "user_email": claims.get("email", claims.get("sub", "unknown")),
        "connected_at": int(time.time()),
        "ttl": int(time.time()) + 86400,
    })
    return {"statusCode": 200, "body": "Connected"}
