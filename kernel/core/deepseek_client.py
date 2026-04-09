from __future__ import annotations

import os
from typing import AsyncIterator, List, Optional

from loguru import logger
from openai import AsyncOpenAI

class DeepSeekClient:
    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY", ""),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
        )

    async def generate(
        self,
        messages: List[dict],
        model_name: str = "deepseek-v3",
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> Optional[str]:
        response = await self._client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        usage = response.usage
        if usage:
            logger.debug(
                f"[DeepSeek] usage | model={model_name} | "
                f"in={usage.prompt_tokens} | out={usage.completion_tokens}"
            )

        content = response.choices[0].message.content if response.choices else None
        return content

    async def stream(
        self,
        messages: List[dict],
        model_name: str = "deepseek-v3",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        stream = await self._client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )

        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content

deepseek_client = DeepSeekClient()
