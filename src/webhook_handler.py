"""GitHub webhook handler for auto-review on PR events."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime
from typing import Any, Dict, Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models import Project, Webhook

logger = structlog.get_logger(__name__)

SUPPORTED_EVENTS = {"pull_request", "push"}


def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub webhook HMAC-SHA256 signature."""
    if not secret:
        return True
    if not signature:
        return False
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


class WebhookProcessor:
    """Processes incoming GitHub webhook events and triggers reviews."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def process_event(
        self,
        event_type: str,
        payload: Dict[str, Any],
        delivery_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Process a webhook event. Returns review_id if a review was triggered.
        """
        if event_type not in SUPPORTED_EVENTS:
            logger.debug("Skipping unsupported event", event_type=event_type)
            return None

        if event_type == "pull_request":
            return await self._handle_pull_request(payload, delivery_id)
        elif event_type == "push":
            return await self._handle_push(payload, delivery_id)
        return None

    async def _handle_pull_request(
        self,
        payload: Dict[str, Any],
        delivery_id: Optional[str],
    ) -> Optional[str]:
        action = payload.get("action", "")
        if action not in ("opened", "synchronize", "reopened"):
            logger.debug("Ignoring PR action", action=action)
            return None

        pr = payload.get("pull_request", {})
        repo = payload.get("repository", {})
        repo_full_name = repo.get("full_name", "")
        pr_url = pr.get("html_url", "")
        pr_number = pr.get("number")

        if not pr_url or not pr_number:
            return None

        # Find monitored project for this repo
        project = await self._find_project(repo_full_name)
        if not project:
            logger.debug("No monitored project for repo", repo=repo_full_name)
            return None

        if not project.auto_watch:
            logger.debug("Auto-watch disabled for project", project_id=project.id)
            return None

        # Record the webhook event
        webhook_record = Webhook(
            project_id=project.id,
            event_type="pull_request",
            payload=json.dumps(payload)[:65535],
            delivery_id=delivery_id,
        )
        self.db.add(webhook_record)
        await self.db.flush()

        # Trigger review
        try:
            review_id = await self._trigger_review(project, pr_url, pr_number)
            webhook_record.processed = True
            webhook_record.review_id = review_id
            webhook_record.processed_at = datetime.utcnow()
            return review_id
        except Exception as e:
            logger.error("Failed to trigger auto-review", pr_url=pr_url, error=str(e))
            webhook_record.processed = False
            return None

    async def _handle_push(
        self,
        payload: Dict[str, Any],
        delivery_id: Optional[str],
    ) -> Optional[str]:
        repo = payload.get("repository", {})
        repo_full_name = repo.get("full_name", "")
        ref = payload.get("ref", "")
        branch = ref.replace("refs/heads/", "") if ref.startswith("refs/heads/") else ref

        project = await self._find_project(repo_full_name)
        if not project:
            return None

        # Record push event
        webhook_record = Webhook(
            project_id=project.id,
            event_type="push",
            payload=json.dumps({"ref": ref, "repo": repo_full_name, "delivery_id": delivery_id})[:65535],
            delivery_id=delivery_id,
            processed=True,
            processed_at=datetime.utcnow(),
        )
        self.db.add(webhook_record)
        logger.info("Push event recorded", repo=repo_full_name, branch=branch)
        return None

    async def _find_project(self, repo_full_name: str) -> Optional[Project]:
        from sqlalchemy import select
        stmt = select(Project).where(
            Project.repo.ilike(repo_full_name.split("/")[-1])
        )
        result = await self.db.execute(stmt)
        projects = result.scalars().all()
        for p in projects:
            if f"{p.owner}/{p.repo}".lower() == repo_full_name.lower():
                return p
        return None

    async def _trigger_review(
        self, project: Project, pr_url: str, pr_number: int
    ) -> str:
        """Trigger an automated review for a PR."""
        from src.models import Review
        from src.config import settings

        github_token = ""
        if project.github_token_enc:
            github_token = settings.decrypt(project.github_token_enc)

        review = Review(
            project_id=project.id,
            pr_url=pr_url,
            pr_number=pr_number,
            status="pending",
        )
        self.db.add(review)
        await self.db.flush()
        review_id = review.id

        # Background task will pick this up
        logger.info("Auto-review queued", review_id=review_id, pr_url=pr_url)
        return review_id
