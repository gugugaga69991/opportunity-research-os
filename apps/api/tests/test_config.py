from opportunity_api.config import Settings


def test_neon_database_url_is_normalized_for_asyncpg() -> None:
    settings = Settings(
        database_url=(
            "postgresql://role:secret@example.neon.tech/opportunity_research"
            "?sslmode=require&channel_binding=require"
        )
    )

    assert settings.database_url == (
        "postgresql+asyncpg://role:secret@example.neon.tech/opportunity_research?ssl=require"
    )


def test_native_asyncpg_database_url_is_preserved() -> None:
    url = "postgresql+asyncpg://role:secret@localhost:5432/opportunity_research"

    assert Settings(database_url=url).database_url == url
