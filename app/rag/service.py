import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

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

    def ingest_directory(self, directory: Path | None = None, subject_id: str = "general") -> int:
        source_directory = directory or self.settings.knowledge_dir
        source_directory.mkdir(parents=True, exist_ok=True)
        paths = [
            path
            for path in source_directory.rglob("*")
            if path.is_file() and path.suffix.lower() in self.SUPPORTED_SUFFIXES
        ]
        return self.ingest_paths(paths, subject_id)

    def restore_local_knowledge(self) -> int:
        self.settings.knowledge_dir.mkdir(parents=True, exist_ok=True)
        total = 0
        root_files = [
            path
            for path in self.settings.knowledge_dir.iterdir()
            if path.is_file() and path.suffix.lower() in self.SUPPORTED_SUFFIXES
        ]
        if root_files:
            total += self.ingest_paths(root_files, "general")
        for subject_directory in self.settings.knowledge_dir.iterdir():
            if not subject_directory.is_dir():
                continue
            paths = [
                path
                for path in subject_directory.rglob("*")
                if path.is_file() and path.suffix.lower() in self.SUPPORTED_SUFFIXES
            ]
            if paths:
                total += self.ingest_paths(paths, subject_directory.name)
        return total

    def subject_directory(self, subject_id: str) -> Path:
        safe_subject_id = re.sub(r"[^\w-]+", "_", subject_id, flags=re.UNICODE).strip("_")
        directory = self.settings.knowledge_dir / (safe_subject_id or "general")
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def ingest_paths(self, paths: list[Path], subject_id: str = "general") -> int:
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
                    subject_id=subject_id,
                )
            )
        vectors = self.embeddings.embed_documents([chunk.text for chunk in chunks]) if chunks else []
        return self.repository.upsert(chunks, vectors)

    def save_memory_note(
        self,
        subject_id: str,
        title: str,
        content: str,
        category: str,
        source: str = "chat",
    ) -> tuple[Path, int]:
        now = datetime.now().astimezone()
        subject_directory = self.subject_directory(subject_id)
        filename = f"{now:%Y%m%d_%H%M%S}_{uuid4().hex[:8]}.md"
        path = subject_directory / filename
        note = (
            f"# {title}\n\n"
            f"- 对象 ID：{subject_id}\n"
            f"- 分类：{category}\n"
            f"- 来源：{source}\n"
            f"- 保存时间：{now.isoformat(timespec='seconds')}\n\n"
            f"{content.strip()}\n"
        )
        path.write_text(note, encoding="utf-8")
        chunk_count = self.ingest_paths([path], subject_id)
        return path, chunk_count

    def list_memory_notes(self, subject_id: str) -> list[dict[str, str]]:
        safe_subject_id = re.sub(r"[^\w-]+", "_", subject_id, flags=re.UNICODE).strip("_")
        subject_directory = self.settings.knowledge_dir / (safe_subject_id or "general")
        if not subject_directory.exists():
            return []
        return [
            {
                "filename": path.name,
                "content": path.read_text(encoding="utf-8"),
                "updated_at": datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(
                    timespec="seconds"
                ),
            }
            for path in sorted(subject_directory.glob("*.md"), reverse=True)
        ]

    def graph(self, subject_id: str = "all") -> dict[str, list[dict[str, str]]]:
        """Build a lightweight people graph from persisted local knowledge folders."""
        self.settings.knowledge_dir.mkdir(parents=True, exist_ok=True)
        nodes: list[dict[str, str]] = []
        for directory in sorted(self.settings.knowledge_dir.iterdir()):
            if not directory.is_dir() or directory.name.startswith("."):
                continue
            if subject_id not in {"", "all", "全部"} and directory.name != subject_id:
                continue
            paths = [path for path in directory.rglob("*") if path.is_file() and path.suffix.lower() in self.SUPPORTED_SUFFIXES]
            if not paths:
                continue
            notes = []
            for path in sorted(paths, reverse=True)[:8]:
                text = path.read_text(encoding="utf-8")
                notes.append({"source": path.name, "content": text[:1200]})
            nodes.append({"id": directory.name, "label": directory.name, "notes": notes})
        return {"nodes": nodes, "edges": []}

    def search(
        self,
        query: str,
        subject_id: str = "general",
        limit: int | None = None,
    ) -> list[KnowledgeChunk]:
        vector = self.embeddings.embed_query(query)
        return self.repository.search(vector, limit or self.settings.rag_top_k, subject_id)

    def format_context(self, query: str, subject_id: str = "general") -> str:
        hits = self.search(query, subject_id)
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
