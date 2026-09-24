from typing import Any

import httpx

from opportunity_api.config import Settings


class OpenRouterClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.client = httpx.AsyncClient(
            base_url=settings.openrouter_base_url,
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://opportunity-os.local",
                "X-Title": "Opportunity Research OS",
            },
            timeout=60,
            transport=transport,
        )

    @property
    def configured(self) -> bool:
        return bool(self.settings.openrouter_api_key)

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        response_format: dict[str, Any] | None = None,
        models: list[str] | None = None,
    ) -> dict[str, Any]:
        if not self.configured:
            raise RuntimeError("OPENROUTER_API_KEY is not configured")
        payload: dict[str, Any] = {
            "model": model or self.settings.openrouter_default_model,
            "messages": messages,
        }
        if response_format:
            payload["response_format"] = response_format
            payload["provider"] = {"require_parameters": True}
        if models:
            payload["models"] = models
        response = await self.client.post("/chat/completions", json=payload)
        response.raise_for_status()
        return response.json()

    async def embed(
        self,
        inputs: str | list[str],
        *,
        model: str | None = None,
        dimensions: int | None = None,
    ) -> dict[str, Any]:
        if not self.configured:
            raise RuntimeError("OPENROUTER_API_KEY is not configured")
        response = await self.client.post(
            "/embeddings",
            json={
                "model": model or self.settings.openrouter_embedding_model,
                "input": inputs,
                "dimensions": dimensions or self.settings.embedding_dimensions,
                "encoding_format": "float",
                "input_type": "search_document",
            },
        )
        response.raise_for_status()
        return response.json()

    async def close(self) -> None:
        await self.client.aclose()
