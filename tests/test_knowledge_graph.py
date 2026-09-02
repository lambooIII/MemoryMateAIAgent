from pathlib import Path
from uuid import uuid4

from app.graph.extraction import GraphExtractor
from app.graph.repository import SQLiteGraphRepository
from app.graph.service import KnowledgeGraphService


def create_graph_service() -> KnowledgeGraphService:
    test_root = Path(__file__).resolve().parents[1] / ".temp" / "test-runs" / uuid4().hex
    return KnowledgeGraphService(
        SQLiteGraphRepository(test_root / "knowledge_graph.db"),
        GraphExtractor(),
    )


def test_ingest_explicit_department_and_aggregate_people() -> None:
    service = create_graph_service()
    try:
        fixtures = {
            "a.md": "- 姓名：张三\n- 所在部门：财务部",
            "b.md": "- 姓名：李四\n- 所在部门：财务部",
        }
        for filename, text in fixtures.items():
            service.ingest_document(Path(filename), text, Path(filename).stem)

        result = service.repository.aggregate("财务部", "任职于", "person")

        assert result["count"] == 2
        assert result["members"] == ["张三", "李四"]
        assert all(item["evidence"] for item in result["evidence"])
    finally:
        service.close()


def test_unchanged_document_is_idempotent() -> None:
    service = create_graph_service()
    try:
        path = Path("person.md")
        text = "- 姓名：张三\n- 部门：财务部"

        first_count = service.ingest_document(path, text, "张三")
        second_count = service.ingest_document(path, text, "张三")

        assert first_count > 0
        assert second_count == 0
        assert service.repository.aggregate("财务部")["count"] == 1
    finally:
        service.close()


def test_find_three_hop_path_with_evidence() -> None:
    service = create_graph_service()
    try:
        repository = service.repository
        document_id, _ = repository.prepare_document("relations.md", "general", "hash")
        person = repository.upsert_entity("张三", "person")
        department = repository.upsert_entity("财务部", "department")
        manager = repository.upsert_entity("李经理", "person")
        location = repository.upsert_entity("A座301", "location")
        repository.add_relation(person, "任职于", department, document_id, "张三在财务部工作", 1.0)
        repository.add_relation(department, "负责人", manager, document_id, "财务部负责人是李经理", 1.0)
        repository.add_relation(manager, "办公地点", location, document_id, "李经理在A座301办公", 1.0)

        paths = repository.find_paths("张三", "A座301", max_depth=3)

        assert len(paths) == 1
        assert [edge["predicate"] for edge in paths[0]] == ["任职于", "负责人", "办公地点"]
        assert all(edge["evidence"] for edge in paths[0])
    finally:
        service.close()


def test_graph_visualization_contains_typed_entities_and_evidence() -> None:
    service = create_graph_service()
    try:
        service.ingest_document(
            Path("profile.md"),
            "- 姓名：张三\n- 工作单位：示例公司\n- 工作地址：科技园1号",
            "张三",
        )

        graph = service.graph()

        types = {node["label"]: node["entity_type"] for node in graph["nodes"]}
        assert types == {"张三": "person", "示例公司": "organization", "科技园1号": "location"}
        assert {edge["label"] for edge in graph["edges"]} == {"任职于", "工作地点"}
        assert all(edge["evidence"] for edge in graph["edges"])
    finally:
        service.close()
