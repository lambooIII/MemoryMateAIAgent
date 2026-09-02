from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "MemoryMate AI"
    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    log_level: str = "INFO"

    model_provider: Literal["openai_compatible", "deepseek", "ollama"] = "openai_compatible"
    model_name: str = ""
    model_api_key: str = ""
    model_base_url: str = ""
    model_temperature: float = Field(default=0.2, ge=0, le=2)

    embedding_provider: Literal["openai_compatible", "ollama"] = "openai_compatible"
    embedding_model: str = "Pro/BAAI/bge-m3"
    embedding_api_key: str = ""
    embedding_base_url: str = "https://api.siliconflow.cn/v1"
    embedding_dimension: int = Field(default=1024, gt=0)

    short_term_memory_backend: Literal["memory", "postgres"] = "memory"
    long_term_memory_backend: Literal["memory", "postgres"] = "memory"
    vector_store_backend: Literal["memory", "milvus"] = "memory"
    enable_knowledge_graph: bool = True
    enable_graph_extraction: bool = True
    graph_database_path: Path = PROJECT_ROOT / "data" / "knowledge_graph.db"
    graph_max_depth: int = Field(default=3, ge=1, le=5)
    postgres_uri: str = ""
    milvus_uri: str = "http://localhost:19530"
    milvus_token: str = ""
    milvus_database: str = "course_agent"
    milvus_collection: str = "knowledge_chunks"

    enable_rag: bool = True
    auto_ingest_local_knowledge: bool = True
    enable_web_search: bool = False
    tavily_api_key: str = ""
    enable_summarization: bool = False
    summary_trigger_messages: int = Field(default=12, ge=4)
    summary_keep_messages: int = Field(default=6, ge=2)
    enable_pii_protection: bool = False

    langsmith_tracing: bool = False
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_api_key: str = ""
    langsmith_project: str = "course-agent-mvp"

    rag_top_k: int = Field(default=4, ge=1, le=20)
    rag_chunk_size: int = Field(default=500, ge=100)
    rag_chunk_overlap: int = Field(default=100, ge=0)
    knowledge_dir: Path = PROJECT_ROOT / "knowledge"

    @model_validator(mode="after")
    def resolve_paths(self) -> "Settings":
        if not self.knowledge_dir.is_absolute():
            self.knowledge_dir = PROJECT_ROOT / self.knowledge_dir
        if not self.graph_database_path.is_absolute():
            self.graph_database_path = PROJECT_ROOT / self.graph_database_path
        if self.rag_chunk_overlap >= self.rag_chunk_size:
            raise ValueError("RAG_CHUNK_OVERLAP must be smaller than RAG_CHUNK_SIZE")
        return self

    @property
    def model_configured(self) -> bool:
        if self.model_provider == "ollama":
            return bool(self.model_name)
        return bool(self.model_name and self.model_api_key)

    @property
    def embedding_configured(self) -> bool:
        if self.embedding_provider == "ollama":
            return bool(self.embedding_model)
        return bool(self.embedding_model and self.embedding_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
