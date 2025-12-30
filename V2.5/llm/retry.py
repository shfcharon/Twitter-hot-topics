"""
JSON-only + retry wrapper for local LLM calls.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Sequence, Tuple


@dataclass(frozen=True)
class RetryConfig:
    max_retry: int = 3
    backoff_s: float = 1.0


def validate_exact_keys(obj: Any, expected_keys: Sequence[str]) -> Tuple[bool, str]:
    if not isinstance(obj, dict):
        return False, "not_a_dict"
    got = set(obj.keys())
    exp = set(expected_keys)
    if got != exp:
        missing = sorted(exp - got)
        extra = sorted(got - exp)
        return False, f"keys_mismatch missing={missing} extra={extra}"
    return True, "ok"


def call_llm_json(
    call_fn: Callable[[str], str],
    prompt: str,
    *,
    expected_keys: Optional[Sequence[str]] = None,
    validator_fn=None,
    retry_cfg: RetryConfig = RetryConfig(),
    on_raw_response: Optional[Callable[[str, int], None]] = None,
) -> Dict[str, Any]:
    """
    call_fn(prompt) -> text
    Enforces: JSON-only, optional exact keys, optional validator.
    """
    last_err: Optional[str] = None
    for i in range(retry_cfg.max_retry):
        try:
            text = call_fn(prompt).strip()
            if on_raw_response:
                on_raw_response(text, i + 1)

            data = json.loads(text)
            if expected_keys is not None:
                ok, msg = validate_exact_keys(data, expected_keys)
                if not ok:
                    raise ValueError(msg)
            if validator_fn is not None:
                ok, msg = validator_fn(data)
                if not ok:
                    raise ValueError(msg)
            return data
        except Exception as e:
            last_err = str(e)
            if i == retry_cfg.max_retry - 1:
                raise RuntimeError(f"LLM JSON failed after retries: {last_err}") from e
            # corrective suffix
            prompt = (
                prompt
                + "\n\nYour previous output was invalid.\n"
                + "Return valid JSON only. No markdown. No extra keys."
            )
            time.sleep(retry_cfg.backoff_s * (i + 1))
    raise RuntimeError(f"LLM JSON failed: {last_err}")

