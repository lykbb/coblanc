from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.contracts import Shot


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["search_assets", "final"]
    kind: Literal["pose", "background"] = "pose"
    tags: list[str] = Field(default_factory=list)
    shot: Shot | None = None
