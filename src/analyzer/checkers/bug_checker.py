"""Bug detection checker — null pointers, type errors, infinite loops, unhandled exceptions."""

from __future__ import annotations

import ast
import re
from typing import List, Optional

from src.analyzer.checkers import CheckerFinding
from src.analyzer.parser import ParseResult, compute_cyclomatic_complexity
from src.analyzer.rules import get_rules_for_language


class BugChecker:
    """Detects common bugs across multiple languages."""

    CATEGORY = "bugs"

    def check(self, parsed: ParseResult, filename: str) -> List[CheckerFinding]:
        findings: List[CheckerFinding] = []
        language = parsed.language
        content = parsed.raw_content
        lines = content.splitlines()

        # Rule-based regex checks
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

        # AST-based Python analysis
        if language == "python" and parsed.ast_tree:
            findings.extend(self._python_ast_checks(parsed, lines))

        # Generic infinite loop detection
        findings.extend(self._check_infinite_loops(content, language, lines))

        # Generic off-by-one detection
        findings.extend(self._check_off_by_one(content, language, lines))

        return findings

    def _python_ast_checks(self, parsed: ParseResult, lines: List[str]) -> List[CheckerFinding]:
        findings: List[CheckerFinding] = []
        tree = parsed.ast_tree

        class BugVisitor(ast.NodeVisitor):
            def __init__(self) -> None:
                self.findings: List[CheckerFinding] = []

            def visit_Attribute(self, node: ast.Attribute) -> None:
                # Detect attribute access on potentially None value
                if isinstance(node.ctx, ast.Load):
                    if isinstance(node.value, ast.Call):
                        # method().attribute without None check
                        line = node.lineno
                        snippet = lines[line - 1].strip() if 0 < line <= len(lines) else ""
                        # Only flag if it looks like it could be None
                        if hasattr(node.value, 'func') and isinstance(node.value.func, ast.Attribute):
                            func_name = node.value.func.attr.lower()
                            if any(k in func_name for k in ("get", "find", "first", "fetch", "load")):
                                self.findings.append(
                                    CheckerFinding(
                                        category="bugs",
                                        severity="warning",
                                        line_number=line,
                                        end_line=line,
                                        message=f"Method `{func_name}()` may return None — accessing `.{node.attr}` without None check",
                                        code_snippet=snippet,
                                        suggestion="Add a None check before accessing attributes.",
                                        rule_id="PY-BUG-AST001",
                                    )
                                )
                self.generic_visit(node)

            def visit_For(self, node: ast.For) -> None:
                # Check for index access that might be off-by-one
                for child in ast.walk(node):
                    if isinstance(child, ast.Subscript):
                        if isinstance(child.slice, ast.BinOp):
                            if isinstance(child.slice.op, ast.Add):
                                line = child.lineno
                                snippet = lines[line - 1].strip() if 0 < line <= len(lines) else ""
                                self.findings.append(
                                    CheckerFinding(
                                        category="bugs",
                                        severity="suggestion",
                                        line_number=line,
                                        end_line=line,
                                        message="Potential off-by-one: index with +offset inside loop",
                                        code_snippet=snippet,
                                        suggestion="Verify loop bounds to prevent IndexError.",
                                        rule_id="PY-BUG-AST002",
                                    )
                                )
                self.generic_visit(node)

            def visit_Try(self, node: ast.Try) -> None:
                for handler in node.handlers:
                    # Detect empty except bodies
                    if len(handler.body) == 1 and isinstance(handler.body[0], ast.Pass):
                        line = handler.lineno
                        snippet = lines[line - 1].strip() if 0 < line <= len(lines) else ""
                        self.findings.append(
                            CheckerFinding(
                                category="bugs",
                                severity="critical",
                                line_number=line,
                                end_line=line,
                                message="Exception silently swallowed with `pass` — bugs will be hidden",
                                code_snippet=snippet,
                                suggestion="Log the exception or re-raise it.",
                                rule_id="PY-BUG-AST003",
                            )
                        )
                self.generic_visit(node)

            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                self._check_function(node)
                self.generic_visit(node)

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
                self._check_function(node)
                self.generic_visit(node)

            def _check_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
                # Check for mutable default arguments
                for default in node.args.defaults + node.args.kw_defaults:
                    if default is None:
                        continue
                    if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                        line = default.lineno
                        snippet = lines[line - 1].strip() if 0 < line <= len(lines) else ""
                        self.findings.append(
                            CheckerFinding(
                                category="bugs",
                                severity="critical",
                                line_number=line,
                                end_line=line,
                                message=f"Mutable default argument in `{node.name}()` — shared across all calls",
                                code_snippet=snippet,
                                suggestion="Use `None` as default and initialize in the function body.",
                                rule_id="PY-BUG-AST004",
                            )
                        )

        visitor = BugVisitor()
        visitor.visit(tree)
        return visitor.findings

    def _check_infinite_loops(self, content: str, language: str, lines: List[str]) -> List[CheckerFinding]:
        findings: List[CheckerFinding] = []
        patterns: dict[str, str] = {
            "python": r"while\s+True\s*:",
            "javascript": r"while\s*\(\s*true\s*\)",
            "typescript": r"while\s*\(\s*true\s*\)",
            "java": r"while\s*\(\s*true\s*\)",
            "go": r"for\s*\{",
            "rust": r"loop\s*\{",
            "ruby": r"while\s+true\b|loop\s+do\b",
        }
        pat = patterns.get(language)
        if not pat:
            return findings

        for match in re.finditer(pat, content, re.IGNORECASE):
            line_num = content[: match.start()].count("\n") + 1
            # Check if there's a break/return within reasonable distance
            surrounding = content[match.start() : match.start() + 500]
            if not re.search(r"\bbreak\b|\breturn\b|\bexit\b|\bpanic\b", surrounding):
                snippet = lines[line_num - 1].strip() if 0 < line_num <= len(lines) else ""
                findings.append(
                    CheckerFinding(
                        category="bugs",
                        severity="warning",
                        line_number=line_num,
                        end_line=line_num,
                        message="Potential infinite loop — no visible break/return in near scope",
                        code_snippet=snippet,
                        suggestion="Ensure there is a reachable exit condition.",
                        rule_id="BUG-INF001",
                    )
                )
        return findings

    def _check_off_by_one(self, content: str, language: str, lines: List[str]) -> List[CheckerFinding]:
        findings: List[CheckerFinding] = []
        # Generic pattern: array access with length (common off-by-one)
        pattern = re.compile(r"\[[\w.]+\.length\]|\[len\(\w+\)\]|\[[\w]+\.size\(\)\]", re.MULTILINE)
        for match in pattern.finditer(content):
            line_num = content[: match.start()].count("\n") + 1
            snippet = lines[line_num - 1].strip() if 0 < line_num <= len(lines) else ""
            findings.append(
                CheckerFinding(
                    category="bugs",
                    severity="critical",
                    line_number=line_num,
                    end_line=line_num,
                    message="Off-by-one error: indexing with `.length` / `len()` will go out of bounds",
                    code_snippet=snippet,
                    suggestion="Use `length - 1` to access the last element.",
                    rule_id="BUG-OBO001",
                )
            )
        return findings
