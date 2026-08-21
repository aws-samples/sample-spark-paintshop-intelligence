"""WebSocket $disconnect handler — removes connection from DynamoDB."""
import os
import boto3

WS_CONNECTIONS_TABLE = os.environ.get("WS_CONNECTIONS_TABLE", "ws-connections")
REGION               = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

dynamodb = boto3.resource("dynamodb", region_name=REGION)


def handler(event, context):
    connection_id = event["requestContext"]["connectionId"]
    dynamodb.Table(WS_CONNECTIONS_TABLE).delete_item(
        Key={"connection_id": connection_id}
    )
    return {"statusCode": 200, "body": "Disconnected"}
