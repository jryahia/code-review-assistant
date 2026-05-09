"""Style checker — naming conventions, line length, cyclomatic complexity, duplicate code."""

from __future__ import annotations

import ast
import re
from collections import Counter
from typing import List, Tuple

from src.analyzer.checkers import CheckerFinding
from src.analyzer.parser import (
    ParseResult,
    compute_cyclomatic_complexity,
    count_function_lines,
    measure_max_nesting,
)
from src.analyzer.rules import get_rules_for_language

MAX_LINE_LENGTH = 120
MAX_FUNCTION_LINES = 60
HIGH_COMPLEXITY_THRESHOLD = 10
DUPLICATE_BLOCK_MIN_LINES = 6


class StyleChecker:
    """Enforces style conventions and detects style issues."""

    CATEGORY = "style"

    def check(self, parsed: ParseResult, filename: str) -> List[CheckerFinding]:
        findings: List[CheckerFinding] = []
        content = parsed.raw_content
        language = parsed.language
        lines = content.splitlines()

        # Rule-based checks
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

        # Line length check
        findings.extend(self._check_line_length(lines))

        # Function length check
        findings.extend(self._check_function_length(parsed, lines))

        # Cyclomatic complexity check
        findings.extend(self._check_complexity(parsed, lines))

        # Duplicate code detection
        findings.extend(self._check_duplicate_blocks(lines))

        # Language-specific naming convention checks
        if language == "python":
            findings.extend(self._check_python_naming(parsed, lines))
        elif language in ("javascript", "typescript"):
            findings.extend(self._check_js_naming(parsed, lines))

        return findings

    def _check_line_length(self, lines: List[str]) -> List[CheckerFinding]:
        findings: List[CheckerFinding] = []
        for i, line in enumerate(lines, start=1):
            if len(line) > MAX_LINE_LENGTH:
                findings.append(
                    CheckerFinding(
                        category=self.CATEGORY,
                        severity="suggestion",
                        line_number=i,
                        end_line=i,
                        message=f"Line too long: {len(line)} characters (max {MAX_LINE_LENGTH})",
                        code_snippet=line[:100] + "..." if len(line) > 100 else line,
                        suggestion=f"Break line to keep under {MAX_LINE_LENGTH} characters.",
                        rule_id="STY-LEN001",
                    )
                )
        return findings

    def _check_function_length(self, parsed: ParseResult, lines: List[str]) -> List[CheckerFinding]:
        findings: List[CheckerFinding] = []
        for func in parsed.functions:
            length = count_function_lines(func)
            if length > MAX_FUNCTION_LINES:
                snippet = lines[func.start_line - 1].strip() if 0 < func.start_line <= len(lines) else ""
                findings.append(
                    CheckerFinding(
                        category=self.CATEGORY,
                        severity="warning",
                        line_number=func.start_line,
                        end_line=func.end_line,
                        message=f"Function `{func.name}` is {length} lines long (max recommended {MAX_FUNCTION_LINES})",
                        code_snippet=snippet,
                        suggestion="Extract logic into smaller, focused helper functions.",
                        rule_id="STY-LEN002",
                    )
                )
        return findings

    def _check_complexity(self, parsed: ParseResult, lines: List[str]) -> List[CheckerFinding]:
        findings: List[CheckerFinding] = []
        for func in parsed.functions:
            if not func.body:
                continue
            complexity = compute_cyclomatic_complexity(func.body, parsed.language)
            if complexity >= HIGH_COMPLEXITY_THRESHOLD:
                snippet = lines[func.start_line - 1].strip() if 0 < func.start_line <= len(lines) else ""
                findings.append(
                    CheckerFinding(
                        category=self.CATEGORY,
                        severity="warning",
                        line_number=func.start_line,
                        end_line=func.end_line,
                        message=f"High cyclomatic complexity ({complexity}) in `{func.name}` — hard to test",
                        code_snippet=snippet,
                        suggestion="Refactor into smaller functions with single responsibilities.",
                        rule_id="STY-CC001",
                    )
                )
        return findings

    def _check_duplicate_blocks(self, lines: List[str]) -> List[CheckerFinding]:
        findings: List[CheckerFinding] = []
        non_empty = [l.strip() for l in lines if l.strip()]
        n = len(non_empty)
        seen: dict[tuple, int] = {}

        for i in range(n - DUPLICATE_BLOCK_MIN_LINES + 1):
            block = tuple(non_empty[i : i + DUPLICATE_BLOCK_MIN_LINES])
            if block in seen:
                # Find the actual line number of this duplicate
                line_num = i + 1
                findings.append(
                    CheckerFinding(
                        category=self.CATEGORY,
                        severity="suggestion",
                        line_number=line_num,
                        end_line=line_num + DUPLICATE_BLOCK_MIN_LINES,
                        message=f"Duplicate code block detected ({DUPLICATE_BLOCK_MIN_LINES}+ lines)",
                        code_snippet=non_empty[i],
                        suggestion="Extract the repeated block into a shared function.",
                        rule_id="STY-DUP001",
                    )
                )
            else:
                seen[block] = i
        return findings

    def _check_python_naming(self, parsed: ParseResult, lines: List[str]) -> List[CheckerFinding]:
        findings: List[CheckerFinding] = []
        if not parsed.ast_tree:
            return findings

        snake_case = re.compile(r"^[a-z_][a-z0-9_]*$")
        pascal_case = re.compile(r"^[A-Z][a-zA-Z0-9]*$")
        screaming_snake = re.compile(r"^[A-Z][A-Z0-9_]*$")

        class NamingVisitor(ast.NodeVisitor):
            def __init__(self) -> None:
                self.findings: List[CheckerFinding] = []

            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                name = node.name
                if not (snake_case.match(name) or name.startswith("_")):
                    line = node.lineno
                    snippet = lines[line - 1].strip() if 0 < line <= len(lines) else ""
                    self.findings.append(
                        CheckerFinding(
                            category="style",
                            severity="suggestion",
                            line_number=line,
                            end_line=line,
                            message=f"Function `{name}` should be snake_case",
                            code_snippet=snippet,
                            suggestion=f"Rename to `{_to_snake_case(name)}`.",
                            rule_id="PY-NAM001",
                        )
                    )
                self.generic_visit(node)

            visit_AsyncFunctionDef = visit_FunctionDef

            def visit_ClassDef(self, node: ast.ClassDef) -> None:
                name = node.name
                if not pascal_case.match(name):
                    line = node.lineno
                    snippet = lines[line - 1].strip() if 0 < line <= len(lines) else ""
                    self.findings.append(
                        CheckerFinding(
                            category="style",
                            severity="suggestion",
                            line_number=line,
                            end_line=line,
                            message=f"Class `{name}` should be PascalCase",
                            code_snippet=snippet,
                            suggestion="Rename class to PascalCase.",
                            rule_id="PY-NAM002",
                        )
                    )
                self.generic_visit(node)

        visitor = NamingVisitor()
        visitor.visit(parsed.ast_tree)
        return visitor.findings

    def _check_js_naming(self, parsed: ParseResult, lines: List[str]) -> List[CheckerFinding]:
        findings: List[CheckerFinding] = []
        # Check for snake_case function names (should be camelCase in JS/TS)
        snake_func = re.compile(r"(?:function|const|let|var)\s+([a-z][a-z]+_[a-z_]+)\s*[=(]")
        content = "\n".join(lines)
        for match in snake_func.finditer(content):
            name = match.group(1)
            line_num = content[: match.start()].count("\n") + 1
            snippet = lines[line_num - 1].strip() if 0 < line_num <= len(lines) else ""
            findings.append(
                CheckerFinding(
                    category=self.CATEGORY,
                    severity="suggestion",
                    line_number=line_num,
                    end_line=line_num,
                    message=f"Function `{name}` uses snake_case — JavaScript convention is camelCase",
                    code_snippet=snippet,
                    suggestion=f"Rename to `{_to_camel_case(name)}`.",
                    rule_id="JS-NAM001",
                )
            )
        return findings


def _to_snake_case(name: str) -> str:
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def _to_camel_case(name: str) -> str:
    components = name.split("_")
    return components[0] + "".join(x.title() for x in components[1:])
