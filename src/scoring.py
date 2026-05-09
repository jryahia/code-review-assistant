"""Score calculation with weighted severity."""

from __future__ import annotations

from typing import List, Optional, Sequence

from src.analyzer.checkers import CheckerFinding
from src.analyzer.engine import FileAnalysisResult

SEVERITY_WEIGHTS = {
    "critical": 10,
    "warning": 5,
    "suggestion": 1,
}

SCORE_BANDS = [
    (90, 100, "Excellent", "#22c55e"),
    (70, 89, "Good", "#4f8cff"),
    (40, 69, "Needs Work", "#fbbf24"),
    (0, 39, "Poor", "#ef4444"),
]


def calculate_score(findings: Sequence[CheckerFinding]) -> float:
    """Calculate a 0-100 score from a list of findings."""
    if not findings:
        return 100.0
    penalty = sum(SEVERITY_WEIGHTS.get(f.severity, 1) for f in findings)
    return max(0.0, min(100.0, 100.0 - penalty))


def calculate_file_score(file_result: FileAnalysisResult) -> float:
    return calculate_score(file_result.findings)


def calculate_aggregate_score(file_results: List[FileAnalysisResult]) -> float:
    """Weighted aggregate: files with more findings drag the score down more."""
    if not file_results:
        return 100.0

    all_findings: List[CheckerFinding] = []
    for fr in file_results:
        all_findings.extend(fr.findings)

    return calculate_score(all_findings)


def get_score_band(score: float) -> tuple[str, str]:
    """Return (label, color) for a score."""
    for low, high, label, color in SCORE_BANDS:
        if low <= score <= high:
            return label, color
    return "Poor", "#ef4444"


def get_score_color(score: float) -> str:
    _, color = get_score_band(score)
    return color


def get_score_label(score: float) -> str:
    label, _ = get_score_band(score)
    return label


def severity_color(severity: str) -> str:
    return {
        "critical": "#ef4444",
        "warning": "#fbbf24",
        "suggestion": "#4f8cff",
    }.get(severity.lower(), "#94a3b8")


def severity_rank(severity: str) -> int:
    return {"critical": 0, "warning": 1, "suggestion": 2}.get(severity.lower(), 3)


def sort_findings(findings: List[CheckerFinding]) -> List[CheckerFinding]:
    """Sort findings: critical first, then warning, then suggestion, then by line."""
    return sorted(
        findings,
        key=lambda f: (severity_rank(f.severity), f.line_number or 0),
    )


def score_summary(score: float) -> dict:
    label, color = get_score_band(score)
    return {
        "score": round(score, 1),
        "label": label,
        "color": color,
        "percentage": round(score),
    }
