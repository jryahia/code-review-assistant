"""Architecture checker — magic numbers, god functions, deep nesting, SOLID violations."""

from __future__ import annotations

import ast
import re
from typing import List

from src.analyzer.checkers import CheckerFinding
from src.analyzer.parser import (
    ParseResult,
    count_function_lines,
    measure_max_nesting,
)
from src.analyzer.rules import get_rules_for_language

GOD_FUNCTION_THRESHOLD = 100
DEEP_NESTING_THRESHOLD = 4
MAGIC_NUMBER_MIN = 3  # numbers >= this (excluding 0,1,2,-1) are flagged

# Numbers that are universally acceptable
ACCEPTABLE_NUMBERS = {0, 1, 2, -1, 100, 1000, 10, 60, 24, 7, 365, 256, 512, 1024}

# Patterns for missing error handling
MISSING_ERROR_PATTERNS: list[tuple[str, list[str], str, str]] = [
    (
        r"async\s+function\s+\w+[^{]*\{(?:[^{}]|\{[^{}]*\})*?await\s+[^;]+;(?![^{}]*catch)",
        ["javascript", "typescript"],
        "Async function with await but no try/catch — unhandled rejections crash the process",
        "ARCH-ERR001",
    ),
    (
        r"fetch\s*\([^)]+\)(?:\s*\.then\s*\([^)]+\))*(?!\s*\.catch)",
        ["javascript", "typescript"],
        "fetch() without .catch() — network errors will be unhandled",
        "ARCH-ERR002",
    ),
    (
        r"go\s+func\s*\([^)]*\)\s*\{[^}]*\}(?!\s*\(\))",
        ["go"],
        "Goroutine launched without panic recovery — panics will crash the whole program",
        "ARCH-ERR003",
    ),
]

# SOLID violation patterns
SOLID_PATTERNS: list[tuple[str, str, str, str]] = [
    (
        r"class\s+\w+[^{]*\{(?:[^{}]|\{[^{}]*\}){2000,}",
        "God class: extremely large class violates Single Responsibility Principle",
        "ARCH-SRP001",
        "Split this class into smaller, focused classes.",
    ),
    (
        r"isinstance\s*\([^,]+,\s*\([^)]+\)\s*\)",
        "Multiple type checks may indicate violation of Open/Closed Principle",
        "ARCH-OCP001",
        "Use polymorphism or strategy pattern instead of type-checking.",
    ),
    (
        r"def\s+\w+\([^)]*\):[^)]*\n(?:\s+[^\n]+\n){50,}",
        "Function exceeds 50 lines — possible Single Responsibility violation",
        "ARCH-SRP002",
        "Refactor into smaller focused functions.",
    ),
]


