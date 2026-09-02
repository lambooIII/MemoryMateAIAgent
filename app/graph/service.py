import hashlib
import json
import re
from pathlib import Path
from typing import Any

from app.graph.extraction import GraphExtractor
from app.graph.models import ExtractedEntity, ExtractedRelation
from app.graph.repository import SQLiteGraphRepository


class KnowledgeGraphService:
    def __init__(self, repository: SQLiteGraphRepository, extractor: GraphExtractor) -> None:
        self.repository = repository
        self.extractor = extractor
        self.repository.collapse_alias_entities()

    def ingest_document(self, path: Path, text: str, subject_id: str) -> int:
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        document_id, changed = self.repository.prepare_document(
            str(path.resolve()), subject_id, content_hash
        )
        if not changed:
            return 0
        extraction = self.extractor.extract(text, subject_id)
        entity_ids: dict[tuple[str, str], str] = {}
        for entity in extraction.entities:
            entity_id = self._save_entity(entity, document_id)
            entity_ids[(entity.name.strip().lower(), entity.entity_type)] = entity_id
        for relation in extraction.relations:
            source_id = self._ensure_relation_entity(relation.source, relation.source_type, document_id, entity_ids)
            target_id = self._ensure_relation_entity(relation.target, relation.target_type, document_id, entity_ids)
            self.repository.add_relation(
                source_id,
                relation.predicate,
                target_id,
                document_id,
                relation.evidence,
                relation.confidence,
            )
        self._save_legacy_relation(text, subject_id, document_id, entity_ids)
        return len(extraction.entities) + len(extraction.relations)

    def _save_entity(self, entity: ExtractedEntity, document_id: str) -> str:
        entity_id = self.repository.upsert_entity(
            entity.name,
            entity.entity_type,
            aliases=entity.aliases,
            is_self=entity.is_self,
        )
        self.repository.add_mention(entity_id, document_id, entity.evidence)
        return entity_id

    def _ensure_relation_entity(
        self,
        name: str,
        entity_type: str,
        document_id: str,
        entity_ids: dict[tuple[str, str], str],
    ) -> str:
        key = (name.strip().lower(), entity_type)
        entity_id = entity_ids.get(key)
        if entity_id:
            return entity_id
        entity_id = self.repository.upsert_entity(name, entity_type)
        self.repository.add_mention(entity_id, document_id)
        entity_ids[key] = entity_id
        return entity_id

    def _save_legacy_relation(
        self,
        text: str,
        subject_id: str,
        document_id: str,
        entity_ids: dict[tuple[str, str], str],
    ) -> None:
        if subject_id in {"", "all", "全部", "general"}:
            return
        relation_match = re.search(r"(?m)^\s*(?:[-*]\s*)?关系\s*[：:]\s*(.+?)\s*$", text)
        self_entity = self.repository.self_entity()
        if not relation_match or not self_entity:
            return
        subject_entity = self.repository.find_entity(subject_id, "person")
        if not subject_entity:
            subject_entity_id = self._ensure_relation_entity(subject_id, "person", document_id, entity_ids)
        else:
            subject_entity_id = str(subject_entity["id"])
        predicate = re.sub(r"[（(][^）)]*[）)]", "", relation_match.group(1)).strip()
        if predicate and subject_entity_id != self_entity["id"]:
            self.repository.add_relation(
                str(self_entity["id"]),
                predicate,
                subject_entity_id,
                document_id,
                relation_match.group(0).strip(),
                1.0,
            )

    def graph(self, subject_id: str = "all") -> dict[str, list[dict[str, Any]]]:
        graph = self.repository.visualization()
        if subject_id in {"", "all", "全部"}:
            return graph
        included = {subject_id}
        for edge in graph["edges"]:
            if edge["source"] == subject_id:
                included.add(edge["target"])
            if edge["target"] == subject_id:
                included.add(edge["source"])
        return {
            "nodes": [node for node in graph["nodes"] if node["id"] in included],
            "edges": [
                edge
                for edge in graph["edges"]
                if edge["source"] in included and edge["target"] in included
            ],
        }

    def reconcile_legacy_relations(self, knowledge_dir: Path) -> None:
        if self.repository.self_entity() is None or not knowledge_dir.is_dir():
            return
        for directory in knowledge_dir.iterdir():
            if not directory.is_dir() or directory.name.startswith("."):
                continue
            for path in directory.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in {".md", ".txt"}:
                    continue
                document_id = self.repository.document_id(str(path.resolve()))
                if document_id:
                    self._save_legacy_relation(
                        path.read_text(encoding="utf-8"), directory.name, document_id, {}
                    )

    def describe_entity(self, entity_name: str, predicate: str | None = None) -> str:
        relations = self.repository.neighbors(entity_name, predicate=predicate)
        if not relations:
            return f"知识图谱中没有找到“{entity_name}”的相关关系。"
        return self._format_relations(relations)

    def aggregate(self, target_name: str, predicate: str | None = None, source_type: str = "person") -> str:
        result = self.repository.aggregate(target_name, predicate, source_type)
        if not result["members"]:
            return f"知识图谱中没有找到指向“{target_name}”且符合条件的实体。"
        evidence = self._format_evidence(result["evidence"])
        return (
            f"图谱聚合结果：{result['target']}共有 {result['count']} 个符合条件的实体："
            f"{', '.join(result['members'])}。\n\n来源证据：\n{evidence}"
        )

    def find_paths(self, source_name: str, target_name: str, max_depth: int = 3) -> str:
        paths = self.repository.find_paths(source_name, target_name, max_depth=max_depth)
        if not paths:
            return f"知识图谱中没有找到“{source_name}”到“{target_name}”的 {max_depth} 跳内路径。"
        blocks = []
        for index, path in enumerate(paths[:5], start=1):
            chain = path[0]["source"]
            for edge in path:
                chain += f" -[{edge['predicate']}]-> {edge['target']}"
            blocks.append(f"路径{index}：{chain}\n{self._format_evidence(path)}")
        return "\n\n".join(blocks)

    def delete_subject(self, subject_id: str) -> None:
        self.repository.delete_subject(subject_id)

    def merge_subject(self, source_subject_id: str, target_subject_id: str) -> None:
        self.repository.merge_entities(source_subject_id, target_subject_id)

    @staticmethod
    def _format_relations(relations: list[dict[str, Any]]) -> str:
        return "\n".join(
            f"- {item['source']} -[{item['predicate']}]-> {item['target']}"
            f"（来源：{Path(item['source_path']).name}；证据：{item['evidence']}）"
            for item in relations
        )

    @staticmethod
    def _format_evidence(items: list[dict[str, Any]]) -> str:
        return "\n".join(
            f"- {Path(item['source_path']).name}：{item['evidence']}"
            for item in items
        )

    def health(self) -> dict[str, str]:
        return {"status": "ready", "database": str(self.repository.database_path)}

    def close(self) -> None:
        self.repository.close()
