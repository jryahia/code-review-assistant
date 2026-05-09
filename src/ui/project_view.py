"""Project view — managed repos and auto-watch configuration."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

import flet as ft

from src.ui.components import (
    ACCENT,
    BG,
    BORDER,
    CARD,
    CRITICAL,
    SUCCESS,
    SURFACE,
    TEXT,
    TEXT_DIM,
    WARNING,
    card,
    divider,
    empty_state,
    label_text,
    loading_spinner,
    primary_button,
    secondary_button,
    section_header,
    show_snack,
    styled_input,
)


class ProjectView(ft.Column):
    """View for managing monitored repositories."""

    def __init__(
        self,
        api_base: str,
        page: Optional[ft.Page] = None,
    ) -> None:
        super().__init__(expand=True, spacing=0)
        self.api_base = api_base
        self._page = page
        self._projects: List[Dict] = []
        self._loading = True
        self._show_form = False

        self._form_name = styled_input("Project Name", "My Awesome Project")
        self._form_url = styled_input("Repository URL", "https://github.com/owner/repo")
        self._form_token = styled_input("GitHub Token", "ghp_...", password=True)
        self._form_description = styled_input("Description (optional)", multiline=True)
        self._form_auto_watch = ft.Switch(
            label="Auto-watch new PRs",
            value=False,
            active_color=ACCENT,
            label_style=ft.TextStyle(color=TEXT, size=12),
        )
        self._form_poll_interval = styled_input("Poll Interval (seconds)", "300", value="300")
        self._form_default_branch = styled_input("Default Branch", "main", value="main")
        self._form_categories = ft.TextField(
            label="Enabled Categories",
            hint_text="bugs,security,style,performance,architecture",
            value="bugs,security,style,performance,architecture",
            bgcolor=SURFACE,
            border_color=BORDER,
            focused_border_color=ACCENT,
            label_style=ft.TextStyle(color=TEXT_DIM),
            text_style=ft.TextStyle(color=TEXT, size=12),
            border_radius=8,
        )

        self._projects_list = ft.Column(spacing=8, expand=True)
        self._form_container = ft.Container(visible=False)
        self._build()

    def _build(self) -> None:
        self.controls = [
            ft.Container(
                content=ft.Column(
                    controls=[
                        section_header(
                            "Monitored Projects",
                            "Repositories with auto-review enabled",
                            actions=[
                                primary_button(
                                    "Add Project",
                                    on_click=self._toggle_form,
                                    icon=ft.icons.ADD,
                                )
                            ],
                        ),
                        ft.Container(height=16),
                        self._build_form(),
                        self._projects_list,
                    ],
                    scroll=ft.ScrollMode.AUTO,
                    expand=True,
                ),
                expand=True,
                bgcolor=BG,
                padding=ft.padding.all(24),
            )
        ]

    def _build_form(self) -> ft.Container:
        self._form_container = ft.Container(
            content=card(
                ft.Column(
                    controls=[
                        ft.Text("Add New Project", size=14, color=TEXT, weight=ft.FontWeight.W_600),
                        ft.Container(height=8),
                        ft.Row(controls=[self._form_name, self._form_url], spacing=12),
                        self._form_token,
                        self._form_description,
                        ft.Row(
                            controls=[self._form_default_branch, self._form_poll_interval],
                            spacing=12,
                        ),
                        self._form_categories,
                        self._form_auto_watch,
                        ft.Container(height=8),
                        ft.Row(
                            controls=[
                                primary_button("Save Project", on_click=lambda _: self._page.run_task(self._save_project) if self._page else None),
                                secondary_button("Cancel", on_click=self._toggle_form),
                            ],
                            spacing=12,
                            alignment=ft.MainAxisAlignment.END,
                        ),
                    ],
                    spacing=10,
                ),
                padding=20,
            ),
            visible=False,
            margin=ft.margin.only(bottom=16),
        )
        return self._form_container

    def _toggle_form(self, e: Optional[ft.ControlEvent] = None) -> None:
        self._form_container.visible = not self._form_container.visible
        if self._page:
            self._page.update()

    async def _save_project(self) -> None:
        name = self._form_name.value or ""
        repo_url = self._form_url.value or ""

        if not name.strip() or not repo_url.strip():
            show_snack(self._page, "Name and Repository URL are required", error=True)
            return
        if "github.com" not in repo_url:
            show_snack(self._page, "Must be a valid GitHub repository URL", error=True)
            return

        payload: Dict[str, Any] = {
            "name": name.strip(),
            "repo_url": repo_url.strip(),
            "auto_watch": self._form_auto_watch.value,
            "enabled_categories": self._form_categories.value or "bugs,security,style,performance,architecture",
            "default_branch": self._form_default_branch.value or "main",
        }
        if self._form_token.value:
            payload["github_token"] = self._form_token.value
        if self._form_description.value:
            payload["description"] = self._form_description.value
        try:
            payload["poll_interval"] = int(self._form_poll_interval.value or "300")
        except ValueError:
            payload["poll_interval"] = 300

        try:
            import httpx
            async with httpx.AsyncClient(base_url=self.api_base, timeout=15) as client:
                resp = await client.post("/api/projects", json=payload)
            if resp.status_code == 201:
                show_snack(self._page, "Project added successfully!")
                self._toggle_form()
                # Clear form
                for field in [self._form_name, self._form_url, self._form_token, self._form_description]:
                    field.value = ""
                self._form_auto_watch.value = False
                await self.refresh()
            elif resp.status_code == 409:
                show_snack(self._page, "This repository is already monitored", error=True)
            else:
                show_snack(self._page, f"Error: {resp.json().get('detail', resp.text)}", error=True)
        except Exception as ex:
            show_snack(self._page, f"Error: {ex}", error=True)

    async def refresh(self) -> None:
        """Load projects from API."""
        import httpx

        self._projects_list.controls = [loading_spinner("Loading projects...")]
        if self._page:
            self._page.update()

        try:
            async with httpx.AsyncClient(base_url=self.api_base, timeout=15) as client:
                resp = await client.get("/api/projects")
                if resp.status_code == 200:
                    self._projects = resp.json()
                else:
                    self._projects = []
        except Exception as ex:
            show_snack(self._page, f"Error loading projects: {ex}", error=True)
            self._projects = []

        self._build_projects_list()
        if self._page:
            self._page.update()

    def _build_projects_list(self) -> None:
        if not self._projects:
            self._projects_list.controls = [
                ft.Container(
                    content=empty_state(
                        "No projects yet",
                        "Add a GitHub repository to monitor its PRs automatically",
                        icon="📦",
                        action_label="Add First Project",
                        on_action=self._toggle_form,
                    ),
                    height=300,
                    alignment=ft.alignment.center,
                )
            ]
            return

        cards: List[ft.Control] = []
        for project in self._projects:
            cards.append(self._project_card(project))
        self._projects_list.controls = cards

    def _project_card(self, project: Dict) -> ft.Container:
        pid = project.get("id", "")
        name = project.get("name", "")
        repo_url = project.get("repo_url", "")
        owner = project.get("owner", "")
        repo = project.get("repo", "")
        auto_watch = project.get("auto_watch", False)
        poll = project.get("poll_interval", 300)
        branch = project.get("default_branch", "main")
        cats = project.get("enabled_categories", "")
        description = project.get("description", "")
        created = str(project.get("created_at", "")).split("T")[0]

        watch_indicator = ft.Container(
            content=ft.Text(
                "● AUTO" if auto_watch else "○ MANUAL",
                size=10,
                color=SUCCESS if auto_watch else TEXT_DIM,
                weight=ft.FontWeight.W_600,
            ),
            bgcolor=(SUCCESS + "22") if auto_watch else SURFACE,
            border=ft.border.all(1, SUCCESS if auto_watch else BORDER),
            border_radius=6,
            padding=ft.padding.symmetric(horizontal=8, vertical=3),
        )

        return card(
            ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Column(
                                controls=[
                                    ft.Text(name, size=14, color=TEXT, weight=ft.FontWeight.W_600),
                                    ft.Row(
                                        controls=[
                                            ft.Text(f"{owner}/{repo}", size=11, color=ACCENT),
                                            ft.Text("•", size=11, color=TEXT_DIM),
                                            ft.Text(f"Branch: {branch}", size=11, color=TEXT_DIM),
                                        ],
                                        spacing=6,
                                    ),
                                ],
                                spacing=3,
                                expand=True,
                            ),
                            watch_indicator,
                            ft.Row(
                                controls=[
                                    ft.IconButton(
                                        icon=ft.icons.REFRESH,
                                        icon_size=16,
                                        icon_color=TEXT_DIM,
                                        tooltip="Check for new PRs",
                                        on_click=lambda _, p=project: show_snack(self._page, f"Checking {p['name']}..."),
                                    ),
                                    ft.IconButton(
                                        icon=ft.icons.DELETE_OUTLINE,
                                        icon_size=16,
                                        icon_color=CRITICAL + "aa",
                                        tooltip="Remove project",
                                        on_click=lambda _, p_id=pid: self._page.run_task(self._delete_project, p_id) if self._page else None,
                                    ),
                                ],
                                spacing=0,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    ),
                    ft.Container(height=8),
                    *([ft.Text(description, size=11, color=TEXT_DIM)] if description else []),
                    ft.Row(
                        controls=[
                            ft.Container(
                                content=ft.Text(c.strip(), size=10, color=ACCENT),
                                bgcolor=ACCENT + "15",
                                border_radius=4,
                                padding=ft.padding.symmetric(horizontal=6, vertical=2),
                            )
                            for c in cats.split(",") if c.strip()
                        ],
                        spacing=4,
                        wrap=True,
                    ),
                    ft.Row(
                        controls=[
                            ft.Text(f"Poll: every {poll}s", size=10, color=TEXT_DIM),
                            ft.Text("•", size=10, color=TEXT_DIM),
                            ft.Text(f"Added: {created}", size=10, color=TEXT_DIM),
                        ],
                        spacing=6,
                    ),
                ],
                spacing=6,
            ),
            padding=16,
        )

    async def _delete_project(self, project_id: str) -> None:
        import httpx
        try:
            async with httpx.AsyncClient(base_url=self.api_base, timeout=15) as client:
                resp = await client.delete(f"/api/projects/{project_id}")
            if resp.status_code == 204:
                show_snack(self._page, "Project removed")
                await self.refresh()
            else:
                show_snack(self._page, f"Delete failed: {resp.status_code}", error=True)
        except Exception as ex:
            show_snack(self._page, f"Error: {ex}", error=True)
