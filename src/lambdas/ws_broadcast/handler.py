"""WebSocket broadcast Lambda — pushes real-time messages to connected dashboard clients.

Triggered by:
  1. DynamoDB Streams on tank-status  → TANK_UPDATE to all clients
  2. EventBridge TankAnomalyDetected  → ANOMALY_ALERT to all clients
  3. WebSocket $default route         → stream-agent action to requesting client
  4. Direct invoke                    → SCHEDULE_UPDATE to all clients
"""
import json
import os
import time
import boto3
from decimal import Decimal

WS_CONNECTIONS_TABLE = os.environ.get("WS_CONNECTIONS_TABLE", "ws-connections")
WS_ENDPOINT          = os.environ.get("WS_ENDPOINT", "")
MPS_RUNTIME_PARAM    = os.environ.get("MPS_RUNTIME_PARAM", "/paintshop/mps_agent_runtime_arn")
RCA_RUNTIME_PARAM    = os.environ.get("RCA_RUNTIME_PARAM", "/paintshop/rca_agent_runtime_arn")
REGION               = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

dynamodb = boto3.resource("dynamodb", region_name=REGION)
ssm      = boto3.client("ssm",        region_name=REGION)


class _Encoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def _gw_client():
    return boto3.client(
        "apigatewaymanagementapi",
        endpoint_url=WS_ENDPOINT,
        region_name=REGION,
    )


def _get_connections() -> list[str]:
    resp = dynamodb.Table(WS_CONNECTIONS_TABLE).scan(
        ProjectionExpression="connection_id"
    )
    return [item["connection_id"] for item in resp.get("Items", [])]


def _send(gw, connection_id: str, message: dict) -> bool:
    """Send message to one connection. Returns False if connection is stale."""
    try:
        gw.post_to_connection(
            ConnectionId=connection_id,
            Data=json.dumps(message, cls=_Encoder).encode("utf-8"),
        )
        return True
    except gw.exceptions.GoneException:
        dynamodb.Table(WS_CONNECTIONS_TABLE).delete_item(
            Key={"connection_id": connection_id}
        )
        return False
    except Exception:
        return True  # keep connection, may be transient


def _broadcast(message: dict):
    """Push message to all active WebSocket connections."""
    if not WS_ENDPOINT:
        return
    gw = _gw_client()
    for cid in _get_connections():
        _send(gw, cid, message)


# ── Message builders ───────────────────────────────────────────────────────

def _handle_dynamodb_stream(record: dict):
    new_image = record.get("dynamodb", {}).get("NewImage", {})
    if not new_image:
        return

    def _unwrap(val: dict):
        if "S" in val:    return val["S"]
        if "N" in val:    return float(val["N"])
        if "BOOL" in val: return val["BOOL"]
        if "M" in val:    return {k: _unwrap(v) for k, v in val["M"].items()}
        if "L" in val:    return [_unwrap(v) for v in val["L"]]
        return None

    flat = {k: _unwrap(v) for k, v in new_image.items()}
    _broadcast({
        "type":            "TANK_UPDATE",
        "tank_id":         flat.get("tank_id", ""),
        "line_id":         flat.get("line_id", "LINE-1"),
        "status":          flat.get("status", "online"),
        "current_jph":     flat.get("current_jph", 0),
        "fault_type":      flat.get("fault_type", "normal"),
        "if_score":        flat.get("if_score", 0.0),
        "lstm_score":      flat.get("lstm_score", 0.0),
        "xgb_confidence":  flat.get("xgb_confidence", 0.0),
        "sensors":         flat.get("sensors", {}),
        "last_reading_ts": flat.get("last_reading_ts", ""),
    })


def _handle_anomaly_event(detail: dict, timestamp: str):
    _broadcast({
        "type":             "ANOMALY_ALERT",
        "tank_id":          detail.get("tank_id", ""),
        "fault_type":       detail.get("fault_type", ""),
        "if_score":         detail.get("if_score", 0.0),
        "lstm_score":       detail.get("lstm_score", 0.0),
        "breached_sensors": detail.get("breached_sensors", []),
        "jph_before":       detail.get("jph_before", 0),
        "timestamp":        timestamp,
    })


def _handle_schedule_update(payload: dict):
    _broadcast({
        "type":           "SCHEDULE_UPDATE",
        "tank_id":        payload.get("tank_id", ""),
        "projected_jph":  payload.get("projected_jph", 0),
        "assignments":    payload.get("assignments", []),
        "fbo_delay_mins": payload.get("fbo_delay_mins", 0),
        "summary":        payload.get("summary", ""),
        "timestamp":      payload.get("timestamp", ""),
    })


def _get_runtime_arn(agent_type: str) -> str:
    """Resolve the current ARN because agent deployments recreate runtimes."""
    param = MPS_RUNTIME_PARAM if agent_type == "mps" else RCA_RUNTIME_PARAM
    return ssm.get_parameter(Name=param)["Parameter"]["Value"]


