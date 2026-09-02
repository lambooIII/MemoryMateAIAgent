"""Run deterministic GraphRAG checks on the synthetic evaluation corpus."""

from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.graph.extraction import GraphExtractor
from app.graph.repository import SQLiteGraphRepository
from app.graph.service import KnowledgeGraphService


CORPUS = ROOT / "tests" / "evaluation" / "knowledge"


def main() -> None:
    database = ROOT / ".temp" / "evaluation" / f"graph_{uuid4().hex}.db"
    database.parent.mkdir(parents=True, exist_ok=True)
    service = KnowledgeGraphService(SQLiteGraphRepository(database), GraphExtractor())
    try:
        for path in sorted(CORPUS.glob("*.md")):
            service.ingest_document(path, path.read_text(encoding="utf-8"), path.stem)

        graph = service.graph()
        aggregate = service.repository.aggregate("财务部", "任职于", "person")
        paths = service.repository.find_paths("张三", "总部 3 楼", max_depth=3)
        print(f"实体数: {len(graph['nodes'])}")
        print(f"关系数: {len(graph['edges'])}")
        print(f"财务部聚合人数: {aggregate['count']}，名单: {', '.join(aggregate['members'])}")
        print(f"张三到总部 3 楼的三跳内路径数: {len(paths)}")
        print("建议记录指标：实体/关系抽取准确率、聚合准确率、路径命中率、证据覆盖率")
    finally:
        service.close()


if __name__ == "__main__":
    main()
