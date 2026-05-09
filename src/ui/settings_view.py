"""Settings view — tokens, AI config, rules toggle, theme, log level."""

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
    label_text,
    loading_spinner,
    primary_button,
    secondary_button,
    section_header,
    show_snack,
    stat_card,
    styled_input,
)


class SettingsView(ft.Column):
    """Application settings — tokens, AI provider, analysis defaults."""

    def __init__(
        self,
        api_base: str,
        page: Optional[ft.Page] = None,
    ) -> None:
        super().__init__(expand=True, spacing=0)
        self.api_base = api_base
        self._page = page
        self._current_settings: Dict[str, Any] = {}
        self._loading = True

        self._github_token = ft.TextField(
            label="GitHub Personal Access Token",
            hint_text="ghp_...",
            password=True,
            can_reveal_password=True,
            bgcolor=SURFACE,
            border_color=BORDER,
            focused_border_color=ACCENT,
            label_style=ft.TextStyle(color=TEXT_DIM),
            text_style=ft.TextStyle(color=TEXT, size=12),
            border_radius=8,
            expand=True,
        )
        self._webhook_secret = ft.TextField(
            label="GitHub Webhook Secret",
            hint_text="your_webhook_secret",
            password=True,
            can_reveal_password=True,
            bgcolor=SURFACE,
            border_color=BORDER,
            focused_border_color=ACCENT,
            label_style=ft.TextStyle(color=TEXT_DIM),
            text_style=ft.TextStyle(color=TEXT, size=12),
            border_radius=8,
            expand=True,
        )
        self._ai_provider_dd = ft.Dropdown(
            label="AI Provider",
            options=[
                ft.dropdown.Option("off", "Off (Static Analysis Only)"),
                ft.dropdown.Option("openai", "OpenAI GPT"),
                ft.dropdown.Option("claude", "Anthropic Claude"),
            ],
            value="off",
            bgcolor=SURFACE,
            border_color=BORDER,
            focused_border_color=ACCENT,
            label_style=ft.TextStyle(color=TEXT_DIM),
            text_style=ft.TextStyle(color=TEXT, size=12),
            width=280,
            on_change=self._on_provider_change,
        )
        self._openai_key = ft.TextField(
            label="OpenAI API Key",
            hint_text="sk-...",
            password=True,
            can_reveal_password=True,
            bgcolor=SURFACE,
            border_color=BORDER,
            focused_border_color=ACCENT,
            label_style=ft.TextStyle(color=TEXT_DIM),
            text_style=ft.TextStyle(color=TEXT, size=12),
            border_radius=8,
            expand=True,
        )
        self._openai_model = ft.Dropdown(
            label="OpenAI Model",
            options=[
                ft.dropdown.Option("gpt-4o", "GPT-4o"),
                ft.dropdown.Option("gpt-4o-mini", "GPT-4o Mini"),
                ft.dropdown.Option("gpt-4-turbo", "GPT-4 Turbo"),
                ft.dropdown.Option("gpt-3.5-turbo", "GPT-3.5 Turbo"),
            ],
            value="gpt-4o",
            bgcolor=SURFACE,
            border_color=BORDER,
            focused_border_color=ACCENT,
            label_style=ft.TextStyle(color=TEXT_DIM),
            text_style=ft.TextStyle(color=TEXT, size=12),
            width=200,
        )
        self._claude_key = ft.TextField(
            label="Anthropic API Key",
            hint_text="sk-ant-...",
            password=True,
            can_reveal_password=True,
            bgcolor=SURFACE,
            border_color=BORDER,
            focused_border_color=ACCENT,
            label_style=ft.TextStyle(color=TEXT_DIM),
            text_style=ft.TextStyle(color=TEXT, size=12),
            border_radius=8,
            expand=True,
        )
        self._claude_model = ft.Dropdown(
            label="Claude Model",
            options=[
                ft.dropdown.Option("claude-3-5-sonnet-20241022", "Claude 3.5 Sonnet"),
                ft.dropdown.Option("claude-opus-4-7", "Claude Opus 4.7"),
                ft.dropdown.Option("claude-sonnet-4-6", "Claude Sonnet 4.6"),
                ft.dropdown.Option("claude-haiku-4-5-20251001", "Claude Haiku 4.5"),
            ],
            value="claude-3-5-sonnet-20241022",
            bgcolor=SURFACE,
            border_color=BORDER,
            focused_border_color=ACCENT,
            label_style=ft.TextStyle(color=TEXT_DIM),
            text_style=ft.TextStyle(color=TEXT, size=12),
            width=250,
        )
        self._default_categories = ft.TextField(
            label="Default Analysis Categories",
            hint_text="bugs,security,style,performance,architecture",
            bgcolor=SURFACE,
            border_color=BORDER,
            focused_border_color=ACCENT,
            label_style=ft.TextStyle(color=TEXT_DIM),
            text_style=ft.TextStyle(color=TEXT, size=12),
            border_radius=8,
            expand=True,
        )
        self._max_file_size = ft.TextField(
            label="Max File Size (KB)",
            hint_text="500",
            bgcolor=SURFACE,
            border_color=BORDER,
            focused_border_color=ACCENT,
            label_style=ft.TextStyle(color=TEXT_DIM),
            text_style=ft.TextStyle(color=TEXT, size=12),
            border_radius=8,
            width=150,
        )
        self._poll_interval = ft.TextField(
            label="Poll Interval (seconds)",
            hint_text="300",
            bgcolor=SURFACE,
            border_color=BORDER,
            focused_border_color=ACCENT,
            label_style=ft.TextStyle(color=TEXT_DIM),
            text_style=ft.TextStyle(color=TEXT, size=12),
            border_radius=8,
            width=180,
        )
        self._log_level_dd = ft.Dropdown(
            label="Log Level",
            options=[
                ft.dropdown.Option("DEBUG", "Debug"),
                ft.dropdown.Option("INFO", "Info"),
                ft.dropdown.Option("WARNING", "Warning"),
                ft.dropdown.Option("ERROR", "Error"),
            ],
            value="INFO",
            bgcolor=SURFACE,
            border_color=BORDER,
            focused_border_color=ACCENT,
            label_style=ft.TextStyle(color=TEXT_DIM),
            text_style=ft.TextStyle(color=TEXT, size=12),
            width=180,
        )
        self._api_port = ft.TextField(
            label="API Port",
            hint_text="8765",
            bgcolor=SURFACE,
            border_color=BORDER,
            focused_border_color=ACCENT,
            label_style=ft.TextStyle(color=TEXT_DIM),
            text_style=ft.TextStyle(color=TEXT, size=12),
            border_radius=8,
            width=120,
        )
        self._openai_section = ft.Container(visible=False)
        self._claude_section = ft.Container(visible=False)
        self._build()

    def _build(self) -> None:
        self.controls = [
            ft.Container(
                content=ft.Column(
                    controls=[
                        section_header("Settings", "Configure tokens, AI provider, and analysis defaults"),
                        ft.Container(height=20),
                        self._build_github_section(),
                        ft.Container(height=16),
                        self._build_ai_section(),
                        ft.Container(height=16),
                        self._build_analysis_section(),
                        ft.Container(height=16),
                        self._build_system_section(),
                        ft.Container(height=16),
                        ft.Row(
                            controls=[
                                primary_button(
                                    "Save Settings",
                                    on_click=lambda _: self._page.run_task(self._save) if self._page else None,
                                ),
                                secondary_button(
                                    "Test GitHub Token",
                                    on_click=lambda _: self._page.run_task(self._test_github) if self._page else None,
                                ),
                            ],
                            spacing=12,
                        ),
                        ft.Container(height=20),
                        self._build_webhook_info(),
                    ],
                    scroll=ft.ScrollMode.AUTO,
                    expand=True,
                ),
                expand=True,
                bgcolor=BG,
                padding=ft.padding.all(24),
            )
        ]

    def _build_github_section(self) -> ft.Container:
        return card(
            ft.Column(
                controls=[
                    ft.Text("GitHub Integration", size=13, color=TEXT, weight=ft.FontWeight.W_600),
                    ft.Container(height=8),
                    ft.Text(
                        "Required for fetching PR diffs. Create a token at github.com/settings/tokens with `repo` scope.",
                        size=11,
                        color=TEXT_DIM,
                    ),
                    ft.Container(height=8),
                    self._github_token,
                    self._webhook_secret,
                ],
                spacing=8,
            ),
            padding=20,
        )

    def _build_ai_section(self) -> ft.Container:
        self._openai_section = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(controls=[self._openai_key, self._openai_model], spacing=12),
                ],
                spacing=8,
            ),
            visible=False,
        )
        self._claude_section = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(controls=[self._claude_key, self._claude_model], spacing=12),
                ],
                spacing=8,
            ),
            visible=False,
        )
        return card(
            ft.Column(
                controls=[
                    ft.Text("AI Review Provider", size=13, color=TEXT, weight=ft.FontWeight.W_600),
                    ft.Container(height=8),
                    ft.Text(
                        "Enable AI semantic review for deeper code analysis (optional).",
                        size=11,
                        color=TEXT_DIM,
                    ),
                    ft.Container(height=8),
                    self._ai_provider_dd,
                    self._openai_section,
                    self._claude_section,
                ],
                spacing=8,
            ),
            padding=20,
        )

    def _build_analysis_section(self) -> ft.Container:
        return card(
            ft.Column(
                controls=[
                    ft.Text("Analysis Defaults", size=13, color=TEXT, weight=ft.FontWeight.W_600),
                    ft.Container(height=8),
                    self._default_categories,
                    ft.Row(controls=[self._max_file_size, self._poll_interval], spacing=12),
                ],
                spacing=8,
            ),
            padding=20,
        )

    def _build_system_section(self) -> ft.Container:
        return card(
            ft.Column(
                controls=[
                    ft.Text("System", size=13, color=TEXT, weight=ft.FontWeight.W_600),
                    ft.Container(height=8),
                    ft.Row(controls=[self._log_level_dd, self._api_port], spacing=12),
                ],
                spacing=8,
            ),
            padding=20,
        )

    def _build_webhook_info(self) -> ft.Container:
        from src.config import settings
        port = settings.api_port
        return card(
            ft.Column(
                controls=[
                    ft.Text("GitHub Webhook Setup", size=13, color=TEXT, weight=ft.FontWeight.W_600),
                    ft.Container(height=8),
                    ft.Text(
                        "To receive auto-review events, add a webhook to your GitHub repository:",
                        size=11,
                        color=TEXT_DIM,
                    ),
                    ft.Container(height=4),
                    ft.Row(
                        controls=[
                            ft.Text("Payload URL:", size=11, color=TEXT_DIM, width=100),
                            ft.Container(
                                content=ft.Text(
                                    f"http://your-server:{port}/api/webhooks/github",
                                    size=11,
                                    color=ACCENT,
                                    selectable=True,
                                    font_family="monospace",
                                ),
                                bgcolor=SURFACE,
                                padding=ft.padding.symmetric(horizontal=8, vertical=4),
                                border_radius=4,
                            ),
                        ],
                        spacing=8,
                    ),
                    ft.Row(
                        controls=[
                            ft.Text("Content Type:", size=11, color=TEXT_DIM, width=100),
                            ft.Text("application/json", size=11, color=TEXT),
                        ],
                        spacing=8,
                    ),
                    ft.Row(
                        controls=[
                            ft.Text("Events:", size=11, color=TEXT_DIM, width=100),
                            ft.Text("Pull requests, Pushes", size=11, color=TEXT),
                        ],
                        spacing=8,
                    ),
                ],
                spacing=6,
            ),
            bgcolor=SURFACE,
            padding=20,
        )

    def _on_provider_change(self, e: ft.ControlEvent) -> None:
        provider = e.control.value
        self._openai_section.visible = provider == "openai"
        self._claude_section.visible = provider == "claude"
        if self._page:
            self._page.update()

    async def load(self) -> None:
        """Load current settings from API."""
        import httpx
        try:
            async with httpx.AsyncClient(base_url=self.api_base, timeout=15) as client:
                resp = await client.get("/api/settings")
                if resp.status_code == 200:
                    self._current_settings = resp.json()
                    self._populate_fields()
        except Exception as ex:
            show_snack(self._page, f"Error loading settings: {ex}", error=True)

    def _populate_fields(self) -> None:
        s = self._current_settings
        has_github = s.get("github_token", "")
        self._github_token.hint_text = "*** (saved)" if has_github else "ghp_..."
        self._webhook_secret.hint_text = "*** (saved)" if s.get("github_webhook_secret") else "webhook_secret"

        provider = s.get("ai_provider", "off")
        self._ai_provider_dd.value = provider
        self._openai_section.visible = provider == "openai"
        self._claude_section.visible = provider == "claude"

        has_oai = s.get("openai_api_key", "")
        self._openai_key.hint_text = "*** (saved)" if has_oai else "sk-..."
        self._openai_model.value = s.get("openai_model", "gpt-4o")

        has_cl = s.get("claude_api_key", "")
        self._claude_key.hint_text = "*** (saved)" if has_cl else "sk-ant-..."
        self._claude_model.value = s.get("claude_model", "claude-3-5-sonnet-20241022")

        self._default_categories.value = s.get("default_categories", "bugs,security,style,performance,architecture")
        self._max_file_size.value = str(s.get("max_file_size_kb", 500))
        self._poll_interval.value = str(s.get("poll_interval_seconds", 300))
        self._log_level_dd.value = s.get("log_level", "INFO")
        self._api_port.value = str(s.get("api_port", 8765))

        if self._page:
            self._page.update()

    async def _save(self) -> None:
        payload: Dict[str, Any] = {}

        if self._github_token.value:
            payload["github_token"] = self._github_token.value
        if self._webhook_secret.value:
            payload["github_webhook_secret"] = self._webhook_secret.value

        provider = self._ai_provider_dd.value
        if provider:
            payload["ai_provider"] = provider
        if self._openai_key.value:
            payload["openai_api_key"] = self._openai_key.value
        if self._openai_model.value:
            payload["openai_model"] = self._openai_model.value
        if self._claude_key.value:
            payload["claude_api_key"] = self._claude_key.value
        if self._claude_model.value:
            payload["claude_model"] = self._claude_model.value

        if self._default_categories.value:
            payload["default_categories"] = self._default_categories.value
        try:
            if self._max_file_size.value:
                payload["max_file_size_kb"] = int(self._max_file_size.value)
            if self._poll_interval.value:
                payload["poll_interval_seconds"] = int(self._poll_interval.value)
            if self._api_port.value:
                payload["api_port"] = int(self._api_port.value)
        except ValueError:
            show_snack(self._page, "Invalid number in port/size/interval fields", error=True)
            return

        if self._log_level_dd.value:
            payload["log_level"] = self._log_level_dd.value

        try:
            import httpx
            async with httpx.AsyncClient(base_url=self.api_base, timeout=15) as client:
                resp = await client.put("/api/settings", json=payload)
            if resp.status_code == 200:
                show_snack(self._page, "Settings saved successfully!")
                self._current_settings = resp.json()
            else:
                show_snack(self._page, f"Error: {resp.text}", error=True)
        except Exception as ex:
            show_snack(self._page, f"Error saving settings: {ex}", error=True)

    async def _test_github(self) -> None:
        token_val = self._github_token.value
        if not token_val:
            from src.config import settings
            token_val = settings.github_token
        if not token_val:
            show_snack(self._page, "Enter a GitHub token first", error=True)
            return
        try:
            from src.github_client import GitHubClient
            async with GitHubClient(token=token_val) as client:
                user = await client.verify_token()
            show_snack(self._page, f"✅ Token valid — logged in as @{user.get('login', '?')}")
        except Exception as ex:
            show_snack(self._page, f"❌ Token invalid: {ex}", error=True)

    async def refresh(self) -> None:
        await self.load()
