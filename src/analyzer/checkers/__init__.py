"""Code checkers package."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class CheckerFinding:
    """A single finding from a checker."""
    category: str
    severity: str
    line_number: Optional[int]
    end_line: Optional[int]
    message: str
    code_snippet: Optional[str] = None
    suggestion: Optional[str] = None
    rule_id: Optional[str] = None
