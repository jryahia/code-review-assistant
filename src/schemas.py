"""Pydantic v2 request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class FindingSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    category: str
    severity: str
    line_number: Optional[int] = None
    end_line: Optional[int] = None
    message: str
    code_snippet: Optional[str] = None
    suggestion: Optional[str] = None
    rule_id: Optional[str] = None


class FileReviewSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    language: str
    score: float
    lines_added: int
    lines_removed: int
    findings_count: int
    findings: List[FindingSchema] = []


class ReviewSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: Optional[str] = None
    pr_url: str
    pr_number: Optional[int] = None
    pr_title: Optional[str] = None
    branch: Optional[str] = None
    base_branch: Optional[str] = None
    commit_sha: Optional[str] = None
    repo_owner: Optional[str] = None
    repo_name: Optional[str] = None
    score: Optional[float] = None
    status: str
    files_changed: int
    lines_added: int
    lines_removed: int
    total_findings: int
    critical_count: int
    warning_count: int
    suggestion_count: int
    ai_summary: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    file_reviews: List[FileReviewSchema] = []


class ReviewListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    pr_url: str
    pr_number: Optional[int] = None
    pr_title: Optional[str] = None
    repo_owner: Optional[str] = None
    repo_name: Optional[str] = None
    score: Optional[float] = None
    status: str
    files_changed: int
    total_findings: int
    critical_count: int
    warning_count: int
    created_at: datetime


class CreateReviewRequest(BaseModel):
    pr_url: str = Field(..., description="GitHub PR URL")
    project_id: Optional[str] = None
    github_token: Optional[str] = None
    categories: Optional[List[str]] = None
    ai_review: bool = False

    @field_validator("pr_url")
    @classmethod
    def validate_pr_url(cls, v: str) -> str:
        if "github.com" not in v or "/pull/" not in v:
            raise ValueError("Must be a valid GitHub PR URL")
        return v.strip()


class ProjectSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    repo_url: str
    owner: str
    repo: str
    description: Optional[str] = None
    auto_watch: bool
    poll_interval: int
    default_branch: str
    enabled_categories: str
    created_at: datetime
    updated_at: datetime


class CreateProjectRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    repo_url: str = Field(..., description="GitHub repository URL")
    description: Optional[str] = None
    github_token: Optional[str] = None
    auto_watch: bool = False
    poll_interval: int = Field(300, ge=60, le=86400)
    default_branch: str = "main"
    enabled_categories: str = "bugs,security,style,performance,architecture"

    @field_validator("repo_url")
    @classmethod
    def validate_repo_url(cls, v: str) -> str:
        if "github.com" not in v:
            raise ValueError("Must be a valid GitHub repository URL")
        return v.strip().rstrip("/")


class UpdateProjectRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    github_token: Optional[str] = None
    auto_watch: Optional[bool] = None
    poll_interval: Optional[int] = Field(None, ge=60, le=86400)
    default_branch: Optional[str] = None
    enabled_categories: Optional[str] = None


class IgnorePatternSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    pattern: str
    description: Optional[str] = None
    is_regex: bool
    created_at: datetime


class CreateIgnorePatternRequest(BaseModel):
    pattern: str = Field(..., min_length=1)
    description: Optional[str] = None
    is_regex: bool = True


class AppSettingsSchema(BaseModel):
    github_token: str = ""
    github_webhook_secret: str = ""
    ai_provider: str = "off"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    claude_api_key: str = ""
    claude_model: str = "claude-3-5-sonnet-20241022"
    default_categories: str = "bugs,security,style,performance,architecture"
    max_file_size_kb: int = 500
    poll_interval_seconds: int = 300
    log_level: str = "INFO"
    api_port: int = 8765


class UpdateSettingsRequest(BaseModel):
    github_token: Optional[str] = None
    github_webhook_secret: Optional[str] = None
    ai_provider: Optional[str] = None
    openai_api_key: Optional[str] = None
    openai_model: Optional[str] = None
    claude_api_key: Optional[str] = None
    claude_model: Optional[str] = None
    default_categories: Optional[str] = None
    max_file_size_kb: Optional[int] = None
    poll_interval_seconds: Optional[int] = None
    log_level: Optional[str] = None
    api_port: Optional[int] = None


class ExportRequest(BaseModel):
    format: str = Field(..., description="markdown | pdf | github_comment")
    github_token: Optional[str] = None


class WebhookEventSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    event_type: str
    delivery_id: Optional[str] = None
    processed: bool
    review_id: Optional[str] = None
    received_at: datetime
    processed_at: Optional[datetime] = None


class AnalysisStats(BaseModel):
    total_reviews: int
    avg_score: float
    total_findings: int
    critical_total: int
    warning_total: int
    suggestion_total: int
    reviews_by_status: Dict[str, int]
    top_languages: List[Dict[str, Any]]
    score_trend: List[Dict[str, Any]]


class PaginatedReviews(BaseModel):
    items: List[ReviewListItem]
    total: int
    page: int
    page_size: int
    pages: int


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str
    ai_provider: str
