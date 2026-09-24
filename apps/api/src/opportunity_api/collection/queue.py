from opportunity_api.jobs import enqueue


async def enqueue_job(function: str, *args: str) -> str | None:
    job = await enqueue(function, *args)
    return str(job.id)
