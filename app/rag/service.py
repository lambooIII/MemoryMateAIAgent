import hashlib
import json
import re
import shutil
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

    @staticmethod
    def infer_subject_id(text: str) -> str | None:
        """Extract a person's name from explicit resume/profile fields."""
        field_match = re.search(r"(?m)^\s*(?:[-*]\s*)?姓名\s*[：:]\s*([^\n｜|,，;；]{2,40})\s*$", text)
        if field_match:
            return field_match.group(1).strip()
        heading_match = re.search(
            r"(?m)^#{1,6}\s+([^\n（(｜|—-]{2,40})(?:（[^）]+）|\([^)]*\))?\s*[｜|—-]+\s*个人信息\s*$",
            text,
        )
        return heading_match.group(1).strip() if heading_match else None

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

    def graph(self, subject_id: str = "all") -> dict[str, list[dict[str, Any]]]:
        """Build a lightweight people graph from persisted local knowledge folders."""
        self.settings.knowledge_dir.mkdir(parents=True, exist_ok=True)
        nodes: list[dict[str, Any]] = []
        relations: dict[str, str] = {}
        self_ids: list[str] = []
        for directory in sorted(self.settings.knowledge_dir.iterdir()):
            if not directory.is_dir() or directory.name.startswith("."):
                continue
            if subject_id not in {"", "all", "全部"} and directory.name != subject_id:
                continue
            paths = [path for path in directory.rglob("*") if path.is_file() and path.suffix.lower() in self.SUPPORTED_SUFFIXES]
            if not paths:
                continue
            graph_config_path = directory / ".graph.json"
            graph_config: dict[str, Any] = {}
            if graph_config_path.is_file():
                try:
                    graph_config = json.loads(graph_config_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    graph_config = {}
            show_relation = graph_config.get("show_relation", True)
            show_relation_in_details = graph_config.get("show_relation_in_details", True)
            notes = []
            full_texts: list[str] = []
            for path in sorted(paths, reverse=True)[:8]:
                text = path.read_text(encoding="utf-8")
                full_texts.append(text)
                display_text = text
                if not show_relation_in_details:
                    display_text = re.sub(r"(?m)^-\s*关系\s*[：:].*\r?\n?", "", display_text)
                notes.append({"source": path.name, "content": display_text})
            combined_text = "\n".join(full_texts)
            relation_match = re.search(r"(?m)^-\s*关系\s*[：:]\s*(.+?)\s*$", combined_text)
            if relation_match and show_relation:
                relation = relation_match.group(1).strip()
                relations[directory.name] = re.sub(r"[（(][^）)]*[）)]", "", relation).strip() or relation
            is_self = "个人信息" in combined_text and directory.name in combined_text
            if is_self:
                self_ids.append(directory.name)
            nodes.append({"id": directory.name, "label": directory.name, "notes": notes, "is_self": is_self})

        node_ids = {node["id"] for node in nodes}
        self_id = next((item for item in self_ids if item in node_ids), None)
        edges = [
            {"source": self_id, "target": node_id, "label": relation}
            for node_id, relation in relations.items()
            if self_id and node_id in node_ids and node_id != self_id
        ]
        return {"nodes": nodes, "edges": edges}

    def delete_subject(self, subject_id: str) -> int:
        if subject_id in {"", "all", "全部"}:
            raise ValueError("不能删除全部对象")
        safe_subject_id = re.sub(r"[^\w-]+", "_", subject_id, flags=re.UNICODE).strip("_") or "general"
        directory = self.settings.knowledge_dir / safe_subject_id
        removed_chunks = self.repository.delete_subject(subject_id)
        if directory.exists():
            shutil.rmtree(directory)
        return removed_chunks

    def merge_subject(self, source_subject_id: str, target_subject_id: str) -> int:
        if source_subject_id in {"", "all", "全部"} or target_subject_id in {"", "all", "全部"}:
            raise ValueError("全部对象不能作为合并来源或目标")
        if source_subject_id == target_subject_id:
            raise ValueError("合并来源和目标不能相同")
        safe_source_id = re.sub(r"[^\w-]+", "_", source_subject_id, flags=re.UNICODE).strip("_")
        source_directory = self.settings.knowledge_dir / (safe_source_id or "general")
        if not source_directory.is_dir():
            raise ValueError(f"来源对象“{source_subject_id}”不存在")
        target_directory = self.subject_directory(target_subject_id)
        merged_paths: list[Path] = []
        for path in sorted(source_directory.iterdir()):
            if not path.is_file() or path.suffix.lower() not in self.SUPPORTED_SUFFIXES:
                continue
            target = target_directory / f"merged_{safe_source_id}_{uuid4().hex[:8]}_{path.name}"
            text = path.read_text(encoding="utf-8")
            text = text.replace(f"# {source_subject_id}的", f"# {target_subject_id}的")
            text = text.replace(f"- 对象 ID：{source_subject_id}", f"- 对象 ID：{target_subject_id}")
            target.write_text(text, encoding="utf-8")
            merged_paths.append(target)

        archive_root = self.settings.knowledge_dir.parent / ".temp" / "trash" / "merged-subjects"
        archive_root.mkdir(parents=True, exist_ok=True)
        archive_directory = archive_root / f"{safe_source_id}_{datetime.now():%Y%m%d_%H%M%S}_{uuid4().hex[:8]}"
        shutil.move(str(source_directory), str(archive_directory))
        self.repository.delete_subject(source_subject_id)
        return self.ingest_paths(merged_paths, target_subject_id) if merged_paths else 0

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
