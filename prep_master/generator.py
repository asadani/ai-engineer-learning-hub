import asyncio
import time
from typing import Callable, Optional, Tuple

import anthropic

from .config import SectionConfig, SECTIONS, MAX_TOKENS, TEMPERATURE
from .prompts import SYSTEM_PROMPT, build_user_prompt


def _retry_generate(fn, retries: int = 3):
    for attempt in range(retries):
        try:
            return fn()
        except anthropic.RateLimitError:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** (attempt + 1))
        except anthropic.APIStatusError as e:
            if attempt == retries - 1:
                raise
            if e.status_code >= 500:
                time.sleep(2 ** (attempt + 1))
            else:
                raise


class Generator:
    def __init__(self, api_key: str, model: str, max_tokens: int = MAX_TOKENS):
        self.client = anthropic.Anthropic(
            api_key=api_key,
            timeout=anthropic.Timeout(60.0, read=180.0),
            max_retries=0,
        )
        self.model = model
        self.max_tokens = max_tokens

    def generate_section(
        self,
        topic: str,
        section: SectionConfig,
        on_progress: Optional[Callable[[int], None]] = None,
    ) -> str:
        user_prompt = build_user_prompt(topic, section)
        chunks = []

        def _do():
            nonlocal chunks
            chunks = []
            with self.client.messages.stream(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
                temperature=TEMPERATURE,
            ) as stream:
                for text in stream.text_stream:
                    chunks.append(text)
                    if on_progress:
                        on_progress(sum(len(c) for c in chunks))

        _retry_generate(_do)
        return "".join(chunks)


class AsyncGenerator:
    def __init__(
        self,
        api_key: str,
        model: str,
        max_tokens: int = MAX_TOKENS,
        max_concurrent: int = 3,
    ):
        self.client = anthropic.AsyncAnthropic(
            api_key=api_key,
            timeout=anthropic.Timeout(60.0, read=180.0),
            max_retries=0,
        )
        self.model = model
        self.max_tokens = max_tokens
        self._sem = asyncio.Semaphore(max_concurrent)

    async def generate_section(
        self,
        topic: str,
        section: SectionConfig,
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> Tuple[SectionConfig, str]:
        user_prompt = build_user_prompt(topic, section)

        async def _do():
            chunks = []
            async with self.client.messages.stream(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
                temperature=TEMPERATURE,
            ) as stream:
                async for text in stream.text_stream:
                    chunks.append(text)
                    if on_progress:
                        on_progress(section.index, sum(len(c) for c in chunks))
            return "".join(chunks)

        async with self._sem:
            for attempt in range(3):
                try:
                    content = await _do()
                    return section, content
                except anthropic.RateLimitError:
                    if attempt == 2:
                        raise
                    await asyncio.sleep(2 ** (attempt + 1))
                except anthropic.APIStatusError as e:
                    if attempt == 2 or e.status_code < 500:
                        raise
                    await asyncio.sleep(2 ** (attempt + 1))

    async def generate_all(
        self,
        topic: str,
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> list[Tuple[SectionConfig, str]]:
        tasks = [self.generate_section(topic, s, on_progress) for s in SECTIONS]
        return await asyncio.gather(*tasks, return_exceptions=True)
