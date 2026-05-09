"""LLM-based semantic code review using OpenAI or Claude."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import structlog

from src.config import settings

logger = structlog.get_logger(__name__)


@dataclass
class AIReviewResult:
    summary: str
    suggestions: List[Dict[str, str]]
    overall_assessment: str
    provider: str


SYSTEM_PROMPT = """You are an expert code reviewer. Analyze the provided code diff and give a concise,
actionable review. Focus on:
1. Logic errors and correctness issues
2. Security vulnerabilities
3. Performance bottlenecks
4. Architectural concerns
5. Best practices for the language

Be specific, cite line numbers when possible, and provide concrete fix suggestions.
Return your response as JSON with this structure:
{
  "summary": "2-3 sentence overview",
  "overall_assessment": "positive|needs_work|critical_issues",
  "suggestions": [
    {"severity": "critical|warning|suggestion", "message": "...", "fix": "..."}
  ]
}"""


class AIReviewer:
    """Semantic code review using OpenAI or Anthropic Claude."""

    def __init__(
        self,
        provider: Optional[str] = None,
        openai_key: Optional[str] = None,
        claude_key: Optional[str] = None,
    ) -> None:
        self.provider = provider or settings.ai_provider
        self.openai_key = openai_key or settings.openai_api_key
        self.claude_key = claude_key or settings.claude_api_key

    async def review(
        self,
        filename: str,
        language: str,
        patch: str,
        existing_findings: List[Dict] = None,
    ) -> Optional[AIReviewResult]:
        """Generate AI semantic review for a file diff."""
        if self.provider == "off" or not patch.strip():
            return None

        prompt = self._build_prompt(filename, language, patch, existing_findings or [])

        try:
            if self.provider == "openai":
                return await self._review_openai(prompt)
            elif self.provider == "claude":
                return await self._review_claude(prompt)
        except Exception as e:
            logger.error("AI review failed", provider=self.provider, error=str(e))
        return None

    def _build_prompt(
        self,
        filename: str,
        language: str,
        patch: str,
        existing_findings: List[Dict],
    ) -> str:
        findings_text = ""
        if existing_findings:
            findings_text = "\n\nStatic analysis already found:\n" + "\n".join(
                f"- [{f.get('severity', '?').upper()}] Line {f.get('line_number', '?')}: {f.get('message', '')}"
                for f in existing_findings[:10]
            )

        # Truncate patch to avoid context limits
        truncated_patch = patch[:6000] + ("\n... (truncated)" if len(patch) > 6000 else "")

        return (
            f"Review this {language} file: `{filename}`\n\n"
            f"```diff\n{truncated_patch}\n```"
            f"{findings_text}\n\n"
            f"Provide additional semantic insights not already covered by static analysis."
        )

    async def _review_openai(self, prompt: str) -> Optional[AIReviewResult]:
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=self.openai_key)
            response = await client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=1500,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or "{}"
            return self._parse_response(raw, "openai")
        except ImportError:
            logger.error("openai package not installed")
            return None

    async def _review_claude(self, prompt: str) -> Optional[AIReviewResult]:
        try:
            import anthropic

            client = anthropic.AsyncAnthropic(api_key=self.claude_key)
            response = await client.messages.create(
                model=settings.claude_model,
                max_tokens=1500,
                system=SYSTEM_PROMPT + "\n\nAlways return valid JSON.",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )
            raw = response.content[0].text if response.content else "{}"
            # Claude may wrap JSON in markdown code block
            raw = _extract_json(raw)
            return self._parse_response(raw, "claude")
        except ImportError:
            logger.error("anthropic package not installed")
            return None

    def _parse_response(self, raw: str, provider: str) -> Optional[AIReviewResult]:
        try:
            data: Dict[str, Any] = json.loads(raw)
            return AIReviewResult(
                summary=data.get("summary", ""),
                suggestions=data.get("suggestions", []),
                overall_assessment=data.get("overall_assessment", "needs_work"),
                provider=provider,
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to parse AI response", error=str(e))
            return AIReviewResult(
                summary=raw[:500] if raw else "AI review unavailable",
                suggestions=[],
                overall_assessment="needs_work",
                provider=provider,
            )

    async def summarize_review(
        self,
        pr_title: str,
        files_summary: List[Dict],
        total_score: float,
    ) -> str:
        """Generate an overall PR summary from per-file results."""
        if self.provider == "off":
            return _generate_default_summary(pr_title, files_summary, total_score)

        files_text = "\n".join(
            f"- {f['filename']}: score={f.get('score', 0):.0f}, "
            f"critical={f.get('critical', 0)}, warning={f.get('warning', 0)}"
            for f in files_summary[:20]
        )
        prompt = (
            f"PR: {pr_title}\n"
            f"Overall score: {total_score:.1f}/100\n\n"
            f"Files analyzed:\n{files_text}\n\n"
            f"Write a 3-4 sentence executive summary of this code review. "
            f"Be specific about the main concerns and overall code quality."
        )

        try:
            if self.provider == "openai":
                from openai import AsyncOpenAI
                client = AsyncOpenAI(api_key=self.openai_key)
                response = await client.chat.completions.create(
                    model=settings.openai_model,
                    messages=[
                        {"role": "system", "content": "You are a senior code reviewer. Write concise, professional summaries."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                    max_tokens=400,
                )
                return response.choices[0].message.content or ""
            elif self.provider == "claude":
                import anthropic
                client = anthropic.AsyncAnthropic(api_key=self.claude_key)
                response = await client.messages.create(
                    model=settings.claude_model,
                    max_tokens=400,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                )
                return response.content[0].text if response.content else ""
        except Exception as e:
            logger.error("AI summarize failed", error=str(e))

        return _generate_default_summary(pr_title, files_summary, total_score)


def _extract_json(text: str) -> str:
    """Extract JSON from markdown code block if present."""
    import re
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


def _generate_default_summary(
    pr_title: str, files_summary: List[Dict], total_score: float
) -> str:
    from src.scoring import get_score_label
    label = get_score_label(total_score)
    critical = sum(f.get("critical", 0) for f in files_summary)
    warnings = sum(f.get("warning", 0) for f in files_summary)
    return (
        f"Code review completed for '{pr_title}'. "
        f"Overall score: {total_score:.1f}/100 ({label}). "
        f"Found {critical} critical issue(s) and {warnings} warning(s) across "
        f"{len(files_summary)} file(s). "
        f"{'Address critical issues before merging.' if critical > 0 else 'No critical issues found.'}"
    )
