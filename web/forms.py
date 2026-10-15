"""Pydantic request models for the JSON endpoints."""

from pydantic import BaseModel, Field, field_validator

SOURCE_TYPES = {"google_drive", "sharepoint"}


class SearchRequest(BaseModel):
    q: str = Field(min_length=1, max_length=1000)
    source_types: list[str] = Field(default_factory=list)
    limit: int = Field(default=10, ge=1, le=50)

    @field_validator("source_types")
    @classmethod
    def _known(cls, value):
        bad = set(value) - SOURCE_TYPES
        if bad:
            raise ValueError(f"unknown source types: {sorted(bad)}")
        return value


class AnswerRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    source_types: list[str] = Field(default_factory=list)
    k: int = Field(default=8, ge=1, le=20)

    @field_validator("source_types")
    @classmethod
    def _known(cls, value):
        bad = set(value) - SOURCE_TYPES
        if bad:
            raise ValueError(f"unknown source types: {sorted(bad)}")
        return value
