import json
import re
from typing import Any

from app.graph.models import ExtractedEntity, ExtractedRelation, GraphExtraction


EXTRACTION_PROMPT = """你是知识图谱信息抽取器。请从下面的私人知识文档中提取明确出现的实体和关系。

规则：
1. 实体类型只能是 person、department、organization、location、event、other。
2. 人名使用真实姓名作为规范名称，昵称放入 aliases；不能用“室友”“对象”等关系代替姓名。
3. 关系谓词使用简短中文，例如“任职于”“位于”“负责人”“室友”“同门”“参与”。
4. 只抽取原文明确陈述的事实，不推测隐含关系。
5. 每条关系必须附带支持它的原文 evidence。
6. 文档所属人物是：{subject_id}。如果文档是该人物本人的简历或个人信息，将其 is_self 标记为 true。

文档：
{text}
"""


class GraphExtractor:
    def __init__(self, model: Any | None = None, max_characters: int = 18_000) -> None:
        self.model = model
        self.max_characters = max_characters

    def extract(self, text: str, subject_id: str) -> GraphExtraction:
        deterministic = self._extract_explicit_fields(text, subject_id)
        if self.model is None:
            return deterministic
        extracted = self._extract_with_model(text, subject_id)
        return self._merge(deterministic, extracted)

    def _extract_with_model(self, text: str, subject_id: str) -> GraphExtraction:
        prompt = EXTRACTION_PROMPT.format(subject_id=subject_id, text=text[: self.max_characters])
        try:
            runnable = self.model.with_structured_output(GraphExtraction)
            result = runnable.invoke(prompt)
            return result if isinstance(result, GraphExtraction) else GraphExtraction.model_validate(result)
        except Exception:
            return GraphExtraction()

    @staticmethod
    def _extract_explicit_fields(text: str, subject_id: str) -> GraphExtraction:
        entities: list[ExtractedEntity] = []
        relations: list[ExtractedRelation] = []
        name_match = re.search(r"(?m)^\s*(?:[-*]\s*)?姓名\s*[：:]\s*([^\n｜|,，;；]{2,40})\s*$", text)
        heading_match = re.search(
            r"(?m)^#{1,6}\s+([^\n（(｜|—-]{2,40})(?:（[^）]+）|\([^)]*\))?\s*[｜|—-]+\s*个人信息\s*$",
            text,
        )
        explicit_name = (name_match or heading_match)
        person_name = explicit_name.group(1).strip() if explicit_name else subject_id.strip()
        valid_person = person_name not in {"", "all", "全部", "general"}
        aliases_match = re.search(r"(?m)^\s*(?:[-*]\s*)?(?:昵称|别名)\s*[：:]\s*(.+?)\s*$", text)
        aliases = []
        if aliases_match:
            aliases = [item.strip() for item in re.split(r"[,，、/；;]", aliases_match.group(1)) if item.strip()]
        is_self = bool(heading_match or ("个人信息" in text and valid_person))
        if valid_person:
            entities.append(
                ExtractedEntity(
                    name=person_name,
                    entity_type="person",
                    aliases=aliases,
                    evidence=(name_match.group(0).strip() if name_match else person_name),
                    is_self=is_self,
                )
            )

        field_types = {
            "部门": ("department", "任职于"),
            "所在部门": ("department", "任职于"),
            "任职部门": ("department", "任职于"),
            "工作单位": ("organization", "任职于"),
            "公司": ("organization", "任职于"),
            "工作地址": ("location", "工作地点"),
            "家庭地址": ("location", "居住于"),
            "常用地址": ("location", "常去地点"),
        }
        if valid_person:
            for field, (entity_type, predicate) in field_types.items():
                match = re.search(rf"(?m)^\s*(?:[-*]\s*)?{field}\s*[：:]\s*(.+?)\s*$", text)
                if not match:
                    continue
                target = match.group(1).strip().strip('"“”')
                if not target:
                    continue
                evidence = match.group(0).strip()
                entities.append(ExtractedEntity(name=target, entity_type=entity_type, evidence=evidence))
                relations.append(
                    ExtractedRelation(
                        source=person_name,
                        source_type="person",
                        predicate=predicate,
                        target=target,
                        target_type=entity_type,
                        evidence=evidence,
                    )
                )
        # Handle compact relationship facts such as “财务部负责人：赵经理”.
        relation_patterns = [
            (r"(?m)^\s*(.+?)负责人\s*[：:]\s*(.+?)\s*$", "负责人", "department", "person"),
            (r"(?m)^\s*(.+?)(?:办公地点|办公地址)\s*[：:]\s*(.+?)\s*$", "办公地点", "department", "location"),
        ]
        for pattern, predicate, source_type, target_type in relation_patterns:
            for match in re.finditer(pattern, text):
                source = match.group(1).strip().lstrip("- ")
                target = match.group(2).strip()
                if not source or not target:
                    continue
                evidence = match.group(0).strip()
                entities.extend(
                    [
                        ExtractedEntity(name=source, entity_type=source_type, evidence=evidence),
                        ExtractedEntity(name=target, entity_type=target_type, evidence=evidence),
                    ]
                )
                relations.append(
                    ExtractedRelation(
                        source=source,
                        source_type=source_type,
                        predicate=predicate,
                        target=target,
                        target_type=target_type,
                        evidence=evidence,
                    )
                )
        return GraphExtraction(entities=entities, relations=relations)

    @staticmethod
    def _merge(first: GraphExtraction, second: GraphExtraction) -> GraphExtraction:
        entities: dict[tuple[str, str], ExtractedEntity] = {}
        for entity in [*first.entities, *second.entities]:
            key = (entity.name.strip().lower(), entity.entity_type)
            previous = entities.get(key)
            if previous:
                previous.aliases = list(dict.fromkeys([*previous.aliases, *entity.aliases]))
                previous.is_self = previous.is_self or entity.is_self
                if not previous.evidence:
                    previous.evidence = entity.evidence
            else:
                entities[key] = entity.model_copy(deep=True)
        relations: dict[tuple[str, str, str, str], ExtractedRelation] = {}
        for relation in [*first.relations, *second.relations]:
            key = (
                relation.source.strip().lower(),
                relation.predicate.strip(),
                relation.target.strip().lower(),
                relation.evidence.strip(),
            )
            relations[key] = relation
        return GraphExtraction(entities=list(entities.values()), relations=list(relations.values()))


def extraction_to_json(extraction: GraphExtraction) -> str:
    return json.dumps(extraction.model_dump(), ensure_ascii=False)
