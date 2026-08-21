"""Agent Stream Lambda — streams MPS or RCA agent reasoning to the dashboard.

Deployed as a Lambda Function URL with InvokeMode=RESPONSE_STREAM.
The frontend calls this directly (via CloudFront) when an anomaly is detected,
and the agent's step-by-step reasoning streams back as Server-Sent Events.

Request body (JSON):
  {
    "agent":       "mps" | "rca",
    "tank_id":     "PT-03",
    "fault_type":  "FoamingExcess",
    "anomaly_score": 0.87,
    "line_id":     "LINE-1"
  }

Response: text/event-stream
  data: {"type": "chunk", "text": "Analyzing tank PT-03 schedule..."}\n\n
  data: {"type": "chunk", "text": "Found 3 affected jobs..."}\n\n
  data: {"type": "done", "result": {...}}\n\n
"""
import json
import os
import boto3

REGION          = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
MPS_PARAM       = os.environ.get("MPS_RUNTIME_PARAM", "/paintshop/mps_agent_runtime_arn")
RCA_PARAM       = os.environ.get("RCA_RUNTIME_PARAM", "/paintshop/rca_agent_runtime_arn")

ssm = boto3.client("ssm", region_name=REGION)
_arn_cache: dict = {}


def _get_runtime_arn(agent_type: str) -> str:
    param = MPS_PARAM if agent_type == "mps" else RCA_PARAM
    if param not in _arn_cache:
        _arn_cache[param] = ssm.get_parameter(Name=param)["Parameter"]["Value"]
    return _arn_cache[param]


def _build_prompt(agent_type: str, body: dict) -> str:
    tank_id    = body.get("tank_id",       "UNKNOWN")
    fault_type = body.get("fault_type",    "UNKNOWN")
    score      = body.get("anomaly_score", 0.0)
    line_id    = body.get("line_id",       "LINE-1")

    if agent_type == "mps":
        return (
            f"Tank anomaly detected. Tank: {tank_id}, Line: {line_id}, "
            f"Fault: {fault_type}, Score: {score:.2f}. "
            f"Reschedule all affected jobs to healthy tanks. "
            f"Maintain JPH >= 45 and minimise FBO delay. Return JSON recommendation."
        )
    return (
        f"RCA requested. Tank: {tank_id}, Fault: {fault_type}, "
        f"Score: {score:.2f}. "
        f"Analyse sensor history, fault patterns, and maintenance records. "
        f"Write the RCA report and return JSON result."
    )


def handler(event, context):
    """Lambda Response Streaming handler — yields SSE chunks."""

    # Parse request body
    raw_body = event.get("body", "{}")
    if isinstance(raw_body, str):
        body = json.loads(raw_body)
    else:
        body = raw_body or {}

    agent_type = body.get("agent", "mps").lower()
    prompt     = _build_prompt(agent_type, body)
    session_id = f"stream-{body.get('tank_id', 'unknown')}-{context.aws_request_id[:8]}"

    def sse(obj: dict) -> bytes:
        return f"data: {json.dumps(obj)}\n\n".encode("utf-8")

    def stream():
        yield sse({"type": "start", "agent": agent_type,
                   "tank_id": body.get("tank_id")})

        try:
            runtime_arn = _get_runtime_arn(agent_type)
            agentcore   = boto3.client("bedrock-agentcore", region_name=REGION)

            resp = agentcore.invoke_agent_runtime(
                agentRuntimeArn=runtime_arn,
                runtimeSessionId=session_id,
                payload=json.dumps({"inputText": prompt, "streaming": True}).encode("utf-8"),
            )

            # response is a streaming blob — read fully then emit as chunks
            raw_body = resp.get("response", "")
            if hasattr(raw_body, "read"):
                raw_body = raw_body.read().decode("utf-8")
            else:
                raw_body = str(raw_body)

            # Emit in chunks of ~512 chars for progressive streaming feel
            chunk_size = 512
            for i in range(0, max(len(raw_body), 1), chunk_size):
                chunk = raw_body[i:i + chunk_size]
                if chunk:
                    yield sse({"type": "chunk", "text": chunk})

            # Extract final JSON result
            start  = raw_body.rfind("{")
            end    = raw_body.rfind("}") + 1
            result = {}
            if start >= 0 and end > start:
                try:
                    result = json.loads(raw_body[start:end])
                except json.JSONDecodeError:
                    pass
            yield sse({"type": "done", "result": result})

        except Exception as exc:
            yield sse({"type": "error", "message": str(exc)})

    # Return streaming response
    # awslambdaric handles the RESPONSE_STREAM mode when InvokeMode is set on Function URL
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type":  "text/event-stream",
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
        "_stream": stream(),   # awslambdaric streaming marker
    }
