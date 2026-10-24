"""
ai_client.py — one place where the site talks to an LLM.

Provider is picked from environment variables (set them on the server, never in code):
  GROQ_API_KEY        → Groq (default model: GROQ_MODEL or "llama-3.3-70b-versatile")
  ANTHROPIC_API_KEY   → Claude (default model: ANTHROPIC_MODEL or "claude-sonnet-5-5")
If crypto-business/.env exists next to this folder, its values are loaded too.
"""
from __future__ import annotations

import os
import requests

BUSINESS_ENV = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "crypto-business", ".env"))


def _load_env_file(path: str) -> None:
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env_file(BUSINESS_ENV)
_load_env_file(os.path.join(os.path.dirname(__file__), ".env"))


def provider() -> str | None:
    if os.environ.get("GROQ_API_KEY"):
        return "Groq"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "Claude"
    return None


class AIError(Exception):
    def __init__(self, msg: str, code: str = "upstream_error"):
        super().__init__(msg)
        self.code = code


def ask(prompt: str, json_mode: bool = False, max_tokens: int = 1500, timeout: int = 90) -> str:
    p = provider()
    if p is None:
        raise AIError("No AI key configured (GROQ_API_KEY or ANTHROPIC_API_KEY).", "no_ai")
    system = "You are a careful crypto market analyst. Never give buy/sell signals, entry points, targets or stop-losses."
    if json_mode:
        system += " Reply with valid JSON only, no prose and no code fences."

    if p == "Groq":
        body = {
            "model": os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "temperature": 0.4,
            "max_tokens": max_tokens,
        }
        r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                          headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
                          json=body, timeout=timeout)
        if r.status_code == 429:
            raise AIError("Rate limited by Groq.", "rate_limited")
        if not r.ok:
            raise AIError(f"Groq error {r.status_code}: {r.text[:300]}")
        return r.json()["choices"][0]["message"]["content"]

    body = {
        "model": os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5"),
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }
    r = requests.post("https://api.anthropic.com/v1/messages",
                      headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"},
                      json=body, timeout=timeout)
    if r.status_code == 429:
        raise AIError("Rate limited by Anthropic.", "rate_limited")
    if not r.ok:
        raise AIError(f"Anthropic error {r.status_code}: {r.text[:300]}")
    return "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
