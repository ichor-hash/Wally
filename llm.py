"""
LLM providers for Ethan.

- groq:              Groq cloud (default; free tier)
- openrouter:        OpenRouter cloud
- openai_compatible: any server that speaks the OpenAI chat-completions API.
                     Point LLM_BASE_URL at Ollama, LM Studio, vLLM or llama.cpp
                     and no text leaves your machine and no tokens are billed.

Selected with LLM_PROVIDER / LLM_MODEL / LLM_BASE_URL / LLM_API_KEY (see .env.example).

Every provider exposes:
- chat(): plain completion, returns text
- chat_with_usage(): returns (text, usage dict)
- stream_chat(): generator of ("token", str) and finally ("usage", dict)
"""
import json
import os
from abc import ABC, abstractmethod
from typing import List, Optional, Iterator, Tuple, Dict, Any

try:
    import groq
except ImportError:
    groq = None


RATE_LIMIT_HEADERS = {
    "x-ratelimit-limit-requests": "limit_requests",
    "x-ratelimit-remaining-requests": "remaining_requests",
    "x-ratelimit-reset-requests": "reset_requests",
    "x-ratelimit-limit-tokens": "limit_tokens",
    "x-ratelimit-remaining-tokens": "remaining_tokens",
    "x-ratelimit-reset-tokens": "reset_tokens",
}


def _usage_dict(usage) -> Dict[str, int]:
    if not usage:
        return {}
    get = usage.get if isinstance(usage, dict) else lambda k, d=0: getattr(usage, k, d)
    return {
        "prompt_tokens": get("prompt_tokens", 0) or 0,
        "completion_tokens": get("completion_tokens", 0) or 0,
        "total_tokens": get("total_tokens", 0) or 0,
    }


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    provider_name = "unknown"

    def __init__(self):
        # Most recent rate-limit headers reported by the upstream API
        self.upstream_limits: Dict[str, Any] = {}

    def _capture_limits(self, headers):
        limits = {}
        for header, key in RATE_LIMIT_HEADERS.items():
            value = headers.get(header)
            if value is not None:
                limits[key] = int(value) if value.isdigit() else value
        if limits:
            self.upstream_limits = limits

    @abstractmethod
    def chat_with_usage(
        self,
        messages: List[dict],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024
    ) -> Tuple[str, Dict[str, int]]:
        """Send chat completion request and return (response text, token usage)."""
        pass

    def chat(
        self,
        messages: List[dict],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024
    ) -> str:
        """Send chat completion request and return response text."""
        return self.chat_with_usage(messages, model, temperature, max_tokens)[0]

    def stream_chat(
        self,
        messages: List[dict],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024
    ) -> Iterator[Tuple[str, Any]]:
        """Default streaming: one token event containing the whole answer."""
        text, usage = self.chat_with_usage(messages, model, temperature, max_tokens)
        yield "token", text
        yield "usage", usage


class GroqLLM(LLMProvider):
    """
    LLM via Groq API.
    Free tier, very fast inference.

    Models available (October 2026):
    - openai/gpt-oss-20b (recommended, free, 1000 T/sec)
    - openai/gpt-oss-120b (free, 500 T/sec)
    - llama-3.1-8b-instant (Enterprise only)
    - llama-3.3-70b-versatile (Enterprise only)

    Requires: GROQ_API_KEY in environment
    """

    provider_name = "Groq"

    def __init__(self, model: str = "openai/gpt-oss-20b"):
        super().__init__()
        if groq is None:
            raise ImportError("groq not installed. Run: pip install groq")

        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not set in environment")

        self.client = groq.Groq(api_key=api_key)
        self.model = model

    def _extra(self, model: Optional[str]) -> Dict[str, Any]:
        """
        gpt-oss models reason before answering, and those hidden tokens are billed
        and count against max_tokens. Grounded Q&A over five chunks needs little
        deliberation, so the default is "low": cheaper, faster, and it stops long
        reasoning from eating the whole output budget and returning an empty answer.
        Override with LLM_REASONING_EFFORT=medium|high, or set it empty to send nothing.
        """
        effort = os.getenv("LLM_REASONING_EFFORT", "low").strip().lower()
        if effort and "gpt-oss" in (model or self.model):
            return {"reasoning_effort": effort}
        return {}

    def chat_with_usage(
        self,
        messages: List[dict],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024
    ) -> Tuple[str, Dict[str, int]]:
        raw = self.client.chat.completions.with_raw_response.create(
            model=model or self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            extra_body=self._extra(model) or None,
        )
        self._capture_limits(raw.headers)
        response = raw.parse()
        return response.choices[0].message.content or "", _usage_dict(response.usage)

    def stream_chat(
        self,
        messages: List[dict],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024
    ) -> Iterator[Tuple[str, Any]]:
        raw = self.client.chat.completions.with_raw_response.create(
            model=model or self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            extra_body={"stream_options": {"include_usage": True}, **self._extra(model)},
        )
        self._capture_limits(raw.headers)
        usage = {}
        for chunk in raw.parse():
            if chunk.choices:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield "token", delta
            # Usage arrives on the final chunk (OpenAI-style or Groq's x_groq field)
            if getattr(chunk, "usage", None):
                usage = _usage_dict(chunk.usage)
            elif getattr(chunk, "x_groq", None) and getattr(chunk.x_groq, "usage", None):
                usage = _usage_dict(chunk.x_groq.usage)
        yield "usage", usage


