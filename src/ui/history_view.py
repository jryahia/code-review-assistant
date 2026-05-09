"""History view — past reviews with search and filter."""

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
    empty_state,
    loading_spinner,
    primary_button,
    score_badge,
    secondary_button,
    section_header,
    show_snack,
    stat_card,
    status_chip,
)


class HistoryView(ft.Column):
    """Search and filter past reviews."""

    def __init__(
        self,
        api_base: str,
        on_open_review: Optional[Callable] = None,
        page: Optional[ft.Page] = None,
    ) -> None:
        super().__init__(expand=True, spacing=0)
        self.api_base = api_base
        self.on_open_review = on_open_review
        self._page = page
        self._reviews: List[Dict] = []
        self._total = 0
        self._page_num = 1
        self._page_size = 20
        self._loading = False
        self._search_query = ""
        self._status_filter = "all"
        self._min_score = ""
        self._max_score = ""

        self._search_field = ft.TextField(
            hint_text="Search by repo name...",
            prefix_icon=ft.icons.SEARCH,
            bgcolor=SURFACE,
            border_color=BORDER,
            focused_border_color=ACCENT,
            label_style=ft.TextStyle(color=TEXT_DIM),
            text_style=ft.TextStyle(color=TEXT, size=12),
            hint_style=ft.TextStyle(color=TEXT_DIM + "80"),
            border_radius=8,
            on_change=self._on_search_change,
            on_submit=lambda _: self._page.run_task(self.refresh) if self._page else None,
            width=280,
        )
        self._status_dd = ft.Dropdown(
            value="all",
            options=[
                ft.dropdown.Option("all", "All Status"),
                ft.dropdown.Option("completed", "Completed"),
                ft.dropdown.Option("failed", "Failed"),
                ft.dropdown.Option("running", "Running"),
                ft.dropdown.Option("pending", "Pending"),
            ],
            width=150,
            bgcolor=SURFACE,
            border_color=BORDER,
            focused_border_color=ACCENT,
            text_style=ft.TextStyle(color=TEXT, size=12),
            on_change=self._on_filter_change,
        )
        self._min_score_field = ft.TextField(
            hint_text="Min",
            width=70,
            bgcolor=SURFACE,
            border_color=BORDER,
            focused_border_color=ACCENT,
            text_style=ft.TextStyle(color=TEXT, size=12),
            border_radius=8,
            on_change=self._on_score_change,
        )
        self._max_score_field = ft.TextField(
            hint_text="Max",
            width=70,
            bgcolor=SURFACE,
            border_color=BORDER,
            focused_border_color=ACCENT,
            text_style=ft.TextStyle(color=TEXT, size=12),
            border_radius=8,
            on_change=self._on_score_change,
        )
        self._reviews_container = ft.Column(
            controls=[loading_spinner()],
            spacing=6,
            expand=True,
        )
        self._pagination_row = ft.Row(spacing=8)
        self._build()

    def _build(self) -> None:
        self.controls = [
            ft.Container(
                content=ft.Column(
                    controls=[
                        section_header("Review History", "Search and filter past reviews"),
                        ft.Container(height=16),
                        # Filter bar
                        ft.Row(
                            controls=[
                                self._search_field,
                                self._status_dd,
                                ft.Row(
                                    controls=[
                                        ft.Text("Score:", size=12, color=TEXT_DIM),
                                        self._min_score_field,
                                        ft.Text("–", size=12, color=TEXT_DIM),
                                        self._max_score_field,
                                    ],
                                    spacing=6,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                                primary_button(
                                    "Search",
                                    on_click=lambda _: self._page.run_task(self.refresh) if self._page else None,
                                    icon=ft.icons.SEARCH,
                                ),
                            ],
                            spacing=10,
                            wrap=True,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Container(height=16),
                        self._reviews_container,
                        ft.Container(height=8),
                        self._pagination_row,
                    ],
                    scroll=ft.ScrollMode.AUTO,
                    expand=True,
                ),
                expand=True,
                bgcolor=BG,
                padding=ft.padding.all(24),
            )
        ]

    def _on_search_change(self, e: ft.ControlEvent) -> None:
        self._search_query = e.control.value or ""

    def _on_filter_change(self, e: ft.ControlEvent) -> None:
        self._status_filter = e.control.value or "all"
        if self._page:
            self._page.run_task(self.refresh)

    def _on_score_change(self, e: ft.ControlEvent) -> None:
        if e.control == self._min_score_field:
            self._min_score = e.control.value or ""
        else:
            self._max_score = e.control.value or ""

    async def refresh(self) -> None:
        """Load reviews from API."""
        import httpx

        self._reviews_container.controls = [loading_spinner("Loading...")]
        if self._page:
            self._page.update()

        params: Dict[str, Any] = {
            "page": self._page_num,
            "page_size": self._page_size,
        }
        if self._search_query:
            params["repo"] = self._search_query
        if self._status_filter != "all":
            params["status"] = self._status_filter
        try:
            if self._min_score:
                params["min_score"] = float(self._min_score)
            if self._max_score:
                params["max_score"] = float(self._max_score)
        except ValueError:
            pass

        try:
            async with httpx.AsyncClient(base_url=self.api_base, timeout=15) as client:
                resp = await client.get("/api/reviews", params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    self._reviews = data.get("items", [])
                    self._total = data.get("total", 0)
                    total_pages = data.get("pages", 1)
                else:
                    show_snack(self._page, f"Failed: {resp.status_code}", error=True)
                    return
        except Exception as ex:
            show_snack(self._page, f"Error: {ex}", error=True)
            self._reviews_container.controls = [
                empty_state("Failed to load reviews", str(ex), icon="❌")
            ]
            if self._page:
                self._page.update()
            return

        self._build_reviews_list()
        self._build_pagination(total_pages)
        if self._page:
            self._page.update()

    def _build_reviews_list(self) -> None:
        if not self._reviews:
            self._reviews_container.controls = [
                ft.Container(
                    content=empty_state(
                        "No reviews found",
                        "Try adjusting your search filters",
                        icon="🔍",
                    ),
                    height=300,
                    alignment=ft.alignment.center,
                )
            ]
            return

        rows: List[ft.Control] = [
            ft.Text(
                f"{self._total} review(s) found",
                size=11,
                color=TEXT_DIM,
            )
        ]
        for review in self._reviews:
            rows.append(self._build_review_row(review))

        self._reviews_container.controls = rows

    def _build_review_row(self, review: Dict) -> ft.Container:
        score = review.get("score") or 0
        pr_number = review.get("pr_number", "?")
        pr_title = review.get("pr_title") or f"PR #{pr_number}"
        repo = f"{review.get('repo_owner', '')}/{review.get('repo_name', '')}"
        created = str(review.get("created_at", ""))
        if "T" in created:
            created = created.replace("T", " ").split(".")[0]
        status = review.get("status", "pending")
        critical = review.get("critical_count", 0)
        warnings = review.get("warning_count", 0)
        files = review.get("files_changed", 0)

        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Column(
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Text(
                                        pr_title[:70],
                                        size=13,
                                        color=TEXT,
                                        weight=ft.FontWeight.W_500,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    ),
                                    status_chip(status),
                                ],
                                spacing=8,
                            ),
                            ft.Row(
                                controls=[
                                    ft.Text(repo, size=11, color=TEXT_DIM),
                                    ft.Text("•", size=11, color=TEXT_DIM),
                                    ft.Text(f"#{pr_number}", size=11, color=ACCENT),
                                    ft.Text("•", size=11, color=TEXT_DIM),
                                    ft.Text(created, size=11, color=TEXT_DIM),
                                    ft.Text("•", size=11, color=TEXT_DIM),
                                    ft.Text(f"{files} files", size=11, color=TEXT_DIM),
                                ],
                                spacing=6,
                            ),
                        ],
                        spacing=3,
                        expand=True,
                    ),
                    ft.Column(
                        controls=[
                            score_badge(score) if status == "completed" else status_chip(status),
                            ft.Row(
                                controls=[
                                    ft.Text(f"🔴{critical}", size=10, color=CRITICAL),
                                    ft.Text(f"🟡{warnings}", size=10, color=WARNING),
                                ],
                                spacing=8,
                            ),
                        ],
                        spacing=4,
                        horizontal_alignment=ft.CrossAxisAlignment.END,
                    ),
                    ft.Row(
                        controls=[
                            ft.IconButton(
                                icon=ft.icons.OPEN_IN_NEW,
                                icon_size=16,
                                icon_color=TEXT_DIM,
                                tooltip="Open Review",
                                on_click=lambda _, rid=review["id"]: self._open(rid),
                            ),
                            ft.IconButton(
                                icon=ft.icons.REFRESH,
                                icon_size=16,
                                icon_color=TEXT_DIM,
                                tooltip="Re-run",
                                on_click=lambda _, rid=review["id"]: self._page.run_task(
                                    self._rerun, rid
                                ) if self._page else None,
                            ),
                            ft.IconButton(
                                icon=ft.icons.DELETE_OUTLINE,
                                icon_size=16,
                                icon_color=CRITICAL + "aa",
                                tooltip="Delete",
                                on_click=lambda _, rid=review["id"]: self._page.run_task(
                                    self._delete, rid
                                ) if self._page else None,
                            ),
                        ],
                        spacing=0,
                    ),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=SURFACE,
            border=ft.border.all(1, BORDER),
            border_radius=8,
            padding=ft.padding.symmetric(horizontal=14, vertical=10),
        )

    def _build_pagination(self, total_pages: int) -> None:
        if total_pages <= 1:
            self._pagination_row.controls = []
            return

        btn_prev = ft.IconButton(
            icon=ft.icons.CHEVRON_LEFT,
            disabled=self._page_num <= 1,
            icon_color=ACCENT if self._page_num > 1 else TEXT_DIM,
            on_click=lambda _: self._go_page(self._page_num - 1),
        )
        btn_next = ft.IconButton(
            icon=ft.icons.CHEVRON_RIGHT,
            disabled=self._page_num >= total_pages,
            icon_color=ACCENT if self._page_num < total_pages else TEXT_DIM,
            on_click=lambda _: self._go_page(self._page_num + 1),
        )
        self._pagination_row.controls = [
            btn_prev,
            ft.Text(f"Page {self._page_num} of {total_pages}", size=12, color=TEXT_DIM),
            btn_next,
        ]

    def _go_page(self, page_num: int) -> None:
        self._page_num = page_num
        if self._page:
            self._page.run_task(self.refresh)

    def _open(self, review_id: str) -> None:
        if self.on_open_review:
            self.on_open_review(review_id)

    async def _rerun(self, review_id: str) -> None:
        import httpx
        try:
            async with httpx.AsyncClient(base_url=self.api_base, timeout=30) as client:
                resp = await client.post(f"/api/reviews/{review_id}/rerun")
            if resp.status_code in (200, 202):
                show_snack(self._page, "Re-run started!")
                await self.refresh()
            else:
                show_snack(self._page, f"Failed: {resp.text}", error=True)
        except Exception as ex:
            show_snack(self._page, f"Error: {ex}", error=True)

    async def _delete(self, review_id: str) -> None:
        import httpx
        try:
            async with httpx.AsyncClient(base_url=self.api_base, timeout=15) as client:
                resp = await client.delete(f"/api/reviews/{review_id}")
            if resp.status_code == 204:
                show_snack(self._page, "Review deleted")
                await self.refresh()
            else:
                show_snack(self._page, f"Delete failed: {resp.status_code}", error=True)
        except Exception as ex:
            show_snack(self._page, f"Error: {ex}", error=True)
