from __future__ import annotations
from typing import List, Literal, Optional
from pydantic import BaseModel, Field, field_validator

HighlightCategory = Literal[
    "risk_high", 
    "risk_medium",
    "risk_low",   
    "clause_key", 
    "obligation", 
    "party",      
    "date",       
]


class DocumentHighlight(BaseModel):
    id: str = Field(...)
    category: HighlightCategory
    text: str = Field(
        ...,
        max_length=500,
    )
    explanation: str = Field(
        ...,
    )
    section: Optional[str] = Field(
        None,
    )
    page_hint: Optional[int] = Field(
        None,
        ge=1,
    )


class DocumentAnalysisMetrics(BaseModel):
    risk_score: int = Field(
        ...,
        ge=0,
        le=100,
    )
    risk_label: str = Field(
        ...,
    )
    clause_count: int = Field(default=0)
    obligation_count: int = Field(default=0)
    flagged_count: int = Field(
        default=0,
    )
    parties: List[str] = Field(
        default_factory=list,
    )
    key_dates: List[str] = Field(
        default_factory=list,
    )
    summary: str = Field(
        ...,
    )


class AnalyzeDocumentRequest(BaseModel):
    document_id: str = Field(...)
    filename: str = Field(...)
    text: str = Field(...)
    analysis_type: Literal["full", "risk", "clauses", "compare"] = Field(
        default="full",
    )

    compare_text: Optional[str] = Field(
        None,
    )
    compare_filename: Optional[str] = Field(
        None,
    )

    language: str = Field(
        default="uz",
    )

    @field_validator("text")
    @classmethod
    def text_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Document text cannot be empty")
        if len(v.strip()) < 50:
            raise ValueError("Document text too short to analyze (min 50 characters)")
        return v


class AnalyzeDocumentResponse(BaseModel):
    document_id: str
    analysis_type: str
    highlights: List[DocumentHighlight] = Field(
        default_factory=list,
    )
    metrics: DocumentAnalysisMetrics
    compare_highlights: Optional[List[DocumentHighlight]] = Field(
        None,
    )
    compare_summary: Optional[str] = Field(
        None,
    )
