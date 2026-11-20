"""One fixed local Qwen3 check. No user input, paid provider or app activation."""

import asyncio
import json
import sys
from pathlib import Path


async def run(root):
    sys.path.insert(0, str(root))
    from core.llm.ollama_local import OllamaLocalProvider
    from core.llm.types import ChatMessage, LLMRequest

    result = {
        "passed": False,
        "outcome": "local_generation_not_confirmed",
        "paid_provider_requested": False,
        "request_limit": 1,
        "endpoint": "http://127.0.0.1:11434/api/chat",
        "model": "qwen3:8b",
    }
    try:
        reply = await OllamaLocalProvider(timeout_seconds=120).complete(
            LLMRequest(
                messages=[
                    ChatMessage(
                        role="user",
                        content="Return exactly CONNECTION_OK and nothing else. This is a fictional software connection check.",
                    )
                ],
                temperature=0,
                max_output_tokens=32,
            ),
            model="qwen3:8b",
        )
        matched = reply.text.strip() == "CONNECTION_OK"
        result.update(
            passed=matched and not reply.is_mock,
            acknowledgement_matched=matched,
            is_mock=reply.is_mock,
            input_tokens=reply.input_tokens,
            output_tokens=reply.output_tokens,
            outcome="local_qwen_generation_passed"
            if matched
            else "local_generation_unexpected_acknowledgement",
        )
    except Exception:
        result["outcome"] = "local_ollama_unavailable_or_failed"
    return result


if __name__ == "__main__":
    result = asyncio.run(run(Path(sys.argv[1]).resolve(strict=True)))
    print(json.dumps(result))
    sys.exit(0 if result["passed"] else 1)
