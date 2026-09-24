import base64
import json
from typing import Any

import httpx

from opportunity_api.config import Settings


class ApifyClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.client = httpx.AsyncClient(
            base_url=settings.apify_base_url,
            headers={"Authorization": f"Bearer {settings.apify_api_token}"},
            timeout=90,
            transport=transport,
        )

    @property
    def configured(self) -> bool:
        return bool(self.settings.apify_api_token)

    async def start_actor(
        self,
        actor_id: str,
        actor_input: dict[str, Any],
        *,
        webhook_url: str = "",
    ) -> dict[str, Any]:
        if not self.configured:
            raise RuntimeError("APIFY_API_TOKEN is not configured")
        actor_path_id = actor_id.replace("/", "~", 1)
        params: dict[str, str] = {}
        if webhook_url:
            webhooks = [
                {
                    "eventTypes": [
                        "ACTOR.RUN.SUCCEEDED",
                        "ACTOR.RUN.FAILED",
                        "ACTOR.RUN.ABORTED",
                        "ACTOR.RUN.TIMED_OUT",
                    ],
                    "requestUrl": webhook_url,
                    "payloadTemplate": (
                        '{"eventType":"{{eventType}}","eventData":'
                        '{"actorRunId":"{{resource.id}}"},"resource":{{resource}}}'
                    ),
                }
            ]
            encoded = base64.b64encode(json.dumps(webhooks).encode()).decode()
            params["webhooks"] = encoded
        response = await self.client.post(
            f"/acts/{actor_path_id}/runs", json=actor_input, params=params
        )
        response.raise_for_status()
        return response.json()["data"]

    async def get_run(self, run_id: str) -> dict[str, Any]:
        response = await self.client.get(f"/actor-runs/{run_id}")
        response.raise_for_status()
        return response.json()["data"]

    async def get_dataset_items(
        self, dataset_id: str, *, page_size: int = 1000
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        offset = 0
        while True:
            response = await self.client.get(
                f"/datasets/{dataset_id}/items",
                params={"clean": "true", "offset": offset, "limit": page_size},
            )
            response.raise_for_status()
            page = response.json()
            items.extend(page)
            if len(page) < page_size:
                return items
            offset += len(page)

    async def close(self) -> None:
        await self.client.aclose()
