"""OpenAI-powered helpers for description generation and reply suggestions."""

from __future__ import annotations

import logging

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


_DESCRIPTION_SYSTEM_PROMPT = (
    "Ты помогаешь продавцу на маркетплейсе FunPay писать продающие описания лотов. "
    "Описание должно быть кратким (3–6 предложений), на русском языке, "
    "без эмодзи-перебора, с понятной структурой: что продаётся, что входит, "
    "условия выдачи и контакта. Не выдумывай факты — используй только то, что "
    "указано в черновике пользователя. Не добавляй ссылки и обещания, которых нет в черновике."
)

_REPLY_SYSTEM_PROMPT = (
    "Ты — менеджер продавца на FunPay. Помоги вежливо ответить покупателю на русском, "
    "коротко (1–3 предложения), доброжелательно, по делу. Не давай гарантий, которых "
    "не было в исходном описании, и не указывай контактные данные."
)


class AIClient:
    """Thin wrapper around the OpenAI async client.

    Constructed lazily — if no API key is configured, the methods raise a
    `RuntimeError` so handlers can show a helpful message to the user.
    """

    def __init__(self, api_key: str | None, model: str):
        self._model = model
        self._client: AsyncOpenAI | None = AsyncOpenAI(api_key=api_key) if api_key else None

    @property
    def is_enabled(self) -> bool:
        return self._client is not None

    async def improve_description(self, draft: str) -> str:
        """Rewrite/improve a lot description draft."""
        return await self._chat(_DESCRIPTION_SYSTEM_PROMPT, draft)

    async def suggest_reply(self, conversation: str) -> str:
        """Suggest a reply to a customer chat snippet."""
        return await self._chat(_REPLY_SYSTEM_PROMPT, conversation)

    async def _chat(self, system: str, user: str) -> str:
        if self._client is None:
            raise RuntimeError("OpenAI API key is not configured (set OPENAI_API_KEY).")
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.6,
        )
        choice = response.choices[0].message.content if response.choices else None
        if not choice:
            raise RuntimeError("OpenAI returned an empty response")
        return choice.strip()
