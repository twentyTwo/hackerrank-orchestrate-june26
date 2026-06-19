import os
from dataclasses import dataclass, field
from typing import Literal

from data.image_utils import to_base64


@dataclass
class ModelConfig:
    provider: Literal["ollama", "claude"]
    model: str
    base_url: str = "http://localhost:11434"
    max_tokens: int = 2048
    temperature: float = 0.0
    extended_thinking: bool = False
    thinking_budget: int = 8000


def call_vlm(
    system_prompt: str,
    user_prompt: str,
    images: list[tuple[bytes, str]],  # (raw_bytes, media_type)
    config: ModelConfig,
) -> str:
    if config.provider == "ollama":
        return _call_ollama(system_prompt, user_prompt, images, config)
    if config.provider == "claude":
        return _call_claude(system_prompt, user_prompt, images, config)
    raise ValueError(f"Unknown provider: {config.provider}")


def _call_ollama(
    system_prompt: str,
    user_prompt: str,
    images: list[tuple[bytes, str]],
    config: ModelConfig,
) -> str:
    import ollama

    encoded = [to_base64(img_bytes) for img_bytes, _ in images]

    response = ollama.chat(
        model=config.model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt, "images": encoded},
        ],
        format="json",
        options={"temperature": config.temperature},
    )
    return response["message"]["content"]


def _call_claude(
    system_prompt: str,
    user_prompt: str,
    images: list[tuple[bytes, str]],
    config: ModelConfig,
) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    content: list[dict] = []
    for img_bytes, media_type in images:
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": to_base64(img_bytes),
                },
            }
        )
    content.append({"type": "text", "text": user_prompt})

    if config.extended_thinking:
        response = client.beta.messages.create(
            model=config.model,
            max_tokens=max(config.max_tokens, config.thinking_budget + 2048),
            system=system_prompt,
            messages=[{"role": "user", "content": content}],
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            betas=["interleaved-thinking-2025-05-14"],
        )
    else:
        response = client.messages.create(
            model=config.model,
            max_tokens=config.max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": content}],
        )
    # return only the text block (thinking blocks are internal reasoning)
    for block in response.content:
        if block.type == "text":
            return block.text
    return response.content[0].text


def config_from_env() -> ModelConfig:
    provider = os.environ.get("LLM_PROVIDER", "ollama")
    if provider == "ollama":
        return ModelConfig(
            provider="ollama",
            model=os.environ.get("OLLAMA_MODEL", "llama3.2-vision:11b"),
            base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
        )
    if provider == "claude":
        thinking = os.environ.get("EXTENDED_THINKING", "false").lower() == "true"
        budget = int(os.environ.get("THINKING_BUDGET_TOKENS", "8000"))
        return ModelConfig(
            provider="claude",
            model=os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6"),
            extended_thinking=thinking,
            thinking_budget=budget,
        )
    raise ValueError(f"Unknown LLM_PROVIDER: {provider}")
