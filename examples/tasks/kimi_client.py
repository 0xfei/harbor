#!/usr/bin/env python3
"""
Shared Kimi API client for all Harbor tasks.

Required environment variables:
    KIMI_API_KEY   - API key
    KIMI_URL       - Base URL (e.g. https://dashscope.aliyuncs.com/compatible-mode/v1)
    KIMI_MODEL     - Model name (e.g. kimi-k2.5)

Usage:
    from kimi_client import call_kimi, KIMI_MODEL
"""

import os
import sys
import requests

KIMI_API_KEY = os.environ.get("KIMI_API_KEY", "")
KIMI_URL = os.environ.get("KIMI_URL", "").rstrip("/")
KIMI_MODEL = os.environ.get("KIMI_MODEL", "")


def _check_env():
    missing = [v for v in ("KIMI_API_KEY", "KIMI_URL", "KIMI_MODEL") if not os.environ.get(v)]
    if missing:
        print(f"ERROR: missing environment variables: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)


def call_kimi(
    messages: list,
    max_tokens: int = 8000,
    temperature: float = 0.2,
    timeout: int = 60,
) -> str:
    """Call Kimi API (OpenAI-compatible). Returns the assistant message content.
    
    Args:
        messages: List of message dicts with 'role' and 'content'
        max_tokens: Maximum tokens in response (default: 8000)
        temperature: Sampling temperature (default: 0.2)
        timeout: API request timeout in seconds (default: 60, max: 300)
    
    Note: Single API call timeout is limited to 1 minute by default.
          For complex analysis tasks, use multiple calls with smaller prompts.
    """
    _check_env()
    url = f"{KIMI_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {KIMI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": KIMI_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]
