"""FastAPI application with all routes."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src import __version__
from src.ai_reviewer import AIReviewer
from src.analyzer.engine import AnalysisEngine
from src.config import settings
from src.database import get_db, init_db
from src.export import export_markdown, export_pdf, get_default_export_path, post_github_comment
from src.github_client import (
    GitHubAuthError,
    GitHubClient,
    GitHubNotFoundError,
    GitHubRateLimitError,
    parse_pr_url,
    parse_repo_url,
)
from src.models import (
    AppSettings,
    FileReview,
    Finding,
    IgnorePattern,
    Project,
    Review,
    Webhook,
)
from src.report_generator import generate_github_comment
from src.schemas import (
    AnalysisStats,
    AppSettingsSchema,
    CreateIgnorePatternRequest,
    CreateProjectRequest,
    CreateReviewRequest,
    ExportRequest,
    HealthResponse,
    IgnorePatternSchema,
    PaginatedReviews,
    ProjectSchema,
    ReviewListItem,
    ReviewSchema,
    UpdateProjectRequest,
    UpdateSettingsRequest,
)
from src.scoring import calculate_aggregate_score, calculate_score
from src.webhook_handler import WebhookProcessor, verify_signature

logger = structlog.get_logger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Code Review Assistant API",
        version=__version__,
        description="Production-quality automated code review",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def startup() -> None:
        await init_db()
        logger.info("Database initialized")

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            version=__version__,
            database="connected",
            ai_provider=settings.ai_provider,
        )

    # ── Reviews ──────────────────────────────────────────────────────────────

    @app.post("/api/reviews", response_model=ReviewSchema, status_code=202)
    async def create_review(
        req: CreateReviewRequest,
        background_tasks: BackgroundTasks,
        db: AsyncSession = Depends(get_db),
    ) -> Review:
        try:
            owner, repo, pr_number = parse_pr_url(req.pr_url)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        review = Review(
            project_id=req.project_id,
            pr_url=req.pr_url,
            pr_number=pr_number,
            repo_owner=owner,
            repo_name=repo,
            status="pending",
        )
        db.add(review)
        await db.flush()
        review_id = review.id

        token = req.github_token or settings.github_token
        categories = req.categories or settings.default_categories_list

        background_tasks.add_task(
            run_review,
            review_id=review_id,
            pr_url=req.pr_url,
            github_token=token,
            categories=categories,
            ai_review=req.ai_review,
        )

        result = await db.get(Review, review_id)
        return result

    @app.get("/api/reviews", response_model=PaginatedReviews)
    async def list_reviews(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        status_filter: Optional[str] = Query(None, alias="status"),
        repo: Optional[str] = Query(None),
        min_score: Optional[float] = Query(None, ge=0, le=100),
        max_score: Optional[float] = Query(None, ge=0, le=100),
        db: AsyncSession = Depends(get_db),
    ) -> PaginatedReviews:
        stmt = select(Review).order_by(desc(Review.created_at))
        if status_filter:
            stmt = stmt.where(Review.status == status_filter)
        if repo:
            stmt = stmt.where(Review.repo_name.ilike(f"%{repo}%"))
        if min_score is not None:
            stmt = stmt.where(Review.score >= min_score)
        if max_score is not None:
            stmt = stmt.where(Review.score <= max_score)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await db.execute(count_stmt)).scalar() or 0

        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        rows = (await db.execute(stmt)).scalars().all()

        return PaginatedReviews(
            items=[ReviewListItem.model_validate(r) for r in rows],
            total=total,
            page=page,
            page_size=page_size,
            pages=max(1, (total + page_size - 1) // page_size),
        )

    @app.get("/api/reviews/{review_id}", response_model=ReviewSchema)
    async def get_review(
        review_id: str, db: AsyncSession = Depends(get_db)
    ) -> Review:
        stmt = (
            select(Review)
            .where(Review.id == review_id)
            .options(
                selectinload(Review.file_reviews).selectinload(FileReview.findings)
            )
        )
        result = await db.execute(stmt)
        review = result.scalar_one_or_none()
        if not review:
            raise HTTPException(status_code=404, detail="Review not found")
        return review

    @app.delete("/api/reviews/{review_id}", status_code=204)
    async def delete_review(
        review_id: str, db: AsyncSession = Depends(get_db)
    ) -> None:
        review = await db.get(Review, review_id)
        if not review:
            raise HTTPException(status_code=404, detail="Review not found")
        await db.delete(review)

    @app.post("/api/reviews/{review_id}/rerun", response_model=ReviewSchema, status_code=202)
    async def rerun_review(
        review_id: str,
        background_tasks: BackgroundTasks,
        db: AsyncSession = Depends(get_db),
    ) -> Review:
        review = await db.get(Review, review_id)
        if not review:
            raise HTTPException(status_code=404, detail="Review not found")

        review.status = "pending"
        review.score = None
        review.error_message = None
        review.completed_at = None
        await db.flush()

        background_tasks.add_task(
            run_review,
            review_id=review_id,
            pr_url=review.pr_url,
            github_token=settings.github_token,
            categories=settings.default_categories_list,
            ai_review=False,
        )
        return review

    # ── Projects ──────────────────────────────────────────────────────────────

    @app.post("/api/projects", response_model=ProjectSchema, status_code=201)
    async def create_project(
        req: CreateProjectRequest, db: AsyncSession = Depends(get_db)
    ) -> Project:
        try:
            owner, repo = parse_repo_url(req.repo_url)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        existing = await db.execute(select(Project).where(Project.repo_url == req.repo_url))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Project with this repo URL already exists")

        token_enc = ""
        if req.github_token:
            token_enc = settings.encrypt(req.github_token)

        project = Project(
            name=req.name,
            repo_url=req.repo_url,
            owner=owner,
            repo=repo,
            description=req.description,
            github_token_enc=token_enc or None,
            auto_watch=req.auto_watch,
            poll_interval=req.poll_interval,
            default_branch=req.default_branch,
            enabled_categories=req.enabled_categories,
        )
        db.add(project)
        await db.flush()
        return project

    @app.get("/api/projects", response_model=List[ProjectSchema])
    async def list_projects(db: AsyncSession = Depends(get_db)) -> List[Project]:
        result = await db.execute(select(Project).order_by(Project.created_at.desc()))
        return list(result.scalars().all())

    @app.get("/api/projects/{project_id}", response_model=ProjectSchema)
    async def get_project(
        project_id: str, db: AsyncSession = Depends(get_db)
    ) -> Project:
        project = await db.get(Project, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        return project

    @app.patch("/api/projects/{project_id}", response_model=ProjectSchema)
    async def update_project(
        project_id: str,
        req: UpdateProjectRequest,
        db: AsyncSession = Depends(get_db),
    ) -> Project:
        project = await db.get(Project, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        if req.name is not None:
            project.name = req.name
        if req.description is not None:
            project.description = req.description
        if req.github_token is not None:
            project.github_token_enc = settings.encrypt(req.github_token) if req.github_token else None
        if req.auto_watch is not None:
            project.auto_watch = req.auto_watch
        if req.poll_interval is not None:
            project.poll_interval = req.poll_interval
        if req.default_branch is not None:
            project.default_branch = req.default_branch
        if req.enabled_categories is not None:
            project.enabled_categories = req.enabled_categories

        await db.flush()
        return project

    @app.delete("/api/projects/{project_id}", status_code=204)
    async def delete_project(
        project_id: str, db: AsyncSession = Depends(get_db)
    ) -> None:
        project = await db.get(Project, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        await db.delete(project)

    @app.get("/api/projects/{project_id}/reviews", response_model=List[ReviewListItem])
    async def get_project_reviews(
        project_id: str,
        limit: int = Query(20, ge=1, le=100),
        db: AsyncSession = Depends(get_db),
    ) -> List[Review]:
        result = await db.execute(
            select(Review)
            .where(Review.project_id == project_id)
            .order_by(desc(Review.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    # ── Ignore Patterns ───────────────────────────────────────────────────────

    @app.post(
        "/api/projects/{project_id}/ignore-patterns",
        response_model=IgnorePatternSchema,
        status_code=201,
    )
    async def add_ignore_pattern(
        project_id: str,
        req: CreateIgnorePatternRequest,
        db: AsyncSession = Depends(get_db),
    ) -> IgnorePattern:
        project = await db.get(Project, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        import re
        if req.is_regex:
            try:
                re.compile(req.pattern)
            except re.error as e:
                raise HTTPException(status_code=400, detail=f"Invalid regex: {e}")

        pattern = IgnorePattern(
            project_id=project_id,
            pattern=req.pattern,
            description=req.description,
            is_regex=req.is_regex,
        )
        db.add(pattern)
        await db.flush()
        return pattern

    @app.get(
        "/api/projects/{project_id}/ignore-patterns",
        response_model=List[IgnorePatternSchema],
    )
    async def list_ignore_patterns(
        project_id: str, db: AsyncSession = Depends(get_db)
    ) -> List[IgnorePattern]:
        result = await db.execute(
            select(IgnorePattern).where(IgnorePattern.project_id == project_id)
        )
        return list(result.scalars().all())

    @app.delete("/api/projects/{project_id}/ignore-patterns/{pattern_id}", status_code=204)
    async def delete_ignore_pattern(
        project_id: str,
        pattern_id: str,
        db: AsyncSession = Depends(get_db),
    ) -> None:
        pattern = await db.get(IgnorePattern, pattern_id)
        if not pattern or pattern.project_id != project_id:
            raise HTTPException(status_code=404, detail="Pattern not found")
        await db.delete(pattern)

    # ── Export ────────────────────────────────────────────────────────────────

    @app.post("/api/reviews/{review_id}/export")
    async def export_review(
        review_id: str,
        req: ExportRequest,
        db: AsyncSession = Depends(get_db),
    ) -> Response:
        stmt = (
            select(Review)
            .where(Review.id == review_id)
            .options(
                selectinload(Review.file_reviews).selectinload(FileReview.findings)
            )
        )
        result = await db.execute(stmt)
        review = result.scalar_one_or_none()
        if not review:
            raise HTTPException(status_code=404, detail="Review not found")

        review_data = _review_to_dict(review)

        if req.format == "markdown":
            content = await export_markdown(review_data)
            return Response(
                content=content.encode("utf-8"),
                media_type="text/markdown",
                headers={"Content-Disposition": f'attachment; filename="review_{review_id}.md"'},
            )
        elif req.format == "pdf":
            pdf_bytes = await export_pdf(review_data)
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="review_{review_id}.pdf"'},
            )
        elif req.format == "github_comment":
            token = req.github_token or settings.github_token
            if not token:
                raise HTTPException(status_code=400, detail="GitHub token required for posting comments")
            try:
                result_data = await post_github_comment(review_data, github_token=token)
                return JSONResponse({"status": "posted", "comment_id": result_data.get("id"), "url": result_data.get("html_url")})
            except Exception as e:
                raise HTTPException(status_code=502, detail=str(e))
        else:
            raise HTTPException(status_code=400, detail=f"Unknown format: {req.format}")

    # ── Settings ──────────────────────────────────────────────────────────────

    @app.get("/api/settings", response_model=AppSettingsSchema)
    async def get_settings(db: AsyncSession = Depends(get_db)) -> AppSettingsSchema:
        rows = (await db.execute(select(AppSettings))).scalars().all()
        stored: Dict[str, str] = {r.key: r.value or "" for r in rows}

        def _get(key: str, default: str = "") -> str:
            return stored.get(key, getattr(settings, key, default) or default)

        return AppSettingsSchema(
            github_token="***" if _get("github_token") else "",
            github_webhook_secret="***" if _get("github_webhook_secret") else "",
            ai_provider=_get("ai_provider", settings.ai_provider),
            openai_api_key="***" if _get("openai_api_key") else "",
            openai_model=_get("openai_model", settings.openai_model),
            claude_api_key="***" if _get("claude_api_key") else "",
            claude_model=_get("claude_model", settings.claude_model),
            default_categories=_get("default_categories", settings.default_categories),
            max_file_size_kb=int(_get("max_file_size_kb", str(settings.max_file_size_kb))),
            poll_interval_seconds=int(_get("poll_interval_seconds", str(settings.poll_interval_seconds))),
            log_level=_get("log_level", settings.log_level),
            api_port=int(_get("api_port", str(settings.api_port))),
        )

    @app.put("/api/settings", response_model=AppSettingsSchema)
    async def update_settings(
        req: UpdateSettingsRequest, db: AsyncSession = Depends(get_db)
    ) -> AppSettingsSchema:
        updates: Dict[str, Any] = req.model_dump(exclude_none=True)
        sensitive = {"github_token", "github_webhook_secret", "openai_api_key", "claude_api_key"}

        for key, value in updates.items():
            stored_value = settings.encrypt(str(value)) if key in sensitive else str(value)
            existing = await db.get(AppSettings, key)
            if existing:
                existing.value = stored_value
            else:
                db.add(AppSettings(key=key, value=stored_value))

        await db.flush()
        return await get_settings(db)

    # ── Webhooks ──────────────────────────────────────────────────────────────

    @app.post("/api/webhooks/github", status_code=200)
    async def github_webhook(
        request: Request,
        background_tasks: BackgroundTasks,
        db: AsyncSession = Depends(get_db),
    ) -> JSONResponse:
        body = await request.body()
        signature = request.headers.get("X-Hub-Signature-256", "")
        event_type = request.headers.get("X-GitHub-Event", "")
        delivery_id = request.headers.get("X-GitHub-Delivery")

        webhook_secret = settings.github_webhook_secret
        if webhook_secret and not verify_signature(body, signature, webhook_secret):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON payload")

        processor = WebhookProcessor(db)
        review_id = await processor.process_event(event_type, payload, delivery_id)

        return JSONResponse(
            {"status": "accepted", "event": event_type, "review_id": review_id}
        )

    # ── Stats ─────────────────────────────────────────────────────────────────

    @app.get("/api/stats", response_model=AnalysisStats)
    async def get_stats(db: AsyncSession = Depends(get_db)) -> AnalysisStats:
        total_reviews = (await db.execute(select(func.count(Review.id)))).scalar() or 0
        avg_score_row = (await db.execute(select(func.avg(Review.score)))).scalar()
        avg_score = float(avg_score_row or 0.0)

        total_findings = (await db.execute(select(func.sum(Review.total_findings)))).scalar() or 0
        critical_total = (await db.execute(select(func.sum(Review.critical_count)))).scalar() or 0
        warning_total = (await db.execute(select(func.sum(Review.warning_count)))).scalar() or 0
        suggestion_total = (await db.execute(select(func.sum(Review.suggestion_count)))).scalar() or 0

        # Status breakdown
        status_rows = await db.execute(
            select(Review.status, func.count(Review.id)).group_by(Review.status)
        )
        reviews_by_status = {row[0]: row[1] for row in status_rows}

        # Top languages
        lang_rows = await db.execute(
            select(FileReview.language, func.count(FileReview.id))
            .group_by(FileReview.language)
            .order_by(desc(func.count(FileReview.id)))
            .limit(5)
        )
        top_languages = [{"language": row[0], "count": row[1]} for row in lang_rows]

        # Score trend (last 10 reviews)
        trend_rows = await db.execute(
            select(Review.created_at, Review.score)
            .where(Review.score.isnot(None))
            .order_by(desc(Review.created_at))
            .limit(10)
        )
        score_trend = [
            {"date": row[0].isoformat() if row[0] else "", "score": row[1] or 0}
            for row in reversed(trend_rows.all())
        ]

        return AnalysisStats(
            total_reviews=total_reviews,
            avg_score=round(avg_score, 1),
            total_findings=int(total_findings),
            critical_total=int(critical_total),
            warning_total=int(warning_total),
            suggestion_total=int(suggestion_total),
            reviews_by_status=reviews_by_status,
            top_languages=top_languages,
            score_trend=score_trend,
        )

    return app


async def run_review(
    review_id: str,
    pr_url: str,
    github_token: str,
    categories: List[str],
    ai_review: bool = False,
) -> None:
    """Background task: run full PR analysis and save results."""
    from src.database import get_session

    async with get_session() as db:
        review = await db.get(Review, review_id)
        if not review:
            logger.error("Review not found for background task", review_id=review_id)
            return

        try:
            review.status = "running"
            await db.flush()

            owner, repo, pr_number = parse_pr_url(pr_url)

            async with GitHubClient(token=github_token) as client:
                pr_info = await client.get_pr(owner, repo, pr_number)

            review.pr_title = pr_info.title
            review.branch = pr_info.head_ref
            review.base_branch = pr_info.base_ref
            review.commit_sha = pr_info.head_sha
            review.files_changed = pr_info.changed_files
            review.lines_added = pr_info.additions
            review.lines_removed = pr_info.deletions

            # Build file dicts for engine
            file_dicts = [
                {
                    "filename": f.filename,
                    "status": f.status,
                    "additions": f.additions,
                    "deletions": f.deletions,
                    "patch": f.patch,
                }
                for f in pr_info.files
            ]

            engine = AnalysisEngine(enabled_categories=categories)
            analysis = await engine.analyze_files(file_dicts)

            ai_reviewer = AIReviewer() if ai_review else None
            all_file_summaries: List[Dict] = []

            for file_result in analysis.files:
                file_review = FileReview(
                    review_id=review_id,
                    filename=file_result.filename,
                    language=file_result.language,
                    score=file_result.score,
                    lines_added=file_result.lines_added,
                    lines_removed=file_result.lines_removed,
                    findings_count=len(file_result.findings),
                )
                db.add(file_review)
                await db.flush()

                # Save findings
                for finding in file_result.findings:
                    db.add(
                        Finding(
                            file_review_id=file_review.id,
                            category=finding.category,
                            severity=finding.severity,
                            line_number=finding.line_number,
                            end_line=finding.end_line,
                            message=finding.message,
                            code_snippet=finding.code_snippet,
                            suggestion=finding.suggestion,
                            rule_id=finding.rule_id,
                        )
                    )

                # AI review for this file
                if ai_reviewer:
                    pr_file = next(
                        (f for f in pr_info.files if f.filename == file_result.filename), None
                    )
                    if pr_file and pr_file.patch:
                        findings_dicts = [
                            {"severity": f.severity, "line_number": f.line_number, "message": f.message}
                            for f in file_result.findings
                        ]
                        await ai_reviewer.review(
                            filename=file_result.filename,
                            language=file_result.language,
                            patch=pr_file.patch or "",
                            existing_findings=findings_dicts,
                        )

                all_file_summaries.append({
                    "filename": file_result.filename,
                    "score": file_result.score,
                    "critical": sum(1 for f in file_result.findings if f.severity == "critical"),
                    "warning": sum(1 for f in file_result.findings if f.severity == "warning"),
                })

            # AI summary for whole PR
            ai_summary = ""
            if ai_reviewer and ai_review:
                ai_summary = await ai_reviewer.summarize_review(
                    pr_title=pr_info.title,
                    files_summary=all_file_summaries,
                    total_score=analysis.total_score,
                )

            review.score = analysis.total_score
            review.total_findings = analysis.total_findings
            review.critical_count = analysis.critical_count
            review.warning_count = analysis.warning_count
            review.suggestion_count = analysis.suggestion_count
            review.ai_summary = ai_summary
            review.status = "completed"
            review.completed_at = datetime.utcnow()

            await db.flush()
            logger.info(
                "Review completed",
                review_id=review_id,
                score=analysis.total_score,
                findings=analysis.total_findings,
            )

        except GitHubAuthError as e:
            review.status = "failed"
            review.error_message = f"GitHub auth error: {e}"
            logger.error("Review failed: auth", review_id=review_id, error=str(e))
        except GitHubNotFoundError as e:
            review.status = "failed"
            review.error_message = f"PR not found: {e}"
            logger.error("Review failed: not found", review_id=review_id, error=str(e))
        except GitHubRateLimitError as e:
            review.status = "failed"
            review.error_message = f"Rate limited: {e}"
            logger.error("Review failed: rate limited", review_id=review_id, error=str(e))
        except Exception as e:
            review.status = "failed"
            review.error_message = str(e)
            logger.error("Review failed", review_id=review_id, error=str(e), exc_info=True)


def _review_to_dict(review: Review) -> Dict[str, Any]:
    """Convert a Review ORM object to a dict for report generation."""
    return {
        "id": review.id,
        "pr_url": review.pr_url,
        "pr_number": review.pr_number,
        "pr_title": review.pr_title,
        "branch": review.branch,
        "repo_owner": review.repo_owner,
        "repo_name": review.repo_name,
        "score": review.score,
        "status": review.status,
        "files_changed": review.files_changed,
        "lines_added": review.lines_added,
        "lines_removed": review.lines_removed,
        "total_findings": review.total_findings,
        "critical_count": review.critical_count,
        "warning_count": review.warning_count,
        "suggestion_count": review.suggestion_count,
        "ai_summary": review.ai_summary,
        "created_at": review.created_at,
        "file_reviews": [
            {
                "filename": fr.filename,
                "language": fr.language,
                "score": fr.score,
                "lines_added": fr.lines_added,
                "lines_removed": fr.lines_removed,
                "findings_count": fr.findings_count,
                "findings": [
                    {
                        "category": f.category,
                        "severity": f.severity,
                        "line_number": f.line_number,
                        "message": f.message,
                        "code_snippet": f.code_snippet,
                        "suggestion": f.suggestion,
                        "rule_id": f.rule_id,
                    }
                    for f in fr.findings
                ],
            }
            for fr in review.file_reviews
        ],
    }


app = create_app()
