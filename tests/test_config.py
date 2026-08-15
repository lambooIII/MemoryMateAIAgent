import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_default_storage_uses_memory() -> None:
    settings = Settings(_env_file=None)

    assert settings.short_term_memory_backend == "memory"
    assert settings.long_term_memory_backend == "memory"
    assert settings.vector_store_backend == "memory"
    assert not settings.model_configured


def test_rejects_invalid_chunk_overlap() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            rag_chunk_size=200,
            rag_chunk_overlap=200,
        )
