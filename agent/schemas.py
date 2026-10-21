from typing import Literal
from pydantic import BaseModel, Field

class Finding(BaseModel):
    rule_id: Literal["ORDER-001", "ORDER-002", "ORDER-003"]
    coverage: Literal["missing", "covered", "uncertain"]
    evidence: list[str] = Field(min_length=1, max_length=8)
    explanation: str = Field(max_length=800)
    implementation: Literal["conforms", "violates", "unknown"] = "unknown"

class Action(BaseModel):
    reason: str = Field(max_length=300, description="Short evidence-based reason for the next action; no private chain of thought")
    tool: Literal["list_endpoints", "search_rules", "inspect_schema", "search_tests", "read_test_file", "run_candidate_test", "assess_coverage", "finish"]
    arguments: dict = Field(default_factory=dict)
    findings: list[Finding] = Field(default_factory=list, max_length=3)
