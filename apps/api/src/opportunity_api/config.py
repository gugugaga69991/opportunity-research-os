from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: str = "development"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"
    database_url: str = "postgresql+asyncpg://opportunity:opportunity@localhost:5432/opportunity_os"
    redis_url: str = "redis://localhost:6379/0"
    openrouter_api_key: str = Field(default="", repr=False)
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_default_model: str = "openai/gpt-4.1-mini"
    openrouter_fallback_models: str = "google/gemini-2.5-flash,anthropic/claude-3.5-haiku"
    openrouter_embedding_model: str = "openai/text-embedding-3-small"
    embedding_dimensions: int = 1536
    near_duplicate_hamming_threshold: int = 3
    semantic_duplicate_threshold: float = 0.94
    processing_batch_size: int = 25
    collection_reconcile_batch_size: int = 20
    clustering_batch_size: int = 50
    cluster_semantic_threshold: float = 0.86
    cluster_high_confidence_threshold: float = 0.92
    opportunity_batch_size: int = 25
    hypothesis_min_signal_count: int = 2
    hypothesis_min_sources: int = 2
    hypothesis_min_evidence_types: int = 2
    hypothesis_min_recurrence: float = 0.5
    research_batch_size: int = 10
    research_min_documents_per_lane: int = 3
    research_max_documents_per_lane: int = 40
    model_retry_limit: int = 3
    decision_batch_size: int = 10
    decision_advance_threshold: float = 70.0
    decision_kill_threshold: float = 40.0
    decision_min_confidence: float = 0.65
    validation_batch_size: int = 10
    validation_min_outreach_sample: int = 50
    validation_strong_positive_rate: float = 0.05
    validation_weak_positive_rate: float = 0.02
    validation_min_pain_confirmations: int = 3
    calibration_min_samples: int = 10
    calibration_max_weight_delta: float = 0.02
    freshness_batch_size: int = 10
    freshness_default_days: int = 60
    freshness_top_opportunity_days: int = 21
    portfolio_high_score_threshold: float = 80.0
    portfolio_score_change_threshold: float = 8.0
    telegram_bot_token: str = Field(default="", repr=False)
    telegram_chat_id: str = ""
    apify_api_token: str = Field(default="", repr=False)
    apify_base_url: str = "https://api.apify.com/v2"
    apify_reddit_actor_id: str = ""
    apify_web_collector_actor_id: str = ""
    apify_research_actor_id: str = ""
    apify_search_discovery_actor_id: str = "apify/google-search-scraper"
    apify_webhook_secret: str = Field(default="change-me", repr=False)
    apify_webhook_url: str = ""

    @property
    def model_route(self) -> list[str]:
        return [
            self.openrouter_default_model,
            *(
                model.strip()
                for model in self.openrouter_fallback_models.split(",")
                if model.strip()
            ),
        ]

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
