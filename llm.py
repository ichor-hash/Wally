"""
LLM providers for RAG system.
Supports Groq and OpenRouter for cloud inference.
"""
import os
from abc import ABC, abstractmethod
from typing import List, Optional

try:
    import groq
except ImportError:
    groq = None


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    @abstractmethod
    def chat(
        self, 
        messages: List[dict], 
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024
    ) -> str:
        """Send chat completion request and return response text."""
        pass


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
    
    def __init__(self, model: str = "openai/gpt-oss-20b"):
        if groq is None:
            raise ImportError("groq not installed. Run: pip install groq")
        
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not set in environment")
        
        self.client = groq.Groq(api_key=api_key)
        self.model = model
    
    def chat(
        self, 
        messages: List[dict], 
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024
    ) -> str:
        response = self.client.chat.completions.create(
            model=model or self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        return response.choices[0].message.content


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
    
    def __init__(self, model: str = "google/gemma-2-9b-it"):
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY not set in environment")
        
        self.api_key = api_key
        self.model = model
    
    def chat(
        self, 
        messages: List[dict], 
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024
    ) -> str:
        import requests
        
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": model or self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]


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
    }
    
    if provider not in providers:
        raise ValueError(f"Unknown provider: {provider}. Choose from: {list(providers.keys())}")
    
    return providers[provider](**kwargs)