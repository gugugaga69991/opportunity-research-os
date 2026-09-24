import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from opportunity_api.collection.routes import router as collection_router
from opportunity_api.config import get_settings
from opportunity_api.database import engine
from opportunity_api.decisions.routes import router as decisions_router
from opportunity_api.intelligence.routes import router as intelligence_router
from opportunity_api.learning.routes import router as learning_router
from opportunity_api.logging import configure_logging
from opportunity_api.operations.routes import router as operations_router
from opportunity_api.opportunities.routes import router as opportunities_router
from opportunity_api.processing.routes import router as processing_router
from opportunity_api.research.routes import router as research_router
from opportunity_api.validation.routes import router as validation_router

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("application_started", extra={"environment": settings.app_env})
    yield
    await engine.dispose()


app = FastAPI(title="Opportunity Research OS API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "PUT"],
    allow_headers=["Content-Type"],
)
app.include_router(collection_router)
app.include_router(processing_router)
app.include_router(intelligence_router)
app.include_router(opportunities_router)
app.include_router(research_router)
app.include_router(decisions_router)
app.include_router(validation_router)
app.include_router(learning_router)
app.include_router(operations_router)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.app_env}


@app.get("/ready", tags=["system"])
async def readiness() -> dict[str, object]:
    database_status = "ok"
    try:
        async with engine.connect() as connection:
            await connection.execute(text("select 1"))
    except Exception:
        logger.exception("database_readiness_failed")
        database_status = "unavailable"
    return {
        "status": "ok" if database_status == "ok" else "degraded",
        "database": database_status,
        "openrouter": "configured" if settings.openrouter_api_key else "unconfigured",
        "apify": "configured" if settings.apify_api_token else "unconfigured",
    }
