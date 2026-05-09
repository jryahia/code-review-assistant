"""Export functions — save to file, post to GitHub."""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import structlog

from src.config import settings
from src.github_client import GitHubClient, parse_pr_url
from src.report_generator import (
    generate_github_comment,
    generate_markdown_report,
    generate_pdf_report,
)

logger = structlog.get_logger(__name__)


async def export_markdown(review_data: Dict[str, Any], output_path: Optional[Path] = None) -> str:
    """Generate and optionally save a Markdown report."""
    content = generate_markdown_report(review_data)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
        logger.info("Markdown report saved", path=str(output_path))

    return content


async def export_pdf(review_data: Dict[str, Any], output_path: Optional[Path] = None) -> bytes:
    """Generate and optionally save a PDF report."""
    pdf_bytes = generate_pdf_report(review_data)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(pdf_bytes)
        logger.info("PDF report saved", path=str(output_path))

    return pdf_bytes


async def post_github_comment(
    review_data: Dict[str, Any],
    github_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Post review results as a GitHub PR comment."""
    pr_url = review_data.get("pr_url", "")
    if not pr_url:
        raise ValueError("review_data must contain 'pr_url'")

    token = github_token or settings.github_token
    if not token:
        raise ValueError("GitHub token is required to post comments")

    owner, repo, pr_number = parse_pr_url(pr_url)
    comment_body = generate_github_comment(review_data)

    async with GitHubClient(token=token) as client:
        result = await client.post_pr_comment(owner, repo, pr_number, comment_body)

    logger.info("GitHub comment posted", pr_url=pr_url, comment_id=result.get("id"))
    return result


def get_default_export_path(review_data: Dict[str, Any], fmt: str) -> Path:
    """Generate a sensible default file path for an export."""
    repo_owner = review_data.get("repo_owner", "unknown")
    repo_name = review_data.get("repo_name", "repo")
    pr_number = review_data.get("pr_number", 0)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    ext = "md" if fmt == "markdown" else fmt
    filename = f"review_{repo_owner}_{repo_name}_pr{pr_number}_{timestamp}.{ext}"
    return settings.data_dir / "exports" / filename
