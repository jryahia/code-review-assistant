"""Flet desktop application shell — routing, navigation, dark theme."""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Callable, Dict, Optional

import flet as ft

from src.ui.components import (
    ACCENT,
    BG,
    BORDER,
    CARD,
    SURFACE,
    TEXT,
    TEXT_DIM,
    show_snack,
)

NAV_ITEMS = [
    ("dashboard", ft.icons.DASHBOARD_OUTLINED, ft.icons.DASHBOARD, "Dashboard"),
    ("new_review", ft.icons.ADD_CIRCLE_OUTLINE, ft.icons.ADD_CIRCLE, "New Review"),
    ("history", ft.icons.HISTORY_OUTLINED, ft.icons.HISTORY, "History"),
    ("projects", ft.icons.FOLDER_OUTLINED, ft.icons.FOLDER, "Projects"),
    ("settings", ft.icons.SETTINGS_OUTLINED, ft.icons.SETTINGS, "Settings"),
]


def launch_ui(api_port: int = 8765) -> None:
    """Launch the Flet desktop application."""

    def main(page: ft.Page) -> None:
        api_base = f"http://127.0.0.1:{api_port}"

        # ── Page configuration ──────────────────────────────────────────────
        page.title = "Code Review Assistant"
        page.theme_mode = ft.ThemeMode.DARK
        page.bgcolor = BG
        page.window_width = 1280
        page.window_height = 820
        page.window_min_width = 900
        page.window_min_height = 600
        page.padding = 0

        page.theme = ft.Theme(
            color_scheme_seed=ACCENT,
            visual_density=ft.VisualDensity.COMPACT,
        )

        # ── State ───────────────────────────────────────────────────────────
        state: Dict[str, Any] = {
            "route": "dashboard",
            "review_id": None,
        }

        # ── Import views lazily ─────────────────────────────────────────────
        from src.ui.dashboard import DashboardView
        from src.ui.history_view import HistoryView
        from src.ui.project_view import ProjectView
        from src.ui.review_view import NewReviewView, ReviewDetailView
        from src.ui.settings_view import SettingsView

        # ── Create view instances ───────────────────────────────────────────
        dashboard_view = DashboardView(
            api_base=api_base,
            on_new_review=lambda: navigate("new_review"),
            on_open_review=lambda rid: navigate("review_detail", review_id=rid),
            page=page,
        )
        new_review_view = NewReviewView(
            api_base=api_base,
            on_review_started=lambda rid: navigate("review_detail", review_id=rid),
            page=page,
        )
        history_view = HistoryView(
            api_base=api_base,
            on_open_review=lambda rid: navigate("review_detail", review_id=rid),
            page=page,
        )
        project_view = ProjectView(api_base=api_base, page=page)
        settings_view = SettingsView(api_base=api_base, page=page)

        # Detail view created dynamically
        detail_view_holder: Dict[str, Optional[ReviewDetailView]] = {"view": None}

        # ── Navigation ──────────────────────────────────────────────────────
        content_area = ft.Container(expand=True, bgcolor=BG)
        nav_rail = _build_nav_rail(state, navigate_fn=None)

        def navigate(route: str, review_id: Optional[str] = None) -> None:
            state["route"] = route
            state["review_id"] = review_id
            _update_nav(nav_rail, route)

            if route == "dashboard":
                content_area.content = dashboard_view
                page.run_task(dashboard_view.refresh)

            elif route == "new_review":
                content_area.content = new_review_view

            elif route == "history":
                content_area.content = history_view
                page.run_task(history_view.refresh)

            elif route == "projects":
                content_area.content = project_view
                page.run_task(project_view.refresh)

            elif route == "settings":
                content_area.content = settings_view
                page.run_task(settings_view.refresh)

            elif route == "review_detail" and review_id:
                dv = ReviewDetailView(
                    review_id=review_id,
                    api_base=api_base,
                    on_back=lambda: navigate("history"),
                    page=page,
                )
                detail_view_holder["view"] = dv
                content_area.content = dv
                page.run_task(dv.load)

            page.update()

        # Wire up nav rail
        nav_rail.on_change = lambda e: navigate(NAV_ITEMS[e.control.selected_index][0])

        # ── Header bar ──────────────────────────────────────────────────────
        header = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Text("⚡", size=20),
                            ft.Text(
                                "Code Review Assistant",
                                size=16,
                                weight=ft.FontWeight.BOLD,
                                color=TEXT,
                            ),
                        ],
                        spacing=8,
                    ),
                    ft.Container(expand=True),
                    ft.Container(
                        content=ft.Row(
                            controls=[
                                ft.Container(
                                    width=8,
                                    height=8,
                                    bgcolor="#22c55e",
                                    border_radius=4,
                                ),
                                ft.Text(f"API :{8765}", size=11, color=TEXT_DIM),
                            ],
                            spacing=6,
                        ),
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=CARD,
            padding=ft.padding.symmetric(horizontal=20, vertical=12),
            border=ft.border.only(bottom=ft.BorderSide(1, BORDER)),
        )

        # ── Main layout ─────────────────────────────────────────────────────
        page.add(
            ft.Column(
                controls=[
                    header,
                    ft.Row(
                        controls=[
                            ft.Container(
                                content=nav_rail,
                                bgcolor=SURFACE,
                                border=ft.border.only(right=ft.BorderSide(1, BORDER)),
                                width=220,
                            ),
                            content_area,
                        ],
                        expand=True,
                        spacing=0,
                    ),
                ],
                expand=True,
                spacing=0,
            )
        )

        # ── Initial navigation ──────────────────────────────────────────────
        navigate("dashboard")

    ft.app(target=main)


def _build_nav_rail(state: Dict, navigate_fn: Optional[Callable]) -> ft.NavigationRail:
    destinations = [
        ft.NavigationRailDestination(
            icon=icon_outlined,
            selected_icon=icon_filled,
            label=label,
        )
        for _, icon_outlined, icon_filled, label in NAV_ITEMS
    ]

    return ft.NavigationRail(
        selected_index=0,
        label_type=ft.NavigationRailLabelType.ALL,
        bgcolor=SURFACE,
        destinations=destinations,
        indicator_color=ACCENT + "22",
        indicator_shape=ft.RoundedRectangleBorder(radius=10),
        selected_label_style=ft.TextStyle(color=ACCENT, size=11, weight=ft.FontWeight.W_600),
        unselected_label_style=ft.TextStyle(color=TEXT_DIM, size=11),
        leading=ft.Container(height=12),
        min_width=220,
        extended=True,
    )


def _update_nav(nav_rail: ft.NavigationRail, route: str) -> None:
    route_map = {item[0]: i for i, item in enumerate(NAV_ITEMS)}
    idx = route_map.get(route, 0)
    if route == "review_detail":
        return
    nav_rail.selected_index = idx
