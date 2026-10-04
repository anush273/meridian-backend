from typing import Any

from pydantic import BaseModel, Field

class RealtimeMessage(BaseModel):
    type: str
    sequence: int = Field(ge=0)
    data: dict[str,Any] = Field(default_factory=dict)