"""Performance checker — memory leaks, N+1 queries, redundant loops, unbounded collections."""

from __future__ import annotations

import ast
import re
from typing import List

from src.analyzer.checkers import CheckerFinding
from src.analyzer.parser import ParseResult
from src.analyzer.rules import get_rules_for_language

# Patterns for N+1 query detection across languages
N_PLUS_ONE_PATTERNS: list[tuple[str, list[str]]] = [
    (
        r"for\s+\w+\s+in\s+\w+[^:]*:\s*\n(?:\s+[^\n]*\n)*?\s+.*\.(filter|get|find|query|execute|select)\s*\(",
        ["python"],
    ),
    (
        r"(?:forEach|for|map)\s*\([^)]*\)\s*\{[^}]*(?:\.find|\.filter|\.get|db\.|query|execute)\s*\(",
        ["javascript", "typescript"],
    ),
    (
        r"for\s+\w+\s*,?\s*\w*\s*:?=\s*range[^{]+\{[^}]*(?:db\.|\.Query|\.Find|\.Exec)\s*\(",
        ["go"],
    ),
]

MEMORY_LEAK_PATTERNS: list[tuple[str, str, str, str]] = [
    (
        r"(?:open|socket|connect)\s*\([^)]+\)(?!\s*with|\s*as\s|\s*\.close)",
        "Resource opened without guaranteed closure",
        "PERF-MEM001",
        "Use a context manager (`with` statement) to ensure the resource is closed.",
    ),
    (
        r"setInterval\s*\([^)]+\)(?![^;]*clearInterval)",
        "setInterval without clearInterval — potential memory leak",
        "PERF-MEM002",
        "Store the interval ID and call clearInterval() when the component unmounts.",
    ),
    (
        r"addEventListener\s*\([^)]+\)(?![^;]*removeEventListener)",
        "Event listener added without removal — potential memory leak",
        "PERF-MEM003",
        "Remove event listeners when they are no longer needed.",
    ),
]

REDUNDANT_LOOP_PATTERNS: list[tuple[str, str, str, str]] = [
    (
        r"(?:for|while)\s*[^{:]+[:{][^}]*(?:for|while)\s*[^{:]+[:{][^}]*(?:for|while)",
        "Triple-nested loop detected — O(n³) time complexity",
        "PERF-LOOP001",
        "Refactor to reduce nesting; consider hash maps or sorting to avoid O(n³).",
    ),
    (
        r"\bsorted\s*\([^)]+\)\s*\[(?:0|-1)\]",
        "Sorting just to get min/max — use min()/max() instead",
        "PERF-LOOP002",
        "Use `min()` or `max()` which are O(n) instead of sort O(n log n).",
    ),
    (
        r"\.count\(\)\s*>\s*0|\.count\(\)\s*!=\s*0",
        "Using .count() > 0 to check existence — use .exists() instead",
        "PERF-LOOP003",
        "Use `.exists()` which stops at the first match, not `.count() > 0` which counts all.",
    ),
]

UNBOUNDED_COLLECTION_PATTERNS: list[tuple[str, str, str, str]] = [
    (
        r"while\s+True[^:]*:\s*\n(?:\s+[^\n]*\n)*?\s+\w+\.(append|add|update|push)\s*\(",
        "Unbounded collection grows inside infinite loop",
        "PERF-UNB001",
        "Add a size limit or use a bounded data structure like deque(maxlen=N).",
    ),
    (
        r"(\w+)\s*=\s*\[\]\s*\n(?:[^\n]*\n)*?for\s+\w+[^\n]*:\s*\n\s+\1\.(append|extend)\s*\(",
        "List growing in loop without size bound",
        "PERF-UNB002",
        "Consider using a generator or limit the collection size.",
    ),
]


