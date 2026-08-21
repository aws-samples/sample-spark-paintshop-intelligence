"""MPS Supervisor Agent — AgentCore Runtime entrypoint."""
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


def _extract_result(value, required_key: str, depth: int = 0):
    """Find a structured result in direct, wrapped, or markdown model output."""
    if depth > 4:
        return None
    if isinstance(value, dict):
        if required_key in value:
            return value
        for key in ("result", "output", "response"):
            if key in value:
                found = _extract_result(value[key], required_key, depth + 1)
                if found:
                    return found
        return None
    if not isinstance(value, str):
        value = str(value)

    try:
        decoded = json.loads(value)
        found = _extract_result(decoded, required_key, depth + 1)
        if found:
            return found
    except json.JSONDecodeError:
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
        found = _extract_result(decoded, required_key, depth + 1)
        if found:
            matches.append(found)
    return matches[-1] if matches else None


@app.entrypoint
async def invoke(payload: dict):
    input_text = payload.get("inputText", payload.get("input", ""))
    log.info("MPS Agent invoked: %.200s", input_text)

    response = get_agent()(input_text)
    result = _extract_result(response, "projected_jph")
    if result:
        return result

    output_str = str(response)
    log.error("MPS agent returned no structured result: %.1000s", output_str)
    return {
        "error": "MPS agent did not return the required structured JSON.",
        "output": output_str,
    }


if __name__ == "__main__":
    app.run()
