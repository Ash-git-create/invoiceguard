from __future__ import annotations
from typing import List, Literal
from pydantic import BaseModel, Field, field_validator


class LineItem(BaseModel):
    description: str = ""
    quantity: float = 1.0
    unit_price: float = 0.0
    total: float = 0.0


class FormatterResponse(BaseModel):
    vendor_name: str = ""
    vendor_id: str = ""
    invoice_number: str = ""
    invoice_date: str = ""
    due_date: str = ""
    line_items: List[LineItem] = Field(default_factory=list)
    subtotal: float = 0.0
    tax: float = 0.0
    grand_total: float = 0.0
    currency: str = "USD"
    payment_terms: str = ""
    math_valid: bool = True
    math_notes: str = ""


class ServiceVerdict(BaseModel):
    description: str = ""
    approved: bool = True
    reason: str = ""
    severity: Literal["info", "warning", "critical"] = "info"


class ServiceCheckResponse(BaseModel):
    verdicts: List[ServiceVerdict] = Field(default_factory=list)
    vendor_approved: bool = True
    vendor_reason: str = ""
    summary: str = ""


class Anomaly(BaseModel):
    type: str = ""
    description: str = ""
    severity: Literal["info", "warning", "critical"] = "info"
    reasoning: str = ""


class AnomalyCheckResponse(BaseModel):
    anomalies: List[Anomaly] = Field(default_factory=list)
    summary: str = ""


class PatternFlag(BaseModel):
    reason: str = ""
    severity: Literal["info", "warning", "critical"] = "info"


class PatternRecognitionResponse(BaseModel):
    pattern_insights: str = ""
    trend_analysis: str = ""
    recommendations: List[str] = Field(default_factory=list)
    price_change_pct: float = 0.0
    new_line_items: List[str] = Field(default_factory=list)
    removed_line_items: List[str] = Field(default_factory=list)
    reliability_score: float = 1.0
    flags: List[PatternFlag] = Field(default_factory=list)


class DecisionFlag(BaseModel):
    agent: str = ""
    reason: str = ""
    severity: Literal["info", "warning", "critical"] = "info"


class DecisionAgentResponse(BaseModel):
    verdict: Literal["approved", "flagged", "rejected", "requires_human"]
    summary: str = ""
    reasoning: str = ""
    flags: List[DecisionFlag] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    pattern_insights: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    @field_validator("verdict", mode="before")
    @classmethod
    def coerce_verdict(cls, v: str) -> str:
        valid = {"approved", "flagged", "rejected", "requires_human"}
        if v not in valid:
            return "requires_human"
        return v
