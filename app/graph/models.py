from typing import Literal

from pydantic import BaseModel, Field


EntityType = Literal["person", "department", "organization", "location", "event", "other"]


class ExtractedEntity(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    entity_type: EntityType = "other"
    aliases: list[str] = Field(default_factory=list)
    evidence: str = Field(default="", max_length=1000)
    is_self: bool = False


class ExtractedRelation(BaseModel):
    source: str = Field(min_length=1, max_length=128)
    source_type: EntityType = "other"
    predicate: str = Field(min_length=1, max_length=64)
    target: str = Field(min_length=1, max_length=128)
    target_type: EntityType = "other"
    evidence: str = Field(min_length=1, max_length=1000)
    confidence: float = Field(default=1.0, ge=0, le=1)


class GraphExtraction(BaseModel):
    entities: list[ExtractedEntity] = Field(default_factory=list)
    relations: list[ExtractedRelation] = Field(default_factory=list)
