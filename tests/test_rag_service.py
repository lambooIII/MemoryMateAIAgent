from pathlib import Path
from uuid import uuid4

from app.core.config import Settings
from app.rag.repository import InMemoryVectorRepository, KnowledgeChunk
from app.rag.service import RagService


class FakeEmbeddings:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


def test_merge_subject_archives_source_and_updates_graph() -> None:
    test_root = Path(__file__).resolve().parents[1] / ".temp" / "test-runs" / uuid4().hex
    knowledge_dir = test_root / "knowledge"
    source_dir = knowledge_dir / "阿雄"
    source_dir.mkdir(parents=True)
    (source_dir / "profile.md").write_text(
        "# 阿雄的资料\n\n- 对象 ID：阿雄\n\n昵称阿雄，姓名余锡雄。\n",
        encoding="utf-8",
    )
    repository = InMemoryVectorRepository()
    repository.upsert(
        [KnowledgeChunk("old", "阿雄的资料", "profile.md", "阿雄")],
        [[1.0, 0.0]],
    )
    service = RagService(Settings(knowledge_dir=knowledge_dir), repository)
    service._embeddings = FakeEmbeddings()

    chunk_count = service.merge_subject("阿雄", "室友")

    assert chunk_count == 1
    assert not source_dir.exists()
    assert [node["id"] for node in service.graph()["nodes"]] == ["室友"]
    merged_note = next((knowledge_dir / "室友").glob("merged_阿雄_*.md"))
    assert "对象 ID：室友" in merged_note.read_text(encoding="utf-8")
    archives = list((test_root / ".temp" / "trash" / "merged-subjects").glob("阿雄_*"))
    assert len(archives) == 1
    assert (archives[0] / "profile.md").exists()
    assert repository.search([1.0, 0.0], 5, "阿雄") == []
