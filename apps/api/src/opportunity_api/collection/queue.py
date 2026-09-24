from arq import create_pool
from arq.connections import RedisSettings

from opportunity_api.config import get_settings


async def enqueue_job(function: str, *args: str) -> str | None:
    settings = get_settings()
    redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        job = await redis.enqueue_job(function, *args)
        return job.job_id if job else None
    finally:
        await redis.aclose()
