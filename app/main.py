import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.agents.service import AgentService
from app.api.routes import router
from app.core.config import PROJECT_ROOT, get_settings
from app.core.logging import configure_logging
from app.graph.extraction import GraphExtractor
from app.graph.repository import SQLiteGraphRepository
from app.graph.service import KnowledgeGraphService
from app.memory.factory import MemoryResources
from app.models.factory import create_chat_model
from app.rag.repository import create_vector_repository
from app.rag.service import RagService


logger = logging.getLogger(__name__)


def _configure_langsmith() -> None:
    settings = get_settings()
    os.environ["LANGSMITH_TRACING"] = str(settings.langsmith_tracing).lower()
    os.environ["LANGSMITH_ENDPOINT"] = settings.langsmith_endpoint
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    if settings.langsmith_api_key:
        os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    _configure_langsmith()

    memory = MemoryResources(settings).open()
    vector_repository = create_vector_repository(settings)
    chat_model = create_chat_model(settings) if settings.model_configured else None
    graph_service = None
    if settings.enable_knowledge_graph:
        graph_service = KnowledgeGraphService(
            SQLiteGraphRepository(settings.graph_database_path),
            GraphExtractor(chat_model if settings.enable_graph_extraction else None),
        )
    rag_service = RagService(settings, vector_repository, graph_service)
    app.state.settings = settings
    app.state.rag_service = rag_service
    app.state.graph_service = graph_service
    app.state.agent_service = None
    if (
        settings.enable_rag
        and settings.auto_ingest_local_knowledge
        and settings.embedding_configured
    ):
        try:
            restored = rag_service.restore_local_knowledge()
            logger.info("Restored %s local knowledge chunks", restored)
        except Exception:
            logger.exception("Failed to restore local knowledge; the API will remain available")
    if settings.model_configured:
        app.state.agent_service = AgentService(
            settings=settings,
            model=chat_model,
            checkpointer=memory.checkpointer,
            store=memory.store,
            rag_service=rag_service,
        )
    try:
        yield
    finally:
        vector_repository.close()
        if graph_service is not None:
            graph_service.close()
        memory.close()


app = FastAPI(
    title="Course Agent Workspace API",
    version="0.1.0",
    description="LangChain 课程知识点整合的 AI Agent + RAG MVP",
    lifespan=lifespan,
)
app.include_router(router)

web_directory = PROJECT_ROOT / "web"
if web_directory.exists():
    app.mount("/", StaticFiles(directory=web_directory, html=True), name="web")


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run("app.main:app", host=settings.app_host, port=settings.app_port, reload=True)
