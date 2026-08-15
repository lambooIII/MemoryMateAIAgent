from app.rag.repository import InMemoryVectorRepository, KnowledgeChunk


def test_memory_repository_returns_most_similar_chunk() -> None:
    repository = InMemoryVectorRepository()
    repository.upsert(
        [
            KnowledgeChunk(chunk_id="memory", text="短期记忆", source="course.md"),
            KnowledgeChunk(chunk_id="rag", text="向量检索", source="course.md"),
        ],
        [[1.0, 0.0], [0.0, 1.0]],
    )

    results = repository.search([0.1, 0.9], limit=1)

    assert results[0].chunk_id == "rag"
    assert results[0].score is not None
    assert repository.count() == 2

