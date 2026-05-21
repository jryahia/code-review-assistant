"""Analysis engine — orchestrates all checkers and aggregates results."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

import structlog

from src.analyzer.checkers import CheckerFinding
from src.analyzer.checkers.architecture_checker import ArchitectureChecker
from src.analyzer.checkers.bug_checker import BugChecker
from src.analyzer.checkers.performance_checker import PerformanceChecker
from src.analyzer.checkers.security_checker import SecurityChecker
from src.analyzer.checkers.style_checker import StyleChecker
from src.analyzer.parser import ParseResult, detect_language, is_supported, parse_content, parse_patch
from src.config import settings

logger = structlog.get_logger(__name__)

CHECKER_MAP = {
    "bugs": BugChecker(),
    "security": SecurityChecker(),
    "style": StyleChecker(),
    "performance": PerformanceChecker(),
    "architecture": ArchitectureChecker(),
}


@dataclass
class FileAnalysisResult:
    filename: str
    language: str
    lines_added: int
    lines_removed: int
    findings: List[CheckerFinding] = field(default_factory=list)
    score: float = 100.0
    parse_error: Optional[str] = None


@dataclass
class AnalysisResult:
    files: List[FileAnalysisResult] = field(default_factory=list)
    total_score: float = 100.0
    total_findings: int = 0
    critical_count: int = 0
    warning_count: int = 0
    suggestion_count: int = 0
    files_analyzed: int = 0
    files_skipped: int = 0


class AnalysisEngine:
    """Orchestrates all language analyzers and aggregates results."""

    def __init__(
        self,
        enabled_categories: Optional[List[str]] = None,
        ignore_patterns: Optional[List[str]] = None,
        max_file_size_kb: int = 500,
    ) -> None:
        self.enabled_categories: Set[str] = (
            set(enabled_categories) if enabled_categories else set(CHECKER_MAP.keys())
        )
        self.ignore_patterns: List[re.Pattern] = []
        self.max_file_size_bytes = max_file_size_kb * 1024

        for pat in (ignore_patterns or []):
            try:
                self.ignore_patterns.append(re.compile(pat))
            except re.error as e:
                logger.warning("Invalid ignore pattern", pattern=pat, error=str(e))

    def _should_ignore(self, filename: str) -> bool:
        for pat in self.ignore_patterns:
            if pat.search(filename):
                return True
        return False

    def _is_too_large(self, content: str) -> bool:
        return len(content.encode()) > self.max_file_size_bytes

    async def analyze_files(
        self,
        files: List[Dict],
        default_content_fetcher: Optional[callable] = None,
    ) -> AnalysisResult:
        """
        Analyze a list of file dicts from GitHub API.
        Each dict has: filename, patch (optional), status, additions, deletions.
        """
        result = AnalysisResult()
        tasks = [
            self._analyze_file(f, default_content_fetcher)
            for f in files
        ]
        file_results = await asyncio.gather(*tasks, return_exceptions=True)

        all_findings: List[CheckerFinding] = []

        for fr in file_results:
            if isinstance(fr, Exception):
                logger.error("File analysis failed", error=str(fr))
                result.files_skipped += 1
                continue
            if fr is None:
                # None indicates the file was legitimately excluded (removed, unsupported, ignored)
                # These are not counted as skipped — they were intentionally filtered out.
                continue
            result.files.append(fr)
            result.files_analyzed += 1
            all_findings.extend(fr.findings)

        result.total_findings = len(all_findings)
        result.critical_count = sum(1 for f in all_findings if f.severity == "critical")
        result.warning_count = sum(1 for f in all_findings if f.severity == "warning")
        result.suggestion_count = sum(1 for f in all_findings if f.severity == "suggestion")
        result.total_score = self._calculate_aggregate_score(result.files)

        return result

    async def _analyze_file(
        self,
        file_info: Dict,
        content_fetcher: Optional[callable] = None,
    ) -> Optional[FileAnalysisResult]:
        filename = file_info.get("filename", "")
        status = file_info.get("status", "modified")
        patch = file_info.get("patch", "")

        if status == "removed":
            return None

        if self._should_ignore(filename):
            logger.debug("Ignoring file", filename=filename)
            return None

        language = detect_language(filename)
        if not is_supported(language):
            logger.debug("Unsupported language", filename=filename, language=language)
            return None

        additions = file_info.get("additions", 0)
        deletions = file_info.get("deletions", 0)

        # Use patch content if no raw content fetcher
        if patch:
            content = _extract_content_from_patch(patch)
        elif content_fetcher:
            try:
                content = await content_fetcher(filename)
            except Exception as e:
                logger.warning("Failed to fetch file content", filename=filename, error=str(e))
                content = ""
        else:
            content = ""

        if not content.strip():
            return FileAnalysisResult(
                filename=filename,
                language=language,
                lines_added=additions,
                lines_removed=deletions,
            )

        if self._is_too_large(content):
            logger.warning("File too large, skipping analysis", filename=filename)
            return FileAnalysisResult(
                filename=filename,
                language=language,
                lines_added=additions,
                lines_removed=deletions,
                parse_error="File too large for analysis",
            )

        try:
            parsed = parse_content(content, language)
            findings = await asyncio.get_event_loop().run_in_executor(
                None, self._run_checkers, parsed, filename
            )
            score = self._calculate_file_score(findings)
            return FileAnalysisResult(
                filename=filename,
                language=language,
                lines_added=additions,
                lines_removed=deletions,
                findings=findings,
                score=score,
                parse_error=parsed.parse_error,
            )
        except Exception as e:
            logger.error("Error analyzing file", filename=filename, error=str(e))
            return FileAnalysisResult(
                filename=filename,
                language=language,
                lines_added=additions,
                lines_removed=deletions,
                parse_error=str(e),
            )

    def _run_checkers(self, parsed: ParseResult, filename: str) -> List[CheckerFinding]:
        findings: List[CheckerFinding] = []
        for category, checker in CHECKER_MAP.items():
            if category not in self.enabled_categories:
                continue
            try:
                result = checker.check(parsed, filename)
                findings.extend(result)
            except Exception as e:
                logger.error(
                    "Checker failed",
                    category=category,
                    filename=filename,
                    error=str(e),
                )
        # Deduplicate findings by (category, line_number, rule_id)
        return _deduplicate_findings(findings)

    def _calculate_file_score(self, findings: List[CheckerFinding]) -> float:
        penalty = sum(
            10 if f.severity == "critical"
            else 5 if f.severity == "warning"
            else 1
            for f in findings
        )
        return max(0.0, min(100.0, 100.0 - penalty))

    def _calculate_aggregate_score(self, files: List[FileAnalysisResult]) -> float:
        if not files:
            return 100.0
        total_penalty = 0.0
        for fr in files:
            for finding in fr.findings:
                if finding.severity == "critical":
                    total_penalty += 10
                elif finding.severity == "warning":
                    total_penalty += 5
                else:
                    total_penalty += 1
        # Normalize: up to 200 penalty = 0 score
        normalized = total_penalty / max(len(files) * 2, 1)
        return max(0.0, min(100.0, 100.0 - normalized))


def _extract_content_from_patch(patch: str) -> str:
    """Extract added/context lines from a unified diff patch."""
    lines = []
    for line in patch.splitlines():
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            continue
        if line.startswith("+"):
            lines.append(line[1:])
        elif not line.startswith("-"):
            lines.append(line.lstrip(" "))
    return "\n".join(lines)


def _deduplicate_findings(findings: List[CheckerFinding]) -> List[CheckerFinding]:
    seen: Set[tuple] = set()
    result: List[CheckerFinding] = []
    for f in findings:
        key = (f.category, f.line_number, f.rule_id or f.message[:50])
        if key not in seen:
            seen.add(key)
            result.append(f)
    return result