class ArchitectureChecker:
    """Detects architectural issues and code smell patterns."""

    CATEGORY = "architecture"

    def check(self, parsed: ParseResult, filename: str) -> List[CheckerFinding]:
        findings: List[CheckerFinding] = []
        content = parsed.raw_content
        language = parsed.language
        lines = content.splitlines()

        # Language-specific rule checks
        for rule in get_rules_for_language(language):
            if rule.category != self.CATEGORY:
                continue
            pattern = rule.compiled()
            if not pattern:
                continue
            for match in pattern.finditer(content):
                line_num = content[: match.start()].count("\n") + 1
                snippet = lines[line_num - 1].strip() if 0 < line_num <= len(lines) else ""
                findings.append(
                    CheckerFinding(
                        category=self.CATEGORY,
                        severity=rule.severity,
                        line_number=line_num,
                        end_line=line_num,
                        message=rule.message,
                        code_snippet=snippet,
                        suggestion=rule.suggestion,
                        rule_id=rule.id,
                    )
                )

        # God function detection
        findings.extend(self._check_god_functions(parsed, lines))

        # Deep nesting detection
        findings.extend(self._check_deep_nesting(parsed, content, lines))

        # Magic numbers detection
        findings.extend(self._check_magic_numbers(content, language, lines))

        # Missing error handling
        findings.extend(self._check_missing_error_handling(content, language, lines))

        # Python-specific architectural checks
        if language == "python" and parsed.ast_tree:
            findings.extend(self._python_arch_ast(parsed, lines))

        # General TODO/FIXME detection
        findings.extend(self._check_todo_comments(content, language, lines))

        return findings

    def _check_god_functions(self, parsed: ParseResult, lines: List[str]) -> List[CheckerFinding]:
        findings: List[CheckerFinding] = []
        for func in parsed.functions:
            length = count_function_lines(func)
            if length > GOD_FUNCTION_THRESHOLD:
                snippet = lines[func.start_line - 1].strip() if 0 < func.start_line <= len(lines) else ""
                findings.append(
                    CheckerFinding(
                        category=self.CATEGORY,
                        severity="warning",
                        line_number=func.start_line,
                        end_line=func.end_line,
                        message=f"God function: `{func.name}` is {length} lines — violates Single Responsibility",
                        code_snippet=snippet,
                        suggestion="Break this function into smaller, focused helper functions.",
                        rule_id="ARCH-GOD001",
                    )
                )
        return findings

    def _check_deep_nesting(
        self, parsed: ParseResult, content: str, lines: List[str]
    ) -> List[CheckerFinding]:
        findings: List[CheckerFinding] = []
        for func in parsed.functions:
            if not func.body:
                continue
            max_depth = measure_max_nesting(func.body)
            if max_depth > DEEP_NESTING_THRESHOLD:
                snippet = lines[func.start_line - 1].strip() if 0 < func.start_line <= len(lines) else ""
                findings.append(
                    CheckerFinding(
                        category=self.CATEGORY,
                        severity="suggestion",
                        line_number=func.start_line,
                        end_line=func.end_line,
                        message=f"Deep nesting ({max_depth} levels) in `{func.name}` — hard to read and test",
                        code_snippet=snippet,
                        suggestion="Use early returns, guard clauses, or extract nested logic into helper functions.",
                        rule_id="ARCH-NEST001",
                    )
                )
        return findings

    def _check_magic_numbers(self, content: str, language: str, lines: List[str]) -> List[CheckerFinding]:
        findings: List[CheckerFinding] = []

        # Match numeric literals not preceded by quotes, word chars, or dot
        pattern = re.compile(
            r"(?<!['\"\w.])\b(\d{" + str(MAGIC_NUMBER_MIN) + r",})\b(?!['\"])",
            re.MULTILINE,
        )

        for match in pattern.finditer(content):
            number = int(match.group(1))
            if number in ACCEPTABLE_NUMBERS:
                continue
            line_num = content[: match.start()].count("\n") + 1
            raw_line = lines[line_num - 1] if 0 < line_num <= len(lines) else ""
            # Skip constant definitions (UPPER_CASE = 1234)
            if re.match(r"\s*[A-Z_]+\s*=", raw_line):
                continue
            # Skip comment lines
            stripped = raw_line.strip()
            if stripped.startswith(("#", "//", "*")):
                continue
            # Skip import/require lines
            if re.match(r"\s*(import|from|require|#include)", raw_line):
                continue

            findings.append(
                CheckerFinding(
                    category=self.CATEGORY,
                    severity="suggestion",
                    line_number=line_num,
                    end_line=line_num,
                    message=f"Magic number `{number}` — define as a named constant",
                    code_snippet=stripped,
                    suggestion=f"Define `CONSTANT_NAME = {number}` at the module/class level.",
                    rule_id="ARCH-MAG001",
                )
            )
        return findings

    def _check_missing_error_handling(
        self, content: str, language: str, lines: List[str]
    ) -> List[CheckerFinding]:
        findings: List[CheckerFinding] = []
        for pattern, langs, message, rule_id in MISSING_ERROR_PATTERNS:
            if language not in langs:
                continue
            for match in re.finditer(pattern, content, re.MULTILINE | re.DOTALL):
                line_num = content[: match.start()].count("\n") + 1
                snippet = lines[line_num - 1].strip() if 0 < line_num <= len(lines) else ""
                findings.append(
                    CheckerFinding(
                        category=self.CATEGORY,
                        severity="warning",
                        line_number=line_num,
                        end_line=line_num,
                        message=message,
                        code_snippet=snippet,
                        suggestion="Add error handling to prevent silent failures.",
                        rule_id=rule_id,
                    )
                )
        return findings

    def _check_todo_comments(self, content: str, language: str, lines: List[str]) -> List[CheckerFinding]:
        findings: List[CheckerFinding] = []
        if language in ("python", "ruby"):
            comment_pattern = re.compile(r"#\s*(TODO|FIXME|HACK|XXX|BUG)\b[^\n]*", re.IGNORECASE)
        else:
            comment_pattern = re.compile(r"//\s*(TODO|FIXME|HACK|XXX|BUG)\b[^\n]*", re.IGNORECASE)

        for match in comment_pattern.finditer(content):
            line_num = content[: match.start()].count("\n") + 1
            snippet = lines[line_num - 1].strip() if 0 < line_num <= len(lines) else ""
            tag = match.group(1).upper()
            severity = "warning" if tag in ("BUG", "FIXME") else "suggestion"
            findings.append(
                CheckerFinding(
                    category=self.CATEGORY,
                    severity=severity,
                    line_number=line_num,
                    end_line=line_num,
                    message=f"{tag} comment: incomplete or workaround code",
                    code_snippet=snippet,
                    suggestion="Resolve the issue or create a tracked ticket.",
                    rule_id=f"ARCH-{tag}001",
                )
            )
        return findings

    def _python_arch_ast(self, parsed: ParseResult, lines: List[str]) -> List[CheckerFinding]:
        findings: List[CheckerFinding] = []
        tree = parsed.ast_tree

        class ArchVisitor(ast.NodeVisitor):
            def __init__(self) -> None:
                self.findings: List[CheckerFinding] = []

            def visit_ClassDef(self, node: ast.ClassDef) -> None:
                # Count methods in class
                methods = [n for n in ast.walk(node) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                if len(methods) > 20:
                    line = node.lineno
                    snippet = lines[line - 1].strip() if 0 < line <= len(lines) else ""
                    self.findings.append(
                        CheckerFinding(
                            category="architecture",
                            severity="warning",
                            line_number=line,
                            end_line=node.end_lineno or line,
                            message=f"God class `{node.name}` has {len(methods)} methods — violates SRP",
                            code_snippet=snippet,
                            suggestion="Split into multiple focused classes.",
                            rule_id="PY-ARCH-AST001",
                        )
                    )

                # Check for missing __init__ docstring
                end = node.end_lineno or node.lineno
                class_len = end - node.lineno
                if class_len > 50:
                    init_methods = [
                        n for n in node.body
                        if isinstance(n, ast.FunctionDef) and n.name == "__init__"
                    ]
                    if not init_methods:
                        line = node.lineno
                        snippet = lines[line - 1].strip() if 0 < line <= len(lines) else ""
                        self.findings.append(
                            CheckerFinding(
                                category="architecture",
                                severity="suggestion",
                                line_number=line,
                                end_line=end,
                                message=f"Large class `{node.name}` has no `__init__` — consider using dataclass",
                                code_snippet=snippet,
                                suggestion="Use @dataclass decorator for data-holding classes.",
                                rule_id="PY-ARCH-AST002",
                            )
                        )
                self.generic_visit(node)

            def visit_If(self, node: ast.If) -> None:
                # Detect isinstance chains (potential OCP violation)
                checks: List[str] = []
                current = node
                while isinstance(current, ast.If):
                    if (
                        isinstance(current.test, ast.Call)
                        and isinstance(current.test.func, ast.Name)
                        and current.test.func.id == "isinstance"
                    ):
                        checks.append("isinstance")
                    if current.orelse and len(current.orelse) == 1:
                        current = current.orelse[0]
                    else:
                        break

                if len(checks) >= 3:
                    line = node.lineno
                    snippet = lines[line - 1].strip() if 0 < line <= len(lines) else ""
                    self.findings.append(
                        CheckerFinding(
                            category="architecture",
                            severity="suggestion",
                            line_number=line,
                            end_line=line,
                            message=f"Chain of {len(checks)} isinstance() checks — consider polymorphism",
                            code_snippet=snippet,
                            suggestion="Use inheritance, ABCs, or @singledispatch instead of isinstance chains.",
                            rule_id="PY-ARCH-AST003",
                        )
                    )
                self.generic_visit(node)

        visitor = ArchVisitor()
        visitor.visit(tree)
        return visitor.findings
