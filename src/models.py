"""
Data models for the summarization API.
"""
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class SummaryStyle(str, Enum):
    bullet = "bullet"
    paragraph = "paragraph"
    tldr = "tldr"


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class SummarizeRequest(BaseModel):
    text: str = Field(..., min_length=10, description="Text to summarize")
    max_length: int = Field(150, ge=20, le=1000, description="Maximum word count for the summary")
    style: SummaryStyle = Field(SummaryStyle.paragraph, description="Output style")

    @field_validator("text")
    @classmethod
    def text_not_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("text must not be blank")
        return stripped


class BatchSummarizeRequest(BaseModel):
    items: list[SummarizeRequest] = Field(
        ...,
        min_length=1,
        max_length=20,
        description="List of texts to summarize (1–20 items)",
    )


class URLSummarizeRequest(BaseModel):
    url: str = Field(..., description="Publicly accessible URL to fetch and summarize")
    max_length: int = Field(150, ge=20, le=1000, description="Maximum word count for the summary")
    style: SummaryStyle = Field(SummaryStyle.paragraph, description="Output style")

    @field_validator("url")
    @classmethod
    def url_must_be_http(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("url must start with http:// or https://")
        return v


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class SummaryResponse(BaseModel):
    summary: str
    word_count: int
    compression_ratio: float = Field(
        ..., description="Ratio of summary words to original words (lower = more compressed)"
    )


class BatchSummaryItem(BaseModel):
    index: int
    summary: str
    word_count: int
    compression_ratio: float


class BatchSummaryResponse(BaseModel):
    results: list[BatchSummaryItem]
    total_items: int


class ModelInfo(BaseModel):
    id: str
    name: str
    description: str
    max_input_tokens: int
    supported_styles: list[SummaryStyle]


class ModelsResponse(BaseModel):
    models: list[ModelInfo]
    default_model: str


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
