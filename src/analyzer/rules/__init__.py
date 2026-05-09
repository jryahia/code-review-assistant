"""Language-specific rule definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Pattern
import re


@dataclass
class Rule:
    """A single analysis rule."""
    id: str
    category: str
    severity: str
    message: str
    pattern: Optional[str] = None
    suggestion: Optional[str] = None
    languages: List[str] = field(default_factory=list)

    def compiled(self) -> Optional[re.Pattern[str]]:
        if self.pattern:
            return re.compile(self.pattern, re.MULTILINE | re.IGNORECASE)
        return None


def get_rules_for_language(language: str) -> List[Rule]:
    """Return all applicable rules for a given language."""
    from src.analyzer.rules import (
        python_rules,
        javascript_rules,
        typescript_rules,
        go_rules,
        rust_rules,
        java_rules,
        ruby_rules,
        solidity_rules,
    )

    rule_map: Dict[str, List[Rule]] = {
        "python": python_rules.RULES,
        "javascript": javascript_rules.RULES,
        "typescript": typescript_rules.RULES,
        "go": go_rules.RULES,
        "rust": rust_rules.RULES,
        "java": java_rules.RULES,
        "ruby": ruby_rules.RULES,
        "solidity": solidity_rules.RULES,
    }

    universal_rules: List[Rule] = [
        Rule(
            id="SEC001",
            category="security",
            severity="critical",
            message="Hardcoded password detected",
            pattern=r'password\s*=\s*["\'][^"\']{4,}["\']',
            suggestion="Use environment variables or a secrets manager instead of hardcoded passwords.",
            languages=["*"],
        ),
        Rule(
            id="SEC002",
            category="security",
            severity="critical",
            message="Hardcoded API key or secret detected",
            pattern=r'(api_key|apikey|secret_key|access_token|auth_token)\s*=\s*["\'][^"\']{8,}["\']',
            suggestion="Store API keys in environment variables or a secure vault.",
            languages=["*"],
        ),
        Rule(
            id="SEC003",
            category="security",
            severity="critical",
            message="Private key material detected in source code",
            pattern=r'-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----',
            suggestion="Never commit private keys to source control. Use environment variables or a secrets manager.",
            languages=["*"],
        ),
        Rule(
            id="PERF001",
            category="performance",
            severity="warning",
            message="Potential N+1 query: database query inside a loop",
            pattern=r'for\s+.+:\s*\n(?:\s+.*\n)*?\s+.*(\.filter\(|\.find\(|\.query\(|SELECT)',
            suggestion="Batch the queries outside the loop or use eager loading.",
            languages=["*"],
        ),
    ]

    lang_rules = rule_map.get(language.lower(), [])
    return universal_rules + lang_rules