class OpenRouterLLM(LLMProvider):
    """
    LLM via OpenRouter API.
    Free credits for new accounts.

    Models:
    - google/gemma-2-9b-it (free)
    - meta-llama/llama-3.1-8b-instruct (free)
    - mistralai/mistral-7b-instruct-v0.2 (free)

    Requires: OPENROUTER_API_KEY in environment
    """

    provider_name = "OpenRouter"
    URL = "https://openrouter.ai/api/v1/chat/completions"
    STREAM_EXTRAS = {"usage": {"include": True}}  # asks for token usage on the final stream chunk

    def __init__(self, model: str = "google/gemma-2-9b-it"):
        super().__init__()
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY not set in environment")

        self.api_key = api_key
        self.model = model

    def _headers(self):
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def chat_with_usage(
        self,
        messages: List[dict],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024
    ) -> Tuple[str, Dict[str, int]]:
        import requests

        response = requests.post(
            self.URL,
            headers=self._headers(),
            json={
                "model": model or self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            },
            timeout=120,
        )
        response.raise_for_status()
        self._capture_limits(response.headers)
        data = response.json()
        return data["choices"][0]["message"]["content"], _usage_dict(data.get("usage"))

    def stream_chat(
        self,
        messages: List[dict],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024
    ) -> Iterator[Tuple[str, Any]]:
        import requests

        response = requests.post(
            self.URL,
            headers=self._headers(),
            json={
                "model": model or self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
                **self.STREAM_EXTRAS,
            },
            stream=True,
            timeout=120,
        )
        response.raise_for_status()
        self._capture_limits(response.headers)
        usage = {}
        for line in response.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            payload = line[len("data: "):]
            if payload == "[DONE]":
                break
            data = json.loads(payload)
            choices = data.get("choices") or []
            if choices:
                delta = choices[0].get("delta", {}).get("content")
                if delta:
                    yield "token", delta
            if data.get("usage"):
                usage = _usage_dict(data["usage"])
        yield "usage", usage


class OpenAICompatibleLLM(OpenRouterLLM):
    """
    Any OpenAI-compatible chat-completions endpoint, typically a local model server.

    Ollama:    LLM_BASE_URL=http://localhost:11434/v1   LLM_MODEL=llama3.2:3b
    LM Studio: LLM_BASE_URL=http://localhost:1234/v1
    vLLM:      LLM_BASE_URL=http://localhost:8000/v1

    LLM_API_KEY is optional; local servers ignore it.
    """

    provider_name = "OpenAI-compatible"
    STREAM_EXTRAS = {"stream_options": {"include_usage": True}}

    def __init__(self, model: Optional[str] = None, base_url: Optional[str] = None, api_key: Optional[str] = None):
        LLMProvider.__init__(self)
        base_url = (base_url or os.getenv("LLM_BASE_URL") or "http://localhost:11434/v1").rstrip("/")
        self.URL = f"{base_url}/chat/completions"
        self.api_key = api_key or os.getenv("LLM_API_KEY", "")
        self.model = model or "llama3.2:3b"
        self.provider_name = "Ollama" if ":11434" in base_url else "OpenAI-compatible"


DEFAULT_MODELS = {"groq": "openai/gpt-oss-20b", "openrouter": "google/gemma-2-9b-it", "openai_compatible": "llama3.2:3b"}


def llm_from_env() -> LLMProvider:
    """Build the provider named by LLM_PROVIDER (default groq), with LLM_MODEL if set."""
    provider = os.getenv("LLM_PROVIDER", "groq").strip().lower()
    model = os.getenv("LLM_MODEL", "").strip() or DEFAULT_MODELS.get(provider)
    return get_llm_provider(provider, model=model)


def get_llm_provider(provider: str = "groq", **kwargs) -> LLMProvider:
    """
    Factory function to get LLM provider.

    Usage:
        llm = get_llm_provider("groq")
        llm = get_llm_provider("openrouter")

    Args:
        provider: One of "groq", "openrouter"
        **kwargs: Additional arguments passed to provider constructor

    Returns:
        LLMProvider instance
    """
    providers = {
        "groq": GroqLLM,
        "openrouter": OpenRouterLLM,
        "openai_compatible": OpenAICompatibleLLM,
    }

    if provider not in providers:
        raise ValueError(f"Unknown provider: {provider}. Choose from: {list(providers.keys())}")

    return providers[provider](**kwargs)
