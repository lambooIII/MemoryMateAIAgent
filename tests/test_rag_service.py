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

    chunk_count = service.merge_subject("阿雄", "余锡雄")

    assert chunk_count == 1
    assert not source_dir.exists()
    assert [node["id"] for node in service.graph()["nodes"]] == ["余锡雄"]
    merged_note = next((knowledge_dir / "余锡雄").glob("merged_阿雄_*.md"))
    assert "对象 ID：余锡雄" in merged_note.read_text(encoding="utf-8")
    archives = list((test_root / ".temp" / "trash" / "merged-subjects").glob("阿雄_*"))
    assert len(archives) == 1
    assert (archives[0] / "profile.md").exists()
    assert repository.search([1.0, 0.0], 5, "阿雄") == []


def test_infer_subject_id_from_resume_heading() -> None:
    text = "## 赖宝泉（男） - 个人信息\n\n## 教育背景"

    assert RagService.infer_subject_id(text) == "赖宝泉"


def test_graph_connects_self_to_people_by_relation() -> None:
    test_root = Path(__file__).resolve().parents[1] / ".temp" / "test-runs" / uuid4().hex
    knowledge_dir = test_root / "knowledge"
    records = {
        "赖宝泉": "## 赖宝泉（男） - 个人信息\n\n个人简历",
        "余锡雄": "- 关系：室友\n- 姓名：余锡雄",
        "况佳元": "- 关系：同门\n- 姓名：况佳元",
        "肖越豪": "- 关系：对象\n- 姓名：肖越豪",
    }
    for subject_id, content in records.items():
        directory = knowledge_dir / subject_id
        directory.mkdir(parents=True)
        (directory / "profile.md").write_text(content, encoding="utf-8")
    service = RagService(Settings(knowledge_dir=knowledge_dir), InMemoryVectorRepository())

    graph = service.graph()

    assert {(edge["target"], edge["label"]) for edge in graph["edges"]} == {
        ("余锡雄", "室友"),
        ("况佳元", "同门"),
        ("肖越豪", "对象"),
    }
