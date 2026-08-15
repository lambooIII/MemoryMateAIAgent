from app.rag.repository import InMemoryVectorRepository, KnowledgeChunk


def test_memory_repository_returns_most_similar_chunk() -> None:
    repository = InMemoryVectorRepository()
    repository.upsert(
        [
            KnowledgeChunk(
                chunk_id="memory",
                text="妈妈喜欢喝茶",
                source="family.md",
                subject_id="妈妈",
            ),
            KnowledgeChunk(
                chunk_id="rag",
                text="对象不喜欢折耳根",
                source="partner.md",
                subject_id="对象",
            ),
        ],
        [[1.0, 0.0], [0.0, 1.0]],
    )

    results = repository.search([0.1, 0.9], limit=1, subject_id="对象")

    assert results[0].chunk_id == "rag"
    assert results[0].score is not None
    assert repository.count() == 2
