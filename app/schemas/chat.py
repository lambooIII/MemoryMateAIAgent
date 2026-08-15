from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)
    thread_id: str = Field(default="default-thread", min_length=1, max_length=128)
    user_id: str = Field(default="anonymous", min_length=1, max_length=128)


class SourceReference(BaseModel):
    source: str
    chunk_id: str
    score: float | None = None


class ChatResponse(BaseModel):
    answer: str
    thread_id: str
    user_id: str
    sources: list[SourceReference] = Field(default_factory=list)


class StatusResponse(BaseModel):
    status: str
    configured: bool
    capabilities: dict[str, Any]


class UserProfile(BaseModel):
    """Agent tool schema for durable user facts."""

    name: str | None = Field(default=None, description="用户姓名")
    occupation: str | None = Field(default=None, description="用户职业")
    preferences: list[str] = Field(default_factory=list, description="用户明确表达的偏好")

