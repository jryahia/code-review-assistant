"""Shared UI components — FindingCard, ScoreBadge, SeverityBadge, StatCard, ScoreGauge."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

import flet as ft

# ── Theme Colors ──────────────────────────────────────────────────────────────
BG = "#0f1117"
SURFACE = "#1a1d27"
CARD = "#222733"
ACCENT = "#4f8cff"
ACCENT_DIM = "#2a4a8a"
TEXT = "#e2e8f0"
TEXT_DIM = "#94a3b8"
BORDER = "#2d3448"

CRITICAL = "#ef4444"
WARNING = "#fbbf24"
SUGGESTION = "#4f8cff"
SUCCESS = "#22c55e"

SEVERITY_COLORS = {
    "critical": CRITICAL,
    "warning": WARNING,
    "suggestion": SUGGESTION,
}

CATEGORY_ICONS = {
    "bugs": "🐛",
    "security": "🔒",
    "performance": "⚡",
    "architecture": "🏗",
    "style": "✨",
}


def card(
    content: ft.Control,
    padding: int = 16,
    margin: int = 0,
    border_radius: int = 10,
    bgcolor: str = CARD,
    expand: bool = False,
) -> ft.Container:
    return ft.Container(
        content=content,
        bgcolor=bgcolor,
        border_radius=border_radius,
        padding=padding,
        margin=margin,
        expand=expand,
        border=ft.border.all(1, BORDER),
    )


def section_title(text: str) -> ft.Text:
    return ft.Text(text, size=14, weight=ft.FontWeight.W_600, color=TEXT)


def label_text(text: str) -> ft.Text:
    return ft.Text(text, size=11, color=TEXT_DIM)


def body_text(text: str, selectable: bool = False) -> ft.Text:
    return ft.Text(text, size=12, color=TEXT, selectable=selectable)


def divider() -> ft.Divider:
    return ft.Divider(height=1, color=BORDER)


# ── Score Gauge ───────────────────────────────────────────────────────────────

def score_gauge(score: float, size: float = 120) -> ft.Container:
    """Circular score gauge using a progress ring."""
    from src.scoring import get_score_band, get_score_label
    _, color = get_score_band(score)
    label_str = get_score_label(score)

    return ft.Container(
        content=ft.Stack(
            controls=[
                ft.Container(
                    content=ft.ProgressRing(
                        value=score / 100,
                        width=size,
                        height=size,
                        stroke_width=8,
                        color=color,
                        bgcolor=BORDER,
                    ),
                    alignment=ft.alignment.center,
                ),
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Text(
                                f"{score:.0f}",
                                size=size * 0.22,
                                weight=ft.FontWeight.BOLD,
                                color=color,
                                text_align=ft.TextAlign.CENTER,
                            ),
                            ft.Text(
                                label_str,
                                size=size * 0.09,
                                color=TEXT_DIM,
                                text_align=ft.TextAlign.CENTER,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=0,
                    ),
                    width=size,
                    height=size,
                    alignment=ft.alignment.center,
                ),
            ],
            width=size,
            height=size,
        ),
        width=size,
        height=size,
    )


# ── Severity Badge ─────────────────────────────────────────────────────────────

def severity_badge(severity: str) -> ft.Container:
    color = SEVERITY_COLORS.get(severity.lower(), TEXT_DIM)
    bg_color = color + "22"
    label = severity.upper()
    return ft.Container(
        content=ft.Text(label, size=9, weight=ft.FontWeight.BOLD, color=color),
        bgcolor=bg_color,
        border=ft.border.all(1, color + "55"),
        border_radius=4,
        padding=ft.padding.symmetric(horizontal=6, vertical=2),
    )


# ── Score Badge ────────────────────────────────────────────────────────────────

def score_badge(score: float, size: int = 12) -> ft.Container:
    from src.scoring import get_score_band
    _, color = get_score_band(score)
    return ft.Container(
        content=ft.Text(f"{score:.0f}", size=size, weight=ft.FontWeight.BOLD, color=color),
        bgcolor=color + "22",
        border=ft.border.all(1, color + "55"),
        border_radius=6,
        padding=ft.padding.symmetric(horizontal=8, vertical=3),
    )


# ── Stat Card ──────────────────────────────────────────────────────────────────

def stat_card(
    label: str,
    value: str,
    color: str = ACCENT,
    icon: Optional[str] = None,
    width: Optional[int] = None,
) -> ft.Container:
    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Text(icon or "", size=18) if icon else ft.Container(),
                        ft.Text(label, size=11, color=TEXT_DIM),
                    ],
                    spacing=4,
                ),
                ft.Text(value, size=22, weight=ft.FontWeight.BOLD, color=color),
            ],
            spacing=4,
        ),
        bgcolor=CARD,
        border=ft.border.all(1, BORDER),
        border_radius=10,
        padding=ft.padding.all(16),
        width=width,
    )


# ── Finding Card ───────────────────────────────────────────────────────────────

def finding_card(
    finding: Dict[str, Any],
    filename: Optional[str] = None,
    expanded: bool = False,
) -> ft.Container:
    severity = finding.get("severity", "suggestion")
    color = SEVERITY_COLORS.get(severity.lower(), TEXT_DIM)
    category = finding.get("category", "")
    icon = CATEGORY_ICONS.get(category, "•")
    line_no = finding.get("line_number")
    message = finding.get("message", "")
    snippet = finding.get("code_snippet", "")
    suggestion = finding.get("suggestion", "")

    header_controls: List[ft.Control] = [
        severity_badge(severity),
        ft.Text(f"{icon} {category.capitalize()}", size=11, color=TEXT_DIM),
    ]
    if line_no:
        header_controls.append(
            ft.Container(
                content=ft.Text(f":{line_no}", size=10, color=TEXT_DIM),
                bgcolor=SURFACE,
                border_radius=4,
                padding=ft.padding.symmetric(horizontal=5, vertical=2),
            )
        )
    if filename:
        header_controls.append(
            ft.Text(
                filename.split("/")[-1],
                size=10,
                color=TEXT_DIM,
                overflow=ft.TextOverflow.ELLIPSIS,
            )
        )

    body_controls: List[ft.Control] = [
        ft.Row(controls=header_controls, spacing=6, wrap=True),
        ft.Text(message, size=12, color=TEXT),
    ]

    if snippet:
        body_controls.append(
            ft.Container(
                content=ft.Text(
                    snippet[:200],
                    size=11,
                    color=TEXT_DIM,
                    font_family="monospace",
                    selectable=True,
                ),
                bgcolor=SURFACE,
                border_radius=6,
                border=ft.border.only(left=ft.BorderSide(3, color)),
                padding=ft.padding.all(8),
            )
        )

    if suggestion:
        body_controls.append(
            ft.Row(
                controls=[
                    ft.Text("💡", size=12),
                    ft.Text(suggestion, size=11, color=ACCENT, italic=True),
                ],
                spacing=4,
            )
        )

    return ft.Container(
        content=ft.Column(controls=body_controls, spacing=6),
        bgcolor=SURFACE,
        border=ft.border.only(left=ft.BorderSide(3, color)),
        border_radius=8,
        padding=ft.padding.all(12),
        margin=ft.margin.only(bottom=4),
    )


# ── File Tree Item ─────────────────────────────────────────────────────────────

def file_tree_item(
    filename: str,
    score: float,
    findings_count: int,
    language: str,
    on_click: Optional[Callable] = None,
    selected: bool = False,
) -> ft.Container:
    from src.scoring import get_score_band
    _, color = get_score_band(score)
    short_name = filename.split("/")[-1]
    dir_path = "/".join(filename.split("/")[:-1])

    return ft.Container(
        content=ft.Row(
            controls=[
                ft.Column(
                    controls=[
                        ft.Text(short_name, size=12, color=TEXT, weight=ft.FontWeight.W_500),
                        ft.Text(dir_path, size=10, color=TEXT_DIM) if dir_path else ft.Container(),
                    ],
                    spacing=2,
                    expand=True,
                ),
                ft.Column(
                    controls=[
                        score_badge(score, size=10),
                        ft.Text(f"{findings_count} issues", size=10, color=TEXT_DIM),
                    ],
                    spacing=2,
                    horizontal_alignment=ft.CrossAxisAlignment.END,
                ),
            ],
            expand=True,
        ),
        bgcolor=ACCENT_DIM if selected else SURFACE,
        border=ft.border.all(1, ACCENT if selected else BORDER),
        border_radius=6,
        padding=ft.padding.symmetric(horizontal=10, vertical=8),
        margin=ft.margin.only(bottom=4),
        on_click=on_click,
        ink=True,
    )


# ── Loading Spinner ────────────────────────────────────────────────────────────

def loading_spinner(message: str = "Loading...") -> ft.Column:
    return ft.Column(
        controls=[
            ft.ProgressRing(color=ACCENT),
            ft.Text(message, size=12, color=TEXT_DIM),
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        alignment=ft.MainAxisAlignment.CENTER,
        spacing=12,
    )


# ── Empty State ────────────────────────────────────────────────────────────────

def empty_state(
    title: str,
    subtitle: str = "",
    icon: str = "📭",
    action_label: Optional[str] = None,
    on_action: Optional[Callable] = None,
) -> ft.Column:
    controls: List[ft.Control] = [
        ft.Text(icon, size=48),
        ft.Text(title, size=16, weight=ft.FontWeight.W_600, color=TEXT),
    ]
    if subtitle:
        controls.append(ft.Text(subtitle, size=12, color=TEXT_DIM, text_align=ft.TextAlign.CENTER))
    if action_label and on_action:
        controls.append(
            ft.ElevatedButton(
                action_label,
                on_click=on_action,
                bgcolor=ACCENT,
                color=TEXT,
            )
        )
    return ft.Column(
        controls=controls,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        alignment=ft.MainAxisAlignment.CENTER,
        spacing=10,
    )


# ── Status Chip ────────────────────────────────────────────────────────────────

def status_chip(status: str) -> ft.Container:
    colors_map = {
        "completed": SUCCESS,
        "running": ACCENT,
        "pending": WARNING,
        "failed": CRITICAL,
    }
    color = colors_map.get(status, TEXT_DIM)
    return ft.Container(
        content=ft.Text(status.capitalize(), size=10, color=color, weight=ft.FontWeight.W_600),
        bgcolor=color + "22",
        border=ft.border.all(1, color + "55"),
        border_radius=10,
        padding=ft.padding.symmetric(horizontal=8, vertical=3),
    )


# ── Section Header ─────────────────────────────────────────────────────────────

def section_header(title: str, subtitle: str = "", actions: Optional[List[ft.Control]] = None) -> ft.Row:
    title_col = ft.Column(
        controls=[
            ft.Text(title, size=16, weight=ft.FontWeight.BOLD, color=TEXT),
            ft.Text(subtitle, size=12, color=TEXT_DIM) if subtitle else ft.Container(height=0),
        ],
        spacing=2,
        expand=True,
    )
    controls: List[ft.Control] = [title_col]
    if actions:
        controls.extend(actions)
    return ft.Row(controls=controls, alignment=ft.MainAxisAlignment.SPACE_BETWEEN)


# ── Input Field ────────────────────────────────────────────────────────────────

def styled_input(
    label: str,
    hint: str = "",
    value: str = "",
    password: bool = False,
    multiline: bool = False,
    on_change: Optional[Callable] = None,
    expand: bool = False,
) -> ft.TextField:
    return ft.TextField(
        label=label,
        hint_text=hint,
        value=value,
        password=password,
        can_reveal_password=password,
        multiline=multiline,
        max_lines=4 if multiline else 1,
        on_change=on_change,
        expand=expand,
        bgcolor=SURFACE,
        border_color=BORDER,
        focused_border_color=ACCENT,
        label_style=ft.TextStyle(color=TEXT_DIM, size=12),
        text_style=ft.TextStyle(color=TEXT, size=12),
        hint_style=ft.TextStyle(color=TEXT_DIM + "80", size=11),
        border_radius=8,
    )


# ── Primary Button ─────────────────────────────────────────────────────────────

def primary_button(
    text: str,
    on_click: Optional[Callable] = None,
    icon: Optional[str] = None,
    disabled: bool = False,
    loading: bool = False,
    width: Optional[int] = None,
) -> ft.ElevatedButton:
    return ft.ElevatedButton(
        text=text if not loading else "Loading...",
        icon=icon,
        on_click=on_click,
        disabled=disabled or loading,
        bgcolor=ACCENT if not disabled else BORDER,
        color=TEXT,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=8),
            padding=ft.padding.symmetric(horizontal=20, vertical=12),
        ),
        width=width,
    )


def secondary_button(
    text: str,
    on_click: Optional[Callable] = None,
    icon: Optional[str] = None,
    disabled: bool = False,
) -> ft.OutlinedButton:
    return ft.OutlinedButton(
        text=text,
        icon=icon,
        on_click=on_click,
        disabled=disabled,
        style=ft.ButtonStyle(
            color=TEXT,
            side=ft.BorderSide(1, BORDER),
            shape=ft.RoundedRectangleBorder(radius=8),
            padding=ft.padding.symmetric(horizontal=16, vertical=10),
        ),
    )


# ── Notification Snackbar ──────────────────────────────────────────────────────

def show_snack(page: ft.Page, message: str, error: bool = False) -> None:
    page.snack_bar = ft.SnackBar(
        content=ft.Text(message, color=TEXT),
        bgcolor=CRITICAL if error else CARD,
        duration=3000,
    )
    page.snack_bar.open = True
    page.update()
