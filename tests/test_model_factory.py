from app.core.config import Settings
from app.models.factory import create_embedding_model


def test_openai_compatible_embeddings_keep_raw_text() -> None:
    settings = Settings(
        _env_file=None,
        embedding_provider="openai_compatible",
        embedding_model="demo-embedding",
        embedding_api_key="test-key",
        embedding_base_url="https://example.com/v1",
    )

    embeddings = create_embedding_model(settings)

    assert embeddings.check_embedding_ctx_length is False
    assert embeddings.dimensions == 1024