def _find_agent_result(value, required_keys: tuple[str, ...], depth: int = 0):
    """Find complete agent JSON without accepting partial tool responses."""
    if depth > 6:
        return None
    if isinstance(value, dict):
        if all(value.get(key) not in (None, "") for key in required_keys):
            return value
        for key in ("result", "output", "response", "message", "content"):
            if key in value:
                found = _find_agent_result(value[key], required_keys, depth + 1)
                if found:
                    return found
        return None
    if isinstance(value, (list, tuple)):
        for item in reversed(value):
            found = _find_agent_result(item, required_keys, depth + 1)
            if found:
                return found
        return None
    if not isinstance(value, str):
        value = str(value)

    try:
        decoded = json.loads(value)
        found = _find_agent_result(decoded, required_keys, depth + 1)
        if found:
            return found
    except (json.JSONDecodeError, TypeError):
        pass

    decoder = json.JSONDecoder()
    matches = []
    for index, char in enumerate(value):
        if char != "{":
            continue
        try:
            decoded, _ = decoder.raw_decode(value[index:])
        except json.JSONDecodeError:
            continue
        found = _find_agent_result(decoded, required_keys, depth + 1)
        if found:
            matches.append(found)
    return matches[-1] if matches else None


def _extract_agent_result(raw_body: str, agent_type: str) -> dict:
    required_keys = (
        ("projected_jph",)
        if agent_type == "mps"
        else ("severity", "root_cause", "recurrence_risk", "recommendation", "report_id")
    )
    result = _find_agent_result(raw_body, required_keys)
    if result:
        return result

    try:
        response = json.loads(raw_body)
    except json.JSONDecodeError:
        response = None
    if isinstance(response, dict) and response.get("error"):
        raise ValueError(str(response["error"]))
    raise ValueError(
        f"{agent_type.upper()} agent returned no complete structured JSON. "
        f"Required fields: {', '.join(required_keys)}."
    )


def _handle_stream_agent(connection_id: str, message: dict):
    """Invoke AgentCore Runtime and stream chunks back to the requesting connection."""
    if not WS_ENDPOINT:
        return

    agent_type = message.get("agent", "mps").lower()
    tank_id    = message.get("tank_id", "UNKNOWN")
    fault_type = message.get("fault_type", "UNKNOWN")
    score      = float(message.get("anomaly_score") or 0.0)
    line_id    = message.get("line_id", "LINE-1")

    gw = _gw_client()

    _send(gw, connection_id, {
        "type": "AGENT_STREAM_START",
        "agent": agent_type,
        "tank_id": tank_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })

    if agent_type == "mps":
        prompt = (
            f"Tank anomaly detected. Tank: {tank_id}, Line: {line_id}, "
            f"Fault: {fault_type}, Score: {score:.2f}. "
            f"Reschedule affected jobs. Maintain JPH >= 45. Return JSON recommendation."
        )
    else:
        prompt = (
            f"RCA requested. Tank: {tank_id}, Fault: {fault_type}, Score: {score:.2f}. "
            f"Analyse sensor history, fault patterns, maintenance records. Return JSON."
        )

    try:
        runtime_arn = _get_runtime_arn(agent_type)
        agentcore   = boto3.client("bedrock-agentcore", region_name=REGION)
        session_id  = f"ws-{agent_type}-{tank_id}-{int(time.time())}-{connection_id[-10:]}"

        resp = agentcore.invoke_agent_runtime(
            agentRuntimeArn=runtime_arn,
            runtimeSessionId=session_id,
            payload=json.dumps({"inputText": prompt, "streaming": True}).encode("utf-8"),
        )
        raw_body = resp.get("response", "")
        if hasattr(raw_body, "read"):
            raw_body = raw_body.read().decode("utf-8")
        else:
            raw_body = str(raw_body)

        # Emit in chunks for progressive feel
        chunk_size = 512
        for i in range(0, max(len(raw_body), 1), chunk_size):
            chunk = raw_body[i:i + chunk_size]
            if chunk:
                _send(gw, connection_id, {
                    "type": "AGENT_CHUNK", "agent": agent_type,
                    "tank_id": tank_id, "text": chunk,
                })

        result = _extract_agent_result(raw_body, agent_type)
        _send(gw, connection_id, {
            "type": "AGENT_STREAM_DONE",
            "agent": agent_type,
            "tank_id": tank_id,
            "result": result,
        })

    except Exception as exc:
        print(
            f"Agent invocation failed: agent={agent_type} tank={tank_id} "
            f"error={exc}",
            flush=True,
        )
        _send(gw, connection_id, {
            "type": "AGENT_STREAM_ERROR",
            "agent": agent_type,
            "tank_id": tank_id,
            "error": str(exc),
        })


# ── Handler ────────────────────────────────────────────────────────────────

def handler(event, context):
    # ── DynamoDB Streams ───────────────────────────────────────────────────
    records = event.get("Records", [])
    if records and records[0].get("eventSource") == "aws:dynamodb":
        for rec in records:
            if rec.get("eventName") in ("INSERT", "MODIFY"):
                _handle_dynamodb_stream(rec)
        return {"statusCode": 200}

    # ── EventBridge ────────────────────────────────────────────────────────
    if event.get("source") == "paintshop.anomaly":
        _handle_anomaly_event(event.get("detail", {}), event.get("time", ""))
        return {"statusCode": 200}

    # ── WebSocket $default (stream-agent action) ───────────────────────────
    if "requestContext" in event and "connectionId" in event.get("requestContext", {}):
        connection_id = event["requestContext"]["connectionId"]
        try:
            body = json.loads(event.get("body", "{}"))
        except (json.JSONDecodeError, TypeError):
            body = {}
        if body.get("action") == "stream-agent":
            _handle_stream_agent(connection_id, body)
        return {"statusCode": 200}

    # ── Direct invoke (schedule update) ────────────────────────────────────
    if event.get("type") == "SCHEDULE_UPDATE":
        _handle_schedule_update(event)

    return {"statusCode": 200}
