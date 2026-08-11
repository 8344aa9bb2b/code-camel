from __future__ import annotations

from typing import Dict, List, Optional

import requests

from .. import config


class LLMClientError(Exception):
    """Raised when the LLM request or response is unusable."""


class LLMClient:
    """Provider-agnostic chat-completion client (OpenAI-compatible API).

    Works against any endpoint that implements the ``/chat/completions``
    contract: OpenAI, OpenRouter, Azure, Ollama, vLLM, etc. Only the
    base URL, API key, and model name differ.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        self._api_key = api_key or config.LLM_API_KEY
        self._base_url = (base_url or config.LLM_BASE_URL).rstrip("/")
        self._model = model or config.LLM_MODEL
        self._timeout = timeout or config.LLM_TIMEOUT
        if not self._api_key:
            raise LLMClientError("LLM_API_KEY is not set.")

    def complete(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float = 0.2,
        json_mode: bool = True,
    ) -> str:
        """Return the assistant's text reply for *messages*."""
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=self._timeout)
        except requests.RequestException as exc:
            raise LLMClientError(f"LLM request failed: {exc}") from exc

        if not resp.ok:
            raise LLMClientError(
                f"POST {url} -> {resp.status_code}: {resp.text[:300]}"
            )

        try:
            content = resp.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMClientError(f"Unexpected LLM response: {exc}") from exc
        return content
