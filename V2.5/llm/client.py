"""
Ollama client (no paid API dependency).

Default Ollama service:
  http://localhost:11434

Endpoints used:
- POST /api/generate
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class OllamaConfig:
    base_url: str = "http://localhost:11434"
    model: str = "qwen2.5:7b-instruct"
    temperature: float = 0.0
    num_predict: int = 512
    timeout_s: int = 120


class OllamaError(RuntimeError):
    pass


def ollama_generate(
    *,
    cfg: OllamaConfig,
    prompt: str,
    stream: bool = False,
    extra_options: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Call Ollama /api/generate and return response text.
    """
    url = cfg.base_url.rstrip("/") + "/api/generate"
    payload: Dict[str, Any] = {
        "model": cfg.model,
        "prompt": prompt,
        "temperature": cfg.temperature,
        "num_predict": cfg.num_predict,
        "stream": stream,
    }
    if extra_options:
        # Ollama supports an "options" field for advanced params; keep optional.
        payload["options"] = extra_options

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=cfg.timeout_s) as resp:
            body = resp.read().decode("utf-8")
            out = json.loads(body)
            # non-stream response includes full "response"
            return str(out.get("response", "")).strip()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore") if hasattr(e, "read") else ""
        raise OllamaError(f"ollama_http_error status={getattr(e,'code',None)} body={body[:500]}") from e
    except Exception as e:
        raise OllamaError(f"ollama_call_failed: {e}") from e

