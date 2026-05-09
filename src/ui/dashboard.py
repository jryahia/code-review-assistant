"""Dashboard view — recent reviews summary and score trend."""

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
    SUCCESS,
    SURFACE,
    TEXT,
    TEXT_DIM,
    WARNING,
    card,
    empty_state,
    loading_spinner,
    primary_button,
    score_badge,
    score_gauge,
    section_header,
    severity_badge,
    show_snack,
    stat_card,
    status_chip,
)


class DashboardView(ft.Column):
    """Main dashboard showing stats, recent reviews, and score trend."""

    def __init__(
        self,
        api_base: str,
        on_new_review: Optional[Callable] = None,
        on_open_review: Optional[Callable] = None,
        page: Optional[ft.Page] = None,
    ) -> None:
        super().__init__(expand=True, spacing=0)
        self.api_base = api_base
        self.on_new_review = on_new_review
        self.on_open_review = on_open_review
        self._page = page
        self._stats: Optional[Dict] = None
        self._reviews: List[Dict] = []
        self._loading = True

        self._build()

    def _build(self) -> None:
        self.controls = [
            ft.Container(
                content=ft.Column(
                    controls=[self._build_loading()],
                    expand=True,
                    scroll=ft.ScrollMode.AUTO,
                ),
                expand=True,
                bgcolor=BG,
                padding=ft.padding.all(24),
            )
        ]

    def _build_loading(self) -> ft.Control:
        return ft.Container(
            content=loading_spinner("Loading dashboard..."),
            expand=True,
            alignment=ft.alignment.center,
        )

    def _build_content(self) -> ft.Column:
        controls: List[ft.Control] = [
            section_header(
                "Dashboard",
                "Code review analytics and recent activity",
                actions=[
                    primary_button(
                        "New Review",
                        on_click=lambda _: self.on_new_review() if self.on_new_review else None,
                        icon=ft.icons.ADD,
                    )
                ],
            ),
            ft.Container(height=20),
        ]

        # Stats row
        if self._stats:
            controls.append(self._build_stats_row())
            controls.append(ft.Container(height=20))

        # Score trend + recent reviews
        controls.append(
            ft.Row(
                controls=[
                    ft.Container(
                        content=ft.Column(
                            controls=[self._build_recent_reviews()],
                            expand=True,
                        ),
                        expand=2,
                    ),
                    ft.Container(
                        content=ft.Column(
                            controls=[self._build_score_trend()],
                        ),
                        expand=1,
                    ),
                ],
                spacing=20,
                expand=True,
                vertical_alignment=ft.CrossAxisAlignment.START,
            )
        )

        return ft.Column(controls=controls, spacing=0, expand=True)

    def _build_stats_row(self) -> ft.Row:
        s = self._stats or {}
        return ft.Row(
            controls=[
                stat_card(
                    "Total Reviews",
                    str(s.get("total_reviews", 0)),
                    color=ACCENT,
                    icon="📋",
                ),
                stat_card(
                    "Avg Score",
                    f"{s.get('avg_score', 0):.1f}",
                    color=SUCCESS,
                    icon="📊",
                ),
                stat_card(
                    "Critical Issues",
                    str(s.get("critical_total", 0)),
                    color=CRITICAL,
                    icon="🔴",
                ),
                stat_card(
                    "Warnings",
                    str(s.get("warning_total", 0)),
                    color=WARNING,
                    icon="🟡",
                ),
                stat_card(
                    "Suggestions",
                    str(s.get("suggestion_total", 0)),
                    color=SUGGESTION,
                    icon="🔵",
                ),
            ],
            spacing=12,
            wrap=True,
        )

    def _build_recent_reviews(self) -> ft.Container:
        header = section_header("Recent Reviews", f"{len(self._reviews)} reviews")

        if not self._reviews:
            content: ft.Control = ft.Container(
                content=empty_state(
                    "No reviews yet",
                    "Start by pasting a GitHub PR URL",
                    icon="🔍",
                    action_label="New Review",
                    on_action=lambda _: self.on_new_review() if self.on_new_review else None,
                ),
                height=200,
                alignment=ft.alignment.center,
            )
        else:
            rows: List[ft.Control] = []
            for review in self._reviews[:10]:
                rows.append(self._review_row(review))
            content = ft.Column(controls=rows, spacing=6, scroll=ft.ScrollMode.AUTO)

        return card(
            ft.Column(
                controls=[header, ft.Container(height=12), content],
                spacing=0,
            ),
            expand=True,
        )

    def _review_row(self, review: Dict) -> ft.Container:
        score = review.get("score") or 0
        pr_title = review.get("pr_title") or review.get("pr_url", "")[:50]
        repo = f"{review.get('repo_owner', '')}/{review.get('repo_name', '')}"
        created = review.get("created_at", "")
        if isinstance(created, str) and "T" in created:
            created = created.split("T")[0]

        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Column(
                        controls=[
                            ft.Text(
                                pr_title[:60],
                                size=13,
                                color=TEXT,
                                weight=ft.FontWeight.W_500,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                            ft.Row(
                                controls=[
                                    ft.Text(repo, size=11, color=TEXT_DIM),
                                    ft.Text("•", size=11, color=TEXT_DIM),
                                    ft.Text(str(created), size=11, color=TEXT_DIM),
                                    status_chip(review.get("status", "pending")),
                                ],
                                spacing=6,
                            ),
                        ],
                        spacing=3,
                        expand=True,
                    ),
                    ft.Column(
                        controls=[
                            score_badge(score),
                            ft.Text(
                                f"{review.get('total_findings', 0)} issues",
                                size=10,
                                color=TEXT_DIM,
                            ),
                        ],
                        spacing=3,
                        horizontal_alignment=ft.CrossAxisAlignment.END,
                    ),
                ],
                expand=True,
            ),
            bgcolor=SURFACE,
            border=ft.border.all(1, BORDER),
            border_radius=8,
            padding=ft.padding.symmetric(horizontal=14, vertical=10),
            on_click=lambda _, r=review: self._open_review(r),
            ink=True,
        )

    def _open_review(self, review: Dict) -> None:
        if self.on_open_review:
            self.on_open_review(review["id"])

    def _build_score_trend(self) -> ft.Container:
        header = section_header("Score Trend", "Last 10 reviews")
        trend = (self._stats or {}).get("score_trend", [])

        if not trend:
            content: ft.Control = ft.Container(
                content=empty_state("No trend data yet", icon="📈"),
                height=150,
                alignment=ft.alignment.center,
            )
        else:
            bars: List[ft.Control] = []
            for item in trend[-10:]:
                sc = item.get("score", 0) or 0
                from src.scoring import get_score_band
                _, col = get_score_band(sc)
                bars.append(
                    ft.Container(
                        content=ft.Tooltip(
                            message=f"Score: {sc:.0f}",
                            content=ft.Container(
                                bgcolor=col,
                                border_radius=ft.border_radius.only(top_left=4, top_right=4),
                                height=max(4, sc * 1.2),
                                width=18,
                            ),
                        )
                    )
                )
            content = ft.Column(
                controls=[
                    ft.Container(
                        content=ft.Row(
                            controls=bars,
                            spacing=4,
                            alignment=ft.MainAxisAlignment.CENTER,
                            vertical_alignment=ft.CrossAxisAlignment.END,
                        ),
                        height=130,
                        alignment=ft.alignment.bottom_center,
                    ),
                    ft.Text("← Older  Newer →", size=10, color=TEXT_DIM, text_align=ft.TextAlign.CENTER),
                ],
                spacing=4,
            )

        lang_section: List[ft.Control] = []
        top_langs = (self._stats or {}).get("top_languages", [])
        if top_langs:
            lang_section.append(ft.Container(height=12))
            lang_section.append(ft.Text("Top Languages", size=12, color=TEXT_DIM, weight=ft.FontWeight.W_600))
            for lang in top_langs[:5]:
                lang_section.append(
                    ft.Row(
                        controls=[
                            ft.Text(lang.get("language", "").capitalize(), size=11, color=TEXT),
                            ft.Container(expand=True),
                            ft.Text(str(lang.get("count", 0)), size=11, color=TEXT_DIM),
                        ]
                    )
                )

        return card(
            ft.Column(
                controls=[header, ft.Container(height=12), content] + lang_section,
                spacing=4,
            )
        )

    async def refresh(self) -> None:
        """Load data from API and refresh the view."""
        import httpx

        self._loading = True
        self.controls[0].content.controls = [self._build_loading()]
        if self._page:
            self._page.update()

        try:
            async with httpx.AsyncClient(base_url=self.api_base, timeout=15) as client:
                stats_resp = await client.get("/api/stats")
                reviews_resp = await client.get("/api/reviews", params={"page_size": 20})

                if stats_resp.status_code == 200:
                    self._stats = stats_resp.json()
                if reviews_resp.status_code == 200:
                    self._reviews = reviews_resp.json().get("items", [])
        except Exception as e:
            if self._page:
                show_snack(self._page, f"Failed to load data: {e}", error=True)

        self._loading = False
        self.controls[0].content.controls = [self._build_content()]
        if self._page:
            self._page.update()
