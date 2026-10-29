from datetime import date
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field, model_validator
import yaml

class Outcome(str, Enum):
    INCLUDE = "include"
    NEEDS_OFFICIAL_DECISION = "needs_official_decision"
    VERIFY = "verify"

class Condition(BaseModel):
    field: str
    op: Literal["eq", "ne", "gt", "gte", "lt", "lte", "in"]
    value: Any

class Source(BaseModel):
    doc: str
    clause: str
    url: str

class TestVector(BaseModel):
    input: dict[str, Any]
    expect: Outcome

class Rule(BaseModel):
    id: str
    description: str
    when: list[Condition]
    outcome: Outcome
    documents: list[str] = []
    desk: str
    source: Source
    verified_on: date
    verified_by: list[str] = Field(min_length=2)
    expires_on: date
    test_vectors: list[TestVector] = Field(min_length=1)
    
    # --- NEW FIELDS FOR ROUTES ---
    clock_hours: int | None = None  # e.g., 72 for crop loss
    contact: str | None = None      # e.g., "14447" or "Block Officer"

    @model_validator(mode="after")
    def check_dates(self):
        if self.expires_on <= self.verified_on:
            raise ValueError("expires_on must be after verified_on")
        return self

    def is_expired(self, today: date | None = None) -> bool:
        return (today or date.today()) > self.expires_on

class RulePack(BaseModel):
    scheme: str
    state: str
    rules: list[Rule]

def load_pack(path: str) -> RulePack:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return RulePack(**data)

if __name__ == "__main__":
    import sys
    pack = load_pack(sys.argv[1])
    print(f"OK: {pack.scheme}, {len(pack.rules)} rules")