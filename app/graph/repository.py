import json
import sqlite3
from collections import deque
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4


def normalize_entity_name(name: str) -> str:
    return "".join(name.strip().lower().split())


class SQLiteGraphRepository:
    def __init__(self, database_path: Path) -> None:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self.database_path = database_path
        self._lock = RLock()
        self._connection = sqlite3.connect(database_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._create_schema()

    def _create_schema(self) -> None:
        with self._lock, self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS graph_documents (
                    id TEXT PRIMARY KEY,
                    path TEXT NOT NULL UNIQUE,
                    subject_id TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS graph_entities (
                    id TEXT PRIMARY KEY,
                    canonical_name TEXT NOT NULL,
                    normalized_name TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    is_self INTEGER NOT NULL DEFAULT 0,
                    attributes_json TEXT NOT NULL DEFAULT '{}',
                    UNIQUE(normalized_name, entity_type)
                );
                CREATE TABLE IF NOT EXISTS graph_aliases (
                    entity_id TEXT NOT NULL REFERENCES graph_entities(id) ON DELETE CASCADE,
                    alias TEXT NOT NULL,
                    normalized_alias TEXT NOT NULL,
                    UNIQUE(entity_id, normalized_alias)
                );
                CREATE INDEX IF NOT EXISTS idx_graph_aliases_normalized
                    ON graph_aliases(normalized_alias);
                CREATE TABLE IF NOT EXISTS graph_mentions (
                    entity_id TEXT NOT NULL REFERENCES graph_entities(id) ON DELETE CASCADE,
                    document_id TEXT NOT NULL REFERENCES graph_documents(id) ON DELETE CASCADE,
                    evidence TEXT NOT NULL DEFAULT '',
                    UNIQUE(entity_id, document_id, evidence)
                );
                CREATE TABLE IF NOT EXISTS graph_relations (
                    id TEXT PRIMARY KEY,
                    source_entity_id TEXT NOT NULL REFERENCES graph_entities(id) ON DELETE CASCADE,
                    predicate TEXT NOT NULL,
                    target_entity_id TEXT NOT NULL REFERENCES graph_entities(id) ON DELETE CASCADE,
                    document_id TEXT NOT NULL REFERENCES graph_documents(id) ON DELETE CASCADE,
                    evidence TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 1.0,
                    UNIQUE(source_entity_id, predicate, target_entity_id, document_id, evidence)
                );
                CREATE INDEX IF NOT EXISTS idx_graph_relations_source
                    ON graph_relations(source_entity_id);
                CREATE INDEX IF NOT EXISTS idx_graph_relations_target
                    ON graph_relations(target_entity_id);
                """
            )

    def prepare_document(self, path: str, subject_id: str, content_hash: str) -> tuple[str, bool]:
        with self._lock, self._connection:
            existing = self._connection.execute(
                "SELECT id, content_hash, subject_id FROM graph_documents WHERE path = ?", (path,)
            ).fetchone()
            if existing and existing["content_hash"] == content_hash and existing["subject_id"] == subject_id:
                return str(existing["id"]), False
            if existing:
                document_id = str(existing["id"])
                self._connection.execute("DELETE FROM graph_relations WHERE document_id = ?", (document_id,))
                self._connection.execute("DELETE FROM graph_mentions WHERE document_id = ?", (document_id,))
                self._connection.execute(
                    "UPDATE graph_documents SET subject_id = ?, content_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (subject_id, content_hash, document_id),
                )
            else:
                document_id = uuid4().hex
                self._connection.execute(
                    "INSERT INTO graph_documents(id, path, subject_id, content_hash) VALUES (?, ?, ?, ?)",
                    (document_id, path, subject_id, content_hash),
                )
            self._remove_orphan_entities()
            return document_id, True

    def document_id(self, path: str) -> str | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT id FROM graph_documents WHERE path = ?", (path,)
            ).fetchone()
        return str(row["id"]) if row else None

    def upsert_entity(
        self,
        name: str,
        entity_type: str,
        aliases: list[str] | None = None,
        is_self: bool = False,
    ) -> str:
        normalized_name = normalize_entity_name(name)
        with self._lock, self._connection:
            alias_row = self._connection.execute(
                "SELECT entity_id FROM graph_aliases WHERE normalized_alias = ? LIMIT 1",
                (normalized_name,),
            ).fetchone()
            if alias_row:
                entity_id = str(alias_row["entity_id"])
                for alias in aliases or []:
                    normalized_alias = normalize_entity_name(alias)
                    if normalized_alias and normalized_alias != normalized_name:
                        self._connection.execute(
                            "INSERT OR IGNORE INTO graph_aliases(entity_id, alias, normalized_alias) VALUES (?, ?, ?)",
                            (entity_id, alias.strip(), normalized_alias),
                        )
                return entity_id
            row = self._connection.execute(
                "SELECT id FROM graph_entities WHERE normalized_name = ? AND entity_type = ?",
                (normalized_name, entity_type),
            ).fetchone()
            if row:
                entity_id = str(row["id"])
                if is_self:
                    self._connection.execute("UPDATE graph_entities SET is_self = 1 WHERE id = ?", (entity_id,))
            else:
                entity_id = uuid4().hex
                self._connection.execute(
                    "INSERT INTO graph_entities(id, canonical_name, normalized_name, entity_type, is_self) VALUES (?, ?, ?, ?, ?)",
                    (entity_id, name.strip(), normalized_name, entity_type, int(is_self)),
                )
            for alias in aliases or []:
                normalized_alias = normalize_entity_name(alias)
                if normalized_alias and normalized_alias != normalized_name:
                    self._connection.execute(
                        "INSERT OR IGNORE INTO graph_aliases(entity_id, alias, normalized_alias) VALUES (?, ?, ?)",
                        (entity_id, alias.strip(), normalized_alias),
                    )
            return entity_id

    def collapse_alias_entities(self) -> int:
        """Merge person nodes whose canonical name is already an alias of another person."""
        with self._lock, self._connection:
            duplicates = self._connection.execute(
                """
                SELECT duplicate.id duplicate_id, canonical.id canonical_id
                FROM graph_entities duplicate
                JOIN graph_aliases alias ON alias.normalized_alias = duplicate.normalized_name
                JOIN graph_entities canonical ON canonical.id = alias.entity_id
                WHERE duplicate.entity_type = 'person'
                  AND canonical.entity_type = 'person'
                  AND duplicate.id != canonical.id
                """
            ).fetchall()
            for row in duplicates:
                duplicate_id, canonical_id = row["duplicate_id"], row["canonical_id"]
                self._connection.execute(
                    "INSERT OR IGNORE INTO graph_aliases(entity_id, alias, normalized_alias) "
                    "SELECT ?, canonical_name, normalized_name FROM graph_entities WHERE id = ?",
                    (canonical_id, duplicate_id),
                )
                self._connection.execute(
                    "UPDATE OR IGNORE graph_mentions SET entity_id = ? WHERE entity_id = ?",
                    (canonical_id, duplicate_id),
                )
                self._connection.execute(
                    "UPDATE OR IGNORE graph_relations SET source_entity_id = ? WHERE source_entity_id = ?",
                    (canonical_id, duplicate_id),
                )
                self._connection.execute(
                    "UPDATE OR IGNORE graph_relations SET target_entity_id = ? WHERE target_entity_id = ?",
                    (canonical_id, duplicate_id),
                )
                self._connection.execute("DELETE FROM graph_entities WHERE id = ?", (duplicate_id,))
            self._remove_orphan_entities()
            return len(duplicates)

    def add_mention(self, entity_id: str, document_id: str, evidence: str = "") -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT OR IGNORE INTO graph_mentions(entity_id, document_id, evidence) VALUES (?, ?, ?)",
                (entity_id, document_id, evidence.strip()),
            )

    def add_relation(
        self,
        source_entity_id: str,
        predicate: str,
        target_entity_id: str,
        document_id: str,
        evidence: str,
        confidence: float,
    ) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT OR IGNORE INTO graph_relations(
                    id, source_entity_id, predicate, target_entity_id, document_id, evidence, confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    uuid4().hex,
                    source_entity_id,
                    predicate.strip(),
                    target_entity_id,
                    document_id,
                    evidence.strip(),
                    confidence,
                ),
            )

    def find_entity(self, name: str, entity_type: str | None = None) -> dict[str, Any] | None:
        normalized = normalize_entity_name(name)
        parameters: list[Any] = [normalized, normalized]
        type_filter = ""
        if entity_type:
            type_filter = " AND e.entity_type = ?"
            parameters.append(entity_type)
        with self._lock:
            row = self._connection.execute(
                f"""
                SELECT DISTINCT e.* FROM graph_entities e
                LEFT JOIN graph_aliases a ON a.entity_id = e.id
                WHERE (e.normalized_name = ? OR a.normalized_alias = ?){type_filter}
                ORDER BY CASE WHEN e.normalized_name = ? THEN 0 ELSE 1 END
                LIMIT 1
                """,
                [*parameters, normalized],
            ).fetchone()
        return dict(row) if row else None

    def self_entity(self) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM graph_entities WHERE is_self = 1 ORDER BY canonical_name LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def neighbors(
        self,
        entity_name: str,
        predicate: str | None = None,
        direction: str = "both",
    ) -> list[dict[str, Any]]:
        entity = self.find_entity(entity_name)
        if not entity:
            return []
        clauses = []
        parameters: list[Any] = []
        if direction in {"out", "both"}:
            clauses.append(
                """
                SELECT s.canonical_name source, r.predicate, t.canonical_name target,
                       s.entity_type source_type, t.entity_type target_type,
                       d.path source_path, r.evidence, r.confidence
                FROM graph_relations r
                JOIN graph_entities s ON s.id = r.source_entity_id
                JOIN graph_entities t ON t.id = r.target_entity_id
                JOIN graph_documents d ON d.id = r.document_id
                WHERE r.source_entity_id = ?
                """
            )
            parameters.append(entity["id"])
        if direction in {"in", "both"}:
            clauses.append(
                """
                SELECT s.canonical_name source, r.predicate, t.canonical_name target,
                       s.entity_type source_type, t.entity_type target_type,
                       d.path source_path, r.evidence, r.confidence
                FROM graph_relations r
                JOIN graph_entities s ON s.id = r.source_entity_id
                JOIN graph_entities t ON t.id = r.target_entity_id
                JOIN graph_documents d ON d.id = r.document_id
                WHERE r.target_entity_id = ?
                """
            )
            parameters.append(entity["id"])
        if not clauses:
            return []
        query = " UNION ALL ".join(clauses)
        with self._lock:
            rows = [dict(row) for row in self._connection.execute(query, parameters).fetchall()]
        if predicate:
            rows = [row for row in rows if row["predicate"] == predicate]
        return rows

    def aggregate(
        self,
        target_name: str,
        predicate: str | None = None,
        source_type: str | None = "person",
    ) -> dict[str, Any]:
        entity = self.find_entity(target_name)
        if not entity:
            return {"target": target_name, "count": 0, "members": [], "evidence": []}
        conditions = ["r.target_entity_id = ?"]
        parameters: list[Any] = [entity["id"]]
        if predicate:
            conditions.append("r.predicate = ?")
            parameters.append(predicate)
        if source_type:
            conditions.append("s.entity_type = ?")
            parameters.append(source_type)
        with self._lock:
            rows = self._connection.execute(
                f"""
                SELECT DISTINCT s.canonical_name member, r.predicate, d.path source_path, r.evidence
                FROM graph_relations r
                JOIN graph_entities s ON s.id = r.source_entity_id
                JOIN graph_documents d ON d.id = r.document_id
                WHERE {' AND '.join(conditions)}
                ORDER BY s.canonical_name
                """,
                parameters,
            ).fetchall()
        members = sorted({str(row["member"]) for row in rows})
        return {
            "target": entity["canonical_name"],
            "count": len(members),
            "members": members,
            "evidence": [dict(row) for row in rows],
        }

    def find_paths(self, source_name: str, target_name: str, max_depth: int = 3) -> list[list[dict[str, Any]]]:
        source = self.find_entity(source_name)
        target = self.find_entity(target_name)
        if not source or not target:
            return []
        with self._lock:
            rows = [
                dict(row)
                for row in self._connection.execute(
                    """
                    SELECT r.source_entity_id, r.target_entity_id, r.predicate, r.evidence,
                           d.path source_path, s.canonical_name source, t.canonical_name target
                    FROM graph_relations r
                    JOIN graph_entities s ON s.id = r.source_entity_id
                    JOIN graph_entities t ON t.id = r.target_entity_id
                    JOIN graph_documents d ON d.id = r.document_id
                    """
                ).fetchall()
            ]
        adjacency: dict[str, list[tuple[str, dict[str, Any]]]] = {}
        for row in rows:
            adjacency.setdefault(row["source_entity_id"], []).append((row["target_entity_id"], row))
            reverse = {**row, "source": row["target"], "target": row["source"], "predicate": f"反向:{row['predicate']}"}
            adjacency.setdefault(row["target_entity_id"], []).append((row["source_entity_id"], reverse))
        queue = deque([(source["id"], [], {source["id"]})])
        paths: list[list[dict[str, Any]]] = []
        while queue and len(paths) < 10:
            current, path, visited = queue.popleft()
            if len(path) >= max_depth:
                continue
            for next_id, edge in adjacency.get(current, []):
                if next_id in visited:
                    continue
                next_path = [*path, edge]
                if next_id == target["id"]:
                    paths.append(next_path)
                else:
                    queue.append((next_id, next_path, {*visited, next_id}))
        return paths

    def visualization(self) -> dict[str, list[dict[str, Any]]]:
        with self._lock:
            entities = [dict(row) for row in self._connection.execute("SELECT * FROM graph_entities").fetchall()]
            relations = [
                dict(row)
                for row in self._connection.execute(
                    """
                    SELECT r.id, s.canonical_name source, r.predicate label,
                           t.canonical_name target, r.evidence, r.confidence, d.path source_path
                    FROM graph_relations r
                    JOIN graph_entities s ON s.id = r.source_entity_id
                    JOIN graph_entities t ON t.id = r.target_entity_id
                    JOIN graph_documents d ON d.id = r.document_id
                    """
                ).fetchall()
            ]
            mentions = [
                dict(row)
                for row in self._connection.execute(
                    """
                    SELECT e.canonical_name entity_name, d.path source_path, m.evidence
                    FROM graph_mentions m
                    JOIN graph_entities e ON e.id = m.entity_id
                    JOIN graph_documents d ON d.id = m.document_id
                    """
                ).fetchall()
            ]
        notes_by_entity: dict[str, list[dict[str, str]]] = {}
        for mention in mentions:
            notes_by_entity.setdefault(mention["entity_name"], []).append(
                {"source": mention["source_path"], "content": mention["evidence"]}
            )
        nodes = [
            {
                "id": entity["canonical_name"],
                "label": entity["canonical_name"],
                "entity_type": entity["entity_type"],
                "is_self": bool(entity["is_self"]),
                "notes": notes_by_entity.get(entity["canonical_name"], []),
            }
            for entity in entities
        ]
        return {"nodes": nodes, "edges": relations}

    def delete_subject(self, subject_id: str) -> None:
        with self._lock, self._connection:
            document_ids = [
                row["id"]
                for row in self._connection.execute(
                    "SELECT id FROM graph_documents WHERE subject_id = ?", (subject_id,)
                ).fetchall()
            ]
            self._connection.executemany("DELETE FROM graph_documents WHERE id = ?", [(item,) for item in document_ids])
            self._remove_orphan_entities()

    def merge_entities(self, source_name: str, target_name: str) -> None:
        source = self.find_entity(source_name, "person")
        target = self.find_entity(target_name, "person")
        if not source or not target or source["id"] == target["id"]:
            return
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT OR IGNORE INTO graph_aliases(entity_id, alias, normalized_alias) VALUES (?, ?, ?)",
                (target["id"], source["canonical_name"], source["normalized_name"]),
            )
            self._connection.execute(
                "UPDATE OR IGNORE graph_mentions SET entity_id = ? WHERE entity_id = ?",
                (target["id"], source["id"]),
            )
            self._connection.execute(
                "UPDATE OR IGNORE graph_relations SET source_entity_id = ? WHERE source_entity_id = ?",
                (target["id"], source["id"]),
            )
            self._connection.execute(
                "UPDATE OR IGNORE graph_relations SET target_entity_id = ? WHERE target_entity_id = ?",
                (target["id"], source["id"]),
            )
            self._connection.execute("DELETE FROM graph_entities WHERE id = ?", (source["id"],))

    def _remove_orphan_entities(self) -> None:
        self._connection.execute(
            """
            DELETE FROM graph_entities
            WHERE id NOT IN (SELECT entity_id FROM graph_mentions)
              AND id NOT IN (SELECT source_entity_id FROM graph_relations)
              AND id NOT IN (SELECT target_entity_id FROM graph_relations)
            """
        )

    def close(self) -> None:
        with self._lock:
            self._connection.close()
