from contextlib import ExitStack
from typing import Any

from app.core.config import Settings


class StorageConfigurationError(RuntimeError):
    pass


class MemoryResources:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._stack = ExitStack()
        self.checkpointer: Any = None
        self.store: Any = None

    def open(self) -> "MemoryResources":
        self.checkpointer = self._create_checkpointer()
        self.store = self._create_store()
        return self

    def close(self) -> None:
        self._stack.close()

    def _create_checkpointer(self) -> Any:
        if self.settings.short_term_memory_backend == "memory":
            from langgraph.checkpoint.memory import InMemorySaver

            return InMemorySaver()

        self._require_postgres_uri()
        from langgraph.checkpoint.postgres import PostgresSaver

        checkpointer = self._stack.enter_context(
            PostgresSaver.from_conn_string(self.settings.postgres_uri)
        )
        checkpointer.setup()
        return checkpointer

    def _create_store(self) -> Any:
        if self.settings.long_term_memory_backend == "memory":
            from langgraph.store.memory import InMemoryStore

            return InMemoryStore()

        self._require_postgres_uri()
        from langgraph.store.postgres import PostgresStore

        store = self._stack.enter_context(
            PostgresStore.from_conn_string(self.settings.postgres_uri)
        )
        store.setup()
        return store

    def _require_postgres_uri(self) -> None:
        if not self.settings.postgres_uri:
            raise StorageConfigurationError(
                "选择 PostgreSQL 记忆后端时必须填写 POSTGRES_URI"
            )

