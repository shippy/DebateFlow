"""LLM provider factory — creates pydantic-ai Agents from ModelConfig."""

from __future__ import annotations

import os

from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

from models import ModelConfig

# Env var names — prefixed with DF_ to avoid Claude Code picking up the keys
API_KEY_ENV_VARS: dict[str, str] = {
    "anthropic": "DF_ANTHROPIC_API_KEY",
    "openai": "DF_OPENAI_API_KEY",
}


def _get_api_key(provider: str) -> str:
    """Read API key from DF_-prefixed env var."""
    env_var = API_KEY_ENV_VARS.get(provider)
    if not env_var:
        raise ValueError(f"Unknown provider '{provider}'. Supported: {list(API_KEY_ENV_VARS)}")
    key = os.environ.get(env_var)
    if not key:
        raise ValueError(f"Set {env_var} in your .env file or environment")
    return key


def _make_model(config: ModelConfig) -> AnthropicModel | OpenAIModel:
    """Create a pydantic-ai Model with explicit API key from DF_* env vars."""
    api_key = _get_api_key(config.provider)
    if config.provider == "anthropic":
        return AnthropicModel(config.model_name, provider=AnthropicProvider(api_key=api_key))
    elif config.provider == "openai":
        return OpenAIModel(config.model_name, provider=OpenAIProvider(api_key=api_key))
    else:
        raise ValueError(f"Unknown provider '{config.provider}'")


def make_agent(config: ModelConfig, system_prompt: str) -> Agent[None, str]:
    """Create a pydantic-ai Agent from a ModelConfig and system prompt."""
    model = _make_model(config)
    return Agent(
        model=model,
        system_prompt=system_prompt,
        model_settings=ModelSettings(temperature=config.temperature),
    )
