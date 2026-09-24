import httpx
import pytest

from opportunity_api.clients.apify import ApifyClient
from opportunity_api.clients.openrouter import OpenRouterClient
from opportunity_api.config import Settings


@pytest.mark.asyncio
async def test_openrouter_requires_key() -> None:
    client = OpenRouterClient(Settings(openrouter_api_key=""))
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        await client.complete([{"role": "user", "content": "test"}])
    await client.close()


@pytest.mark.asyncio
async def test_openrouter_structured_completion_and_embedding_contracts() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/chat/completions"):
            return httpx.Response(
                200,
                json={
                    "model": "model/primary",
                    "choices": [{"message": {"content": "{}"}}],
                },
            )
        return httpx.Response(
            200,
            json={"model": "embed/model", "data": [{"embedding": [0.1, 0.2]}]},
        )

    settings = Settings(
        openrouter_api_key="token",
        openrouter_base_url="https://openrouter.test/api/v1",
        embedding_dimensions=2,
    )
    client = OpenRouterClient(settings, transport=httpx.MockTransport(handler))
    await client.complete(
        [{"role": "user", "content": "test"}],
        models=["model/backup"],
        response_format={"type": "json_schema", "json_schema": {"name": "test"}},
    )
    await client.embed("document", model="embed/model", dimensions=2)
    completion = __import__("json").loads(requests[0].content)
    embedding = __import__("json").loads(requests[1].content)
    assert completion["models"] == ["model/backup"]
    assert completion["provider"] == {"require_parameters": True}
    assert embedding["dimensions"] == 2
    assert embedding["input_type"] == "search_document"
    await client.close()


@pytest.mark.asyncio
async def test_apify_actor_contract() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/acts/reddit~run/runs"
        return httpx.Response(201, json={"data": {"id": "run-1"}})

    settings = Settings(apify_api_token="token", apify_base_url="https://api.apify.test/v2")
    client = ApifyClient(settings, transport=httpx.MockTransport(handler))
    result = await client.start_actor("reddit/run", {"queries": ["manual reconciliation"]})
    assert result["id"] == "run-1"
    await client.close()


@pytest.mark.asyncio
async def test_apify_dataset_pagination() -> None:
    offsets: list[int] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params["offset"])
        offsets.append(offset)
        page = [{"id": offset}, {"id": offset + 1}] if offset == 0 else [{"id": offset}]
        return httpx.Response(200, json=page)

    settings = Settings(apify_api_token="token", apify_base_url="https://api.apify.test/v2")
    client = ApifyClient(settings, transport=httpx.MockTransport(handler))
    items = await client.get_dataset_items("dataset-1", page_size=2)
    assert [item["id"] for item in items] == [0, 1, 2]
    assert offsets == [0, 2]
    await client.close()
