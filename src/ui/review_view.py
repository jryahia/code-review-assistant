"""Review detail view — file tree + findings + code snippets."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

import flet as ft

from src.ui.components import (
    ACCENT,
    BG,
    BORDER,
    CARD,
    CRITICAL,
    SUGGESTION,
    SURFACE,
    TEXT,
    TEXT_DIM,
    WARNING,
    card,
    divider,
    empty_state,
    file_tree_item,
    finding_card,
    label_text,
    loading_spinner,
    primary_button,
    score_badge,
    score_gauge,
    secondary_button,
    section_header,
    severity_badge,
    show_snack,
    stat_card,
    status_chip,
)


class NewReviewView(ft.Column):
    """Form to start a new PR review."""

    def __init__(
        self,
        api_base: str,
        on_review_started: Optional[Callable] = None,
        page: Optional[ft.Page] = None,
    ) -> None:
        super().__init__(expand=True)
        self.api_base = api_base
        self.on_review_started = on_review_started
        self._page = page
        self._loading = False
        self._pr_url_field = ft.TextField(
            label="GitHub PR URL",
            hint_text="https://github.com/owner/repo/pull/123",
            bgcolor=SURFACE,
            border_color=BORDER,
            focused_border_color=ACCENT,
            label_style=ft.TextStyle(color=TEXT_DIM),
            text_style=ft.TextStyle(color=TEXT, size=13),
            hint_style=ft.TextStyle(color=TEXT_DIM + "80"),
            border_radius=8,
            expand=True,
        )
        self._token_field = ft.TextField(
            label="GitHub Token (optional — overrides setting)",
            hint_text="ghp_...",
            password=True,
            can_reveal_password=True,
            bgcolor=SURFACE,
            border_color=BORDER,
            focused_border_color=ACCENT,
            label_style=ft.TextStyle(color=TEXT_DIM),
            text_style=ft.TextStyle(color=TEXT, size=13),
            border_radius=8,
            expand=True,
        )
        self._ai_toggle = ft.Switch(
            label="AI Semantic Review",
            value=False,
            active_color=ACCENT,
            label_style=ft.TextStyle(color=TEXT_DIM, size=12),
        )
        self._category_checks = {
            cat: ft.Checkbox(
                label=cat.capitalize(),
                value=True,
                active_color=ACCENT,
                label_style=ft.TextStyle(color=TEXT, size=12),
            )
            for cat in ["bugs", "security", "style", "performance", "architecture"]
        }
        self._submit_btn = primary_button("Analyze PR", on_click=self._submit)
        self._build()

    def _build(self) -> None:
        self.controls = [
            ft.Container(
                content=ft.Column(
                    controls=[
                        section_header("New Review", "Paste a GitHub PR URL to start"),
                        ft.Container(height=24),
                        card(
                            ft.Column(
                                controls=[
                                    ft.Text("PR URL", size=12, color=TEXT_DIM, weight=ft.FontWeight.W_600),
                                    self._pr_url_field,
                                    ft.Container(height=8),
                                    ft.Text("Authentication", size=12, color=TEXT_DIM, weight=ft.FontWeight.W_600),
                                    self._token_field,
                                    ft.Container(height=8),
                                    ft.Text("Analysis Options", size=12, color=TEXT_DIM, weight=ft.FontWeight.W_600),
                                    ft.Row(
                                        controls=list(self._category_checks.values()),
                                        spacing=16,
                                        wrap=True,
                                    ),
                                    self._ai_toggle,
                                    ft.Container(height=8),
                                    ft.Row(
                                        controls=[self._submit_btn],
                                        alignment=ft.MainAxisAlignment.END,
                                    ),
                                ],
                                spacing=8,
                            ),
                            padding=24,
                        ),
                        ft.Container(height=20),
                        self._build_info_card(),
                    ],
                    scroll=ft.ScrollMode.AUTO,
                    expand=True,
                ),
                expand=True,
                bgcolor=BG,
                padding=ft.padding.all(24),
            )
        ]

    def _build_info_card(self) -> ft.Container:
        return card(
            ft.Column(
                controls=[
                    ft.Text("How it works", size=13, color=TEXT, weight=ft.FontWeight.W_600),
                    ft.Container(height=8),
                    *[
                        ft.Row(
                            controls=[
                                ft.Text(f"{i+1}.", size=12, color=ACCENT, weight=ft.FontWeight.W_600),
                                ft.Text(step, size=12, color=TEXT_DIM),
                            ],
                            spacing=8,
                        )
                        for i, step in enumerate([
                            "Fetch PR diff and changed files via GitHub API",
                            "Detect language for each file and run static analysis",
                            "Apply 5 analyzer categories: Bugs, Security, Style, Performance, Architecture",
                            "Calculate composite score (0-100) based on finding severity",
                            "Optionally run AI semantic review for deeper insights",
                        ])
                    ],
                ],
                spacing=6,
            ),
            bgcolor=SURFACE,
        )

    async def _submit(self, e: ft.ControlEvent) -> None:
        pr_url = self._pr_url_field.value or ""
        if not pr_url.strip():
            show_snack(self._page, "Please enter a GitHub PR URL", error=True)
            return

        if "github.com" not in pr_url or "/pull/" not in pr_url:
            show_snack(self._page, "Invalid GitHub PR URL format", error=True)
            return

        categories = [cat for cat, chk in self._category_checks.items() if chk.value]
        if not categories:
            show_snack(self._page, "Select at least one analysis category", error=True)
            return

        self._submit_btn.disabled = True
        self._submit_btn.text = "Analyzing..."
        if self._page:
            self._page.update()

        try:
            import httpx
            payload = {
                "pr_url": pr_url.strip(),
                "categories": categories,
                "ai_review": self._ai_toggle.value,
            }
            if self._token_field.value:
                payload["github_token"] = self._token_field.value

            async with httpx.AsyncClient(base_url=self.api_base, timeout=30) as client:
                resp = await client.post("/api/reviews", json=payload)

            if resp.status_code in (200, 201, 202):
                data = resp.json()
                show_snack(self._page, "Review started! Redirecting...")
                if self.on_review_started:
                    self.on_review_started(data["id"])
            else:
                detail = resp.json().get("detail", resp.text)
                show_snack(self._page, f"Error: {detail}", error=True)

        except Exception as ex:
            show_snack(self._page, f"Error: {ex}", error=True)
        finally:
            self._submit_btn.disabled = False
            self._submit_btn.text = "Analyze PR"
            if self._page:
                self._page.update()


class ReviewDetailView(ft.Column):
    """Full review detail with file tree + per-file findings + code snippets."""

    def __init__(
        self,
        review_id: str,
        api_base: str,
        on_back: Optional[Callable] = None,
        page: Optional[ft.Page] = None,
    ) -> None:
        super().__init__(expand=True, spacing=0)
        self.review_id = review_id
        self.api_base = api_base
        self.on_back = on_back
        self._page = page
        self._review: Optional[Dict] = None
        self._selected_file: Optional[str] = None
        self._loading = True
        self._polling = False
        self._build_loading()

    def _build_loading(self) -> None:
        self.controls = [
            ft.Container(
                content=loading_spinner("Loading review..."),
                expand=True,
                alignment=ft.alignment.center,
                bgcolor=BG,
            )
        ]

    async def load(self) -> None:
        """Load the review from the API (with polling for pending reviews)."""
        import asyncio
        import httpx

        for attempt in range(60):
            try:
                async with httpx.AsyncClient(base_url=self.api_base, timeout=15) as client:
                    resp = await client.get(f"/api/reviews/{self.review_id}")
                    if resp.status_code == 200:
                        self._review = resp.json()
                        status = self._review.get("status", "")
                        if status in ("completed", "failed"):
                            break
                        # Still running — update loading message
                        if self._page:
                            self.controls = [
                                ft.Container(
                                    content=loading_spinner(f"Analyzing... ({attempt + 1}s)"),
                                    expand=True,
                                    alignment=ft.alignment.center,
                                    bgcolor=BG,
                                )
                            ]
                            self._page.update()
                        await asyncio.sleep(2)
                    else:
                        break
            except Exception:
                await asyncio.sleep(2)

        self._loading = False
        self._build_review()
        if self._page:
            self._page.update()

    def _build_review(self) -> None:
        if not self._review:
            self.controls = [
                ft.Container(
                    content=empty_state("Review not found", icon="❌"),
                    expand=True,
                    bgcolor=BG,
                    alignment=ft.alignment.center,
                )
            ]
            return

        status = self._review.get("status", "")
        if status == "failed":
            self._build_failed()
            return

        self.controls = [
            ft.Container(
                content=ft.Column(
                    controls=[self._build_header(), self._build_body()],
                    spacing=0,
                    expand=True,
                ),
                expand=True,
                bgcolor=BG,
            )
        ]

    def _build_failed(self) -> None:
        error = self._review.get("error_message", "Unknown error") if self._review else "Unknown"
        self.controls = [
            ft.Container(
                content=ft.Column(
                    controls=[
                        ft.IconButton(
                            icon=ft.icons.ARROW_BACK,
                            icon_color=TEXT_DIM,
                            on_click=lambda _: self.on_back() if self.on_back else None,
                        ),
                        empty_state("Review Failed", error, icon="❌"),
                    ],
                    spacing=12,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                expand=True,
                bgcolor=BG,
                alignment=ft.alignment.center,
            )
        ]

    def _build_header(self) -> ft.Container:
        r = self._review or {}
        score = r.get("score") or 0
        pr_title = r.get("pr_title") or r.get("pr_url", "")[:60]
        pr_url = r.get("pr_url", "")
        repo = f"{r.get('repo_owner', '')}/{r.get('repo_name', '')}"
        branch = r.get("branch", "")

        export_dd = ft.PopupMenuButton(
            icon=ft.icons.DOWNLOAD,
            icon_color=TEXT_DIM,
            items=[
                ft.PopupMenuItem(text="Export Markdown", on_click=lambda _: self._export("markdown")),
                ft.PopupMenuItem(text="Export PDF", on_click=lambda _: self._export("pdf")),
                ft.PopupMenuItem(text="Post GitHub Comment", on_click=lambda _: self._export("github_comment")),
            ],
            tooltip="Export",
        )

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.IconButton(
                                icon=ft.icons.ARROW_BACK,
                                icon_color=TEXT_DIM,
                                on_click=lambda _: self.on_back() if self.on_back else None,
                                tooltip="Back",
                            ),
                            ft.Column(
                                controls=[
                                    ft.Text(
                                        pr_title[:80],
                                        size=16,
                                        color=TEXT,
                                        weight=ft.FontWeight.BOLD,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    ),
                                    ft.Row(
                                        controls=[
                                            ft.Text(repo, size=11, color=TEXT_DIM),
                                            ft.Text("•", size=11, color=TEXT_DIM),
                                            ft.Text(f"#{r.get('pr_number', '?')}", size=11, color=ACCENT),
                                            ft.Text("•", size=11, color=TEXT_DIM),
                                            ft.Text(branch, size=11, color=TEXT_DIM),
                                            status_chip(r.get("status", "pending")),
                                        ],
                                        spacing=6,
                                    ),
                                ],
                                spacing=3,
                                expand=True,
                            ),
                            export_dd,
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    ),
                    ft.Container(height=16),
                    ft.Row(
                        controls=[
                            score_gauge(score, size=100),
                            ft.Container(width=20),
                            ft.Column(
                                controls=[
                                    ft.Row(
                                        controls=[
                                            stat_card("Files", str(r.get("files_changed", 0)), width=100),
                                            stat_card("+Lines", str(r.get("lines_added", 0)), color="#22c55e", width=100),
                                            stat_card("-Lines", str(r.get("lines_removed", 0)), color=CRITICAL, width=100),
                                        ],
                                        spacing=8,
                                    ),
                                    ft.Row(
                                        controls=[
                                            stat_card("🔴 Critical", str(r.get("critical_count", 0)), color=CRITICAL, width=100),
                                            stat_card("🟡 Warning", str(r.get("warning_count", 0)), color=WARNING, width=100),
                                            stat_card("🔵 Suggest", str(r.get("suggestion_count", 0)), color=SUGGESTION, width=100),
                                        ],
                                        spacing=8,
                                    ),
                                ],
                                spacing=8,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(height=8),
                    # AI Summary
                    *([card(
                        ft.Column(
                            controls=[
                                ft.Text("🤖 AI Summary", size=12, color=TEXT_DIM, weight=ft.FontWeight.W_600),
                                ft.Text(r["ai_summary"], size=12, color=TEXT),
                            ],
                            spacing=4,
                        ),
                        bgcolor=SURFACE,
                    )] if r.get("ai_summary") else []),
                ],
                spacing=0,
            ),
            bgcolor=CARD,
            padding=ft.padding.all(20),
            border=ft.border.only(bottom=ft.BorderSide(1, BORDER)),
        )

    def _build_body(self) -> ft.Row:
        file_reviews = (self._review or {}).get("file_reviews", [])

        # File tree (left panel)
        file_tree_items: List[ft.Control] = []
        for fr in file_reviews:
            findings = fr.get("findings", [])
            crit = sum(1 for f in findings if f.get("severity") == "critical")
            warn = sum(1 for f in findings if f.get("severity") == "warning")
            filename = fr.get("filename", "")
            file_tree_items.append(
                file_tree_item(
                    filename=filename,
                    score=fr.get("score", 100) or 100,
                    findings_count=len(findings),
                    language=fr.get("language", ""),
                    on_click=lambda _, fn=filename: self._select_file(fn),
                    selected=filename == self._selected_file,
                )
            )

        file_tree = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text("Files Changed", size=12, color=TEXT_DIM, weight=ft.FontWeight.W_600),
                    ft.Container(height=8),
                    ft.Column(
                        controls=file_tree_items,
                        scroll=ft.ScrollMode.AUTO,
                        spacing=0,
                        expand=True,
                    ),
                ],
                expand=True,
            ),
            bgcolor=SURFACE,
            padding=ft.padding.all(12),
            width=250,
            border=ft.border.only(right=ft.BorderSide(1, BORDER)),
        )

        # Findings panel (right)
        findings_panel = self._build_findings_panel(file_reviews)

        return ft.Row(
            controls=[file_tree, findings_panel],
            spacing=0,
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

    def _build_findings_panel(self, file_reviews: List[Dict]) -> ft.Container:
        if not file_reviews:
            return ft.Container(
                content=empty_state("No files analyzed", icon="📂"),
                expand=True,
                alignment=ft.alignment.center,
            )

        # Show selected file or all findings
        if self._selected_file:
            selected_fr = next(
                (fr for fr in file_reviews if fr.get("filename") == self._selected_file), None
            )
            display_reviews = [selected_fr] if selected_fr else file_reviews
        else:
            display_reviews = file_reviews

        sections: List[ft.Control] = []
        for fr in display_reviews:
            filename = fr.get("filename", "")
            findings = fr.get("findings", [])
            lang = fr.get("language", "")
            fr_score = fr.get("score", 100) or 100

            file_header = ft.Row(
                controls=[
                    ft.Text(filename, size=13, color=TEXT, weight=ft.FontWeight.W_600, selectable=True),
                    ft.Text(lang.capitalize(), size=11, color=TEXT_DIM),
                    score_badge(fr_score),
                    ft.Text(f"{len(findings)} findings", size=11, color=TEXT_DIM),
                ],
                spacing=8,
                wrap=True,
            )

            if findings:
                # Sort: critical first
                sorted_findings = sorted(
                    findings,
                    key=lambda f: {"critical": 0, "warning": 1, "suggestion": 2}.get(f.get("severity", ""), 3),
                )
                finding_controls = [finding_card(f) for f in sorted_findings]
            else:
                finding_controls = [
                    ft.Container(
                        content=ft.Text("✅ No issues found in this file", size=12, color="#22c55e"),
                        padding=ft.padding.all(12),
                    )
                ]

            sections.append(
                ft.Column(
                    controls=[
                        file_header,
                        ft.Container(height=8),
                        *finding_controls,
                        ft.Container(height=16),
                    ],
                    spacing=0,
                )
            )

        return ft.Container(
            content=ft.Column(
                controls=sections,
                scroll=ft.ScrollMode.AUTO,
                spacing=0,
                expand=True,
            ),
            expand=True,
            padding=ft.padding.all(16),
        )

    def _select_file(self, filename: str) -> None:
        if self._selected_file == filename:
            self._selected_file = None
        else:
            self._selected_file = filename
        self._build_review()
        if self._page:
            self._page.update()

    async def _export(self, fmt: str) -> None:
        if not self._review:
            return
        try:
            import httpx
            async with httpx.AsyncClient(base_url=self.api_base, timeout=30) as client:
                resp = await client.post(
                    f"/api/reviews/{self.review_id}/export",
                    json={"format": fmt},
                )
            if resp.status_code == 200:
                if fmt == "github_comment":
                    data = resp.json()
                    show_snack(self._page, f"Comment posted: {data.get('url', '')}")
                else:
                    # Save to data dir
                    from src.config import settings
                    ext = "md" if fmt == "markdown" else "pdf"
                    out_path = settings.data_dir / "exports" / f"review_{self.review_id}.{ext}"
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_bytes(resp.content)
                    show_snack(self._page, f"Saved: {out_path}")
            else:
                show_snack(self._page, f"Export failed: {resp.text}", error=True)
        except Exception as ex:
            show_snack(self._page, f"Export error: {ex}", error=True)
