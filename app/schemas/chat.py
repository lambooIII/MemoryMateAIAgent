from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)
    thread_id: str = Field(default="default-thread", min_length=1, max_length=128)
    user_id: str = Field(default="anonymous", min_length=1, max_length=128)
    subject_id: str = Field(default="partner", min_length=1, max_length=128)


class SourceReference(BaseModel):
    source: str
    chunk_id: str
    score: float | None = None


class ChatResponse(BaseModel):
    answer: str
    thread_id: str
    user_id: str
    subject_id: str
    sources: list[SourceReference] = Field(default_factory=list)


class StatusResponse(BaseModel):
    status: str
    configured: bool
    capabilities: dict[str, Any]


class SubjectProfile(BaseModel):
    """任意关系对象的资料和稳定偏好。"""

    relation: str | None = Field(default=None, description="关系类型，例如妈妈、爸爸、对象、前任")
    name: str | None = Field(default=None, description="关系对象姓名")
    birthday: str | None = Field(default=None, description="对象生日，建议使用 YYYY-MM-DD")
    occupation: str | None = Field(default=None, description="对象职业或工作信息")
    preferences: list[str] = Field(default_factory=list, description="对象喜欢的事物")
    dislikes: list[str] = Field(default_factory=list, description="对象不喜欢或需要避开的事物")
    important_dates: dict[str, str] = Field(default_factory=dict, description="纪念日等重要日期")
    category: str = Field(default="general", description="记忆分类，例如基本资料、喜好、雷区、重要事件")
    summary: str | None = Field(default=None, description="需要长期保存的重要事件或补充摘要")