class PerformanceChecker:
    """Detects performance anti-patterns in source code."""

    CATEGORY = "performance"

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

        # N+1 query detection
        findings.extend(self._check_n_plus_one(content, language, lines))

        # Memory leak detection
        findings.extend(self._check_memory_leaks(content, language, lines))

        # Redundant loop patterns
        findings.extend(self._check_redundant_loops(content, lines))

        # Unbounded collection detection
        findings.extend(self._check_unbounded_collections(content, lines))

        # Python-specific AST performance checks
        if language == "python" and parsed.ast_tree:
            findings.extend(self._python_perf_ast(parsed, lines))

        return findings

    def _check_n_plus_one(self, content: str, language: str, lines: List[str]) -> List[CheckerFinding]:
        findings: List[CheckerFinding] = []
        for pattern, langs in N_PLUS_ONE_PATTERNS:
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
                        message="N+1 query pattern: database query inside a loop",
                        code_snippet=snippet,
                        suggestion="Use eager loading, batch queries, or prefetch data before the loop.",
                        rule_id="PERF-N1001",
                    )
                )
        return findings

    def _check_memory_leaks(self, content: str, language: str, lines: List[str]) -> List[CheckerFinding]:
        findings: List[CheckerFinding] = []
        for pattern, message, rule_id, suggestion in MEMORY_LEAK_PATTERNS:
            for match in re.finditer(pattern, content, re.MULTILINE):
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
                        suggestion=suggestion,
                        rule_id=rule_id,
                    )
                )
        return findings

    def _check_redundant_loops(self, content: str, lines: List[str]) -> List[CheckerFinding]:
        findings: List[CheckerFinding] = []
        for pattern, message, rule_id, suggestion in REDUNDANT_LOOP_PATTERNS:
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
                        suggestion=suggestion,
                        rule_id=rule_id,
                    )
                )
        return findings

    def _check_unbounded_collections(self, content: str, lines: List[str]) -> List[CheckerFinding]:
        findings: List[CheckerFinding] = []
        for pattern, message, rule_id, suggestion in UNBOUNDED_COLLECTION_PATTERNS:
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
                        suggestion=suggestion,
                        rule_id=rule_id,
                    )
                )
        return findings

    def _python_perf_ast(self, parsed: ParseResult, lines: List[str]) -> List[CheckerFinding]:
        findings: List[CheckerFinding] = []
        tree = parsed.ast_tree

        class PerfVisitor(ast.NodeVisitor):
            def __init__(self) -> None:
                self.findings: List[CheckerFinding] = []

            def visit_For(self, node: ast.For) -> None:
                # Detect string concatenation in loops
                for child in ast.walk(node):
                    if isinstance(child, ast.AugAssign):
                        if isinstance(child.op, ast.Add):
                            if isinstance(child.value, ast.Constant) and isinstance(child.value.value, str):
                                line = child.lineno
                                snippet = lines[line - 1].strip() if 0 < line <= len(lines) else ""
                                self.findings.append(
                                    CheckerFinding(
                                        category="performance",
                                        severity="warning",
                                        line_number=line,
                                        end_line=line,
                                        message="String concatenation with `+=` in loop is O(n²)",
                                        code_snippet=snippet,
                                        suggestion="Use a list and `''.join()` after the loop.",
                                        rule_id="PY-PERF-AST001",
                                    )
                                )
                self.generic_visit(node)

            def visit_ListComp(self, node: ast.ListComp) -> None:
                # Check if list comp result is passed to sum/any/all/min/max
                line = node.lineno
                snippet = lines[line - 1].strip() if 0 < line <= len(lines) else ""
                self.findings.append(
                    CheckerFinding(
                        category="performance",
                        severity="suggestion",
                        line_number=line,
                        end_line=line,
                        message="List comprehension inside aggregate function — use generator expression",
                        code_snippet=snippet,
                        suggestion="Remove `[]` to use a generator: `sum(x for x in ...)`.",
                        rule_id="PY-PERF-AST002",
                    )
                )
                self.generic_visit(node)

        # Only check ListComps that are direct arguments to aggregate functions
        class AggregateVisitor(ast.NodeVisitor):
            def __init__(self) -> None:
                self.findings: List[CheckerFinding] = []

            def visit_Call(self, node: ast.Call) -> None:
                aggregate_funcs = {"sum", "any", "all", "min", "max", "sorted", "list", "set", "tuple"}
                if isinstance(node.func, ast.Name) and node.func.id in aggregate_funcs:
                    for arg in node.args:
                        if isinstance(arg, ast.ListComp):
                            line = arg.lineno
                            snippet = lines[line - 1].strip() if 0 < line <= len(lines) else ""
                            self.findings.append(
                                CheckerFinding(
                                    category="performance",
                                    severity="suggestion",
                                    line_number=line,
                                    end_line=line,
                                    message=f"List comprehension inside `{node.func.id}()` — use generator expression",
                                    code_snippet=snippet,
                                    suggestion="Remove `[]` to use a generator expression.",
                                    rule_id="PY-PERF-AST003",
                                )
                            )
                self.generic_visit(node)

        v = AggregateVisitor()
        v.visit(tree)
        return v.findings
