"""Bedrock Agent action group handler — provides scheduling tools to the supervisor agent.

Action group: SchedulingTools
Tools:
  GET /get-production-schedule  - jobs scheduled for a tank in the next N hours
  GET /get-available-tanks      - healthy tanks on a production line
  GET /get-fault-history        - recent fault decisions recorded for a tank
"""
import json
import os
import boto3
from datetime import datetime, timezone, timedelta
from boto3.dynamodb.conditions import Key, Attr

JOBS_TABLE    = os.environ.get("JOBS_TABLE",    "production-jobs")
STATUS_TABLE  = os.environ.get("STATUS_TABLE",  "tank-status")
HISTORY_TABLE = os.environ.get("HISTORY_TABLE", "schedule-history")

dynamodb = boto3.resource("dynamodb")


def _get_param(params: list, name: str, default=None):
    for p in params or []:
        if p["name"] == name:
            return p["value"]
    return default


def get_production_schedule(tank_id: str, hours_ahead: int = 24) -> dict:
    table   = dynamodb.Table(JOBS_TABLE)
    now     = datetime.now(timezone.utc)
    cutoff  = (now + timedelta(hours=hours_ahead)).isoformat()
    result  = table.scan(
        FilterExpression=Attr("tank_id").eq(tank_id)
            & Attr("scheduled_time").lte(cutoff)
            & Attr("status").ne("completed"),
    )
    return {
        "tank_id":     tank_id,
        "hours_ahead": hours_ahead,
        "jobs":        result.get("Items", []),
    }


def get_available_tanks(line_id: str) -> dict:
    table  = dynamodb.Table(STATUS_TABLE)
    result = table.scan(
        FilterExpression=Attr("line_id").eq(line_id) & Attr("status").eq("online"),
    )
    return {
        "line_id":         line_id,
        "available_tanks": result.get("Items", []),
    }


def get_fault_history(tank_id: str, hours: int = 24) -> dict:
    table  = dynamodb.Table(HISTORY_TABLE)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    result = table.query(
        IndexName="tank-time-index",
        KeyConditionExpression=Key("trigger_tank").eq(tank_id)
            & Key("timestamp").gte(cutoff),
    )
    return {
        "tank_id":      tank_id,
        "hours":        hours,
        "fault_events": result.get("Items", []),
    }


def handler(event, context):
    action_group = event.get("actionGroup", "")
    api_path     = event.get("apiPath", "")
    http_method  = event.get("httpMethod", "GET").upper()
    parameters   = event.get("parameters", [])

    try:
        if api_path == "/get-production-schedule":
            tank_id     = _get_param(parameters, "tank_id")
            hours_ahead = int(_get_param(parameters, "hours_ahead", 24))
            body   = get_production_schedule(tank_id, hours_ahead)
            status = 200
        elif api_path == "/get-available-tanks":
            line_id = _get_param(parameters, "line_id")
            body    = get_available_tanks(line_id)
            status  = 200
        elif api_path == "/get-fault-history":
            tank_id = _get_param(parameters, "tank_id")
            hours   = int(_get_param(parameters, "hours", 24))
            body    = get_fault_history(tank_id, hours)
            status  = 200
        else:
            body   = {"error": f"Unknown apiPath: {api_path}"}
            status = 404
    except Exception as exc:
        body   = {"error": str(exc)}
        status = 500

    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": action_group,
            "apiPath":     api_path,
            "httpMethod":  http_method,
            "httpStatusCode": status,
            "responseBody": {
                "application/json": {
                    "body": json.dumps(body, default=str)
                }
            },
        },
    }
