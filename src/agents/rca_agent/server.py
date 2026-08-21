"""RCA Agent — AgentCore Runtime entrypoint."""
import json
import logging
import sys
import os

_agent_dir = os.path.dirname(os.path.abspath(__file__))
if _agent_dir not in sys.path:
    sys.path.insert(0, _agent_dir)

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from agent import get_agent

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = BedrockAgentCoreApp()


_RCA_RESULT_KEYS = (
    "severity", "root_cause", "recurrence_risk", "recommendation", "report_id",
)


def _extract_result(value, required_keys: tuple[str, ...], depth: int = 0):
    """Find a complete result without accepting intermediate tool responses."""
    if depth > 6:
        return None
    if isinstance(value, dict):
        if all(value.get(key) not in (None, "") for key in required_keys):
            return value
        for key in ("result", "output", "response", "message", "content"):
            if key in value:
                found = _extract_result(value[key], required_keys, depth + 1)
                if found:
                    return found
        return None
    if isinstance(value, (list, tuple)):
        for item in reversed(value):
            found = _extract_result(item, required_keys, depth + 1)
            if found:
                return found
        return None
    if not isinstance(value, str):
        message = getattr(value, "message", None)
        if message is not None:
            found = _extract_result(message, required_keys, depth + 1)
            if found:
                return found
        value = str(value)

    try:
        decoded = json.loads(value)
        found = _extract_result(decoded, required_keys, depth + 1)
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
        found = _extract_result(decoded, required_keys, depth + 1)
        if found:
            matches.append(found)
    return matches[-1] if matches else None


@app.entrypoint
async def invoke(payload: dict):
    input_text = payload.get("inputText", payload.get("input", ""))
    log.info("RCA Agent invoked: %.200s", input_text)

    response = get_agent()(input_text)
    result = _extract_result(response, _RCA_RESULT_KEYS)
    if result:
        return result

    output_str = str(response)
    log.error("RCA agent returned no complete structured result: %.1000s", output_str)
    return {
        "error": "RCA agent did not return complete structured JSON with a recommendation.",
        "output": output_str,
    }


if __name__ == "__main__":
    app.run()
