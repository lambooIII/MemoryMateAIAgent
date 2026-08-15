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
    """恋爱对象资料和稳定偏好的结构化输入。"""

    partner_name: str | None = Field(default=None, description="对象姓名")
    birthday: str | None = Field(default=None, description="对象生日，建议使用 YYYY-MM-DD")
    occupation: str | None = Field(default=None, description="对象职业或工作信息")
    preferences: list[str] = Field(default_factory=list, description="对象喜欢的事物")
    dislikes: list[str] = Field(default_factory=list, description="对象不喜欢或需要避开的事物")
    important_dates: dict[str, str] = Field(default_factory=dict, description="纪念日等重要日期")
