import hashlib
from pathlib import Path
from typing import Any

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import Settings
from app.models.factory import create_embedding_model
from app.rag.repository import KnowledgeChunk, VectorRepository


class RagService:
    SUPPORTED_SUFFIXES = {".txt", ".md"}

    def __init__(self, settings: Settings, repository: VectorRepository) -> None:
        self.settings = settings
        self.repository = repository
        self._embeddings: Any = None
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.rag_chunk_size,
            chunk_overlap=settings.rag_chunk_overlap,
            separators=["\n==============================\n", "\n\n", "\n", "。", " ", ""],
        )

    @property
    def embeddings(self) -> Any:
        if self._embeddings is None:
            self._embeddings = create_embedding_model(self.settings)
        return self._embeddings

    def ingest_directory(self, directory: Path | None = None) -> int:
        source_directory = directory or self.settings.knowledge_dir
        source_directory.mkdir(parents=True, exist_ok=True)
        paths = [
            path
            for path in source_directory.rglob("*")
            if path.is_file() and path.suffix.lower() in self.SUPPORTED_SUFFIXES
        ]
        return self.ingest_paths(paths)

    def ingest_paths(self, paths: list[Path]) -> int:
        documents: list[Document] = []
        for path in paths:
            if path.suffix.lower() not in self.SUPPORTED_SUFFIXES:
                raise ValueError(f"暂不支持文件类型：{path.suffix}")
            text = path.read_text(encoding="utf-8")
            documents.append(Document(page_content=text, metadata={"source": str(path)}))

        split_documents = self._splitter.split_documents(documents)
        chunks = []
        for index, document in enumerate(split_documents):
            source = document.metadata.get("source", "unknown")
            digest = hashlib.sha256(
                f"{source}:{index}:{document.page_content}".encode("utf-8")
            ).hexdigest()[:24]
            chunks.append(
                KnowledgeChunk(
                    chunk_id=digest,
                    text=document.page_content,
                    source=source,
                )
            )
        vectors = self.embeddings.embed_documents([chunk.text for chunk in chunks]) if chunks else []
        return self.repository.upsert(chunks, vectors)

    def search(self, query: str, limit: int | None = None) -> list[KnowledgeChunk]:
        vector = self.embeddings.embed_query(query)
        return self.repository.search(vector, limit or self.settings.rag_top_k)

    def format_context(self, query: str) -> str:
        hits = self.search(query)
        if not hits:
            return "知识库中没有检索到相关内容。"
        blocks = []
        for index, hit in enumerate(hits, start=1):
            score = f"{hit.score:.4f}" if hit.score is not None else "unknown"
            blocks.append(
                f"[片段{index} | source={hit.source} | chunk_id={hit.chunk_id} | score={score}]\n{hit.text}"
            )
        return "\n\n".join(blocks)

    def count(self) -> int:
        return self.repository.count()

