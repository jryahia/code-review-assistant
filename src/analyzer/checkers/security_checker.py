"""Security checker — SQL injection, XSS, hardcoded secrets, command injection, eval."""

from __future__ import annotations

import ast
import re
from typing import List

from src.analyzer.checkers import CheckerFinding
from src.analyzer.parser import ParseResult
from src.analyzer.rules import get_rules_for_language

# Patterns to detect hardcoded secrets across all languages
SECRET_PATTERNS: list[tuple[str, str, str]] = [
    (r'(?i)(password|passwd|pwd)\s*[=:]\s*["\'][^"\']{6,}["\']', "Hardcoded password", "SEC-HS001"),
    (r'(?i)(api_key|apikey|api-key)\s*[=:]\s*["\'][^"\']{8,}["\']', "Hardcoded API key", "SEC-HS002"),
    (r'(?i)(secret_key|secret|auth_secret)\s*[=:]\s*["\'][^"\']{8,}["\']', "Hardcoded secret key", "SEC-HS003"),
    (r'(?i)(access_token|refresh_token|bearer_token)\s*[=:]\s*["\'][^"\']{8,}["\']', "Hardcoded access token", "SEC-HS004"),
    (r'(?i)(aws_access_key_id|aws_secret)\s*[=:]\s*["\'][^"\']{8,}["\']', "Hardcoded AWS credentials", "SEC-HS005"),
    (r'sk-[a-zA-Z0-9]{32,}', "Hardcoded OpenAI API key", "SEC-HS006"),
    (r'sk-ant-[a-zA-Z0-9\-]{32,}', "Hardcoded Anthropic API key", "SEC-HS007"),
    (r'ghp_[a-zA-Z0-9]{36}', "Hardcoded GitHub personal access token", "SEC-HS008"),
    (r'-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----', "Private key embedded in source", "SEC-HS009"),
    (r'(?i)jdbc:[a-z]+://[^:]+:[^@]+@', "Database connection string with credentials", "SEC-HS010"),
]

SQL_INJECTION_PATTERNS: list[tuple[str, str]] = [
    (r'(?i)(execute|query|exec)\s*\(\s*f["\']', "SEC-SQL001"),
    (r'(?i)(execute|query|exec)\s*\(\s*["\'][^"\']*["\'\s]\s*\+\s*\w+', "SEC-SQL002"),
    (r'(?i)(execute|query|exec)\s*\(\s*["\'][^"\']*%s[^"\']*["\']\s*%\s*\w+', "SEC-SQL003"),
    (r'(?i)raw\(\s*f["\']', "SEC-SQL004"),
    (r'(?i)cursor\.execute\([^,)]*\+', "SEC-SQL005"),
    (r'(?i)(SELECT|INSERT|UPDATE|DELETE|DROP)\s+.*\+\s*\w+', "SEC-SQL006"),
]

XSS_PATTERNS: list[tuple[str, str]] = [
    (r'\.innerHTML\s*=\s*\w+', "SEC-XSS001"),
    (r'document\.write\s*\([^"\']+\)', "SEC-XSS002"),
    (r'\.outerHTML\s*=\s*\w+', "SEC-XSS003"),
    (r'insertAdjacentHTML\s*\([^,]+,\s*\w+', "SEC-XSS004"),
]

COMMAND_INJECTION_PATTERNS: list[tuple[str, str]] = [
    (r'subprocess\.(call|run|Popen|check_output)\s*\([^)]*shell\s*=\s*True', "SEC-CMD001"),
    (r'os\.system\s*\(', "SEC-CMD002"),
    (r'os\.popen\s*\(', "SEC-CMD003"),
    (r'Runtime\.exec\s*\(', "SEC-CMD004"),
    (r'exec\s*\(\s*["\'][a-z]', "SEC-CMD005"),
    (r'child_process\.(exec|spawn|execFile)\s*\([^,)]+\+', "SEC-CMD006"),
]


class SecurityChecker:
    """Detects security vulnerabilities in source code."""

    CATEGORY = "security"

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
                if not self._is_in_comment(snippet, language):
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

        # Universal secret detection
        findings.extend(self._check_secrets(content, lines))

        # SQL injection
        findings.extend(self._check_sql_injection(content, language, lines))

        # XSS (web languages)
        if language in ("javascript", "typescript"):
            findings.extend(self._check_xss(content, lines))

        # Command injection
        findings.extend(self._check_command_injection(content, language, lines))

        # Python-specific AST checks
        if language == "python" and parsed.ast_tree:
            findings.extend(self._python_security_ast(parsed, lines))

        return findings

    def _is_in_comment(self, line: str, language: str) -> bool:
        stripped = line.strip()
        if language in ("python", "ruby"):
            return stripped.startswith("#")
        return stripped.startswith("//") or stripped.startswith("*") or stripped.startswith("/*")

    def _check_secrets(self, content: str, lines: List[str]) -> List[CheckerFinding]:
        findings: List[CheckerFinding] = []
        for pattern, message, rule_id in SECRET_PATTERNS:
            for match in re.finditer(pattern, content, re.MULTILINE):
                line_num = content[: match.start()].count("\n") + 1
                raw_line = lines[line_num - 1] if 0 < line_num <= len(lines) else ""
                if self._is_test_or_example(raw_line):
                    continue
                # Redact the actual secret value in the snippet
                snippet = re.sub(r'["\'][^"\']{4,}["\']', '"[REDACTED]"', raw_line.strip())
                findings.append(
                    CheckerFinding(
                        category=self.CATEGORY,
                        severity="critical",
                        line_number=line_num,
                        end_line=line_num,
                        message=message,
                        code_snippet=snippet,
                        suggestion="Use environment variables or a secrets manager. Never commit credentials.",
                        rule_id=rule_id,
                    )
                )
        return findings

    def _is_test_or_example(self, line: str) -> bool:
        lower = line.lower()
        return any(k in lower for k in ("example", "placeholder", "your_", "changeme", "xxx", "abc123", "dummy", "test"))

    def _check_sql_injection(self, content: str, language: str, lines: List[str]) -> List[CheckerFinding]:
        findings: List[CheckerFinding] = []
        for pattern, rule_id in SQL_INJECTION_PATTERNS:
            for match in re.finditer(pattern, content, re.MULTILINE):
                line_num = content[: match.start()].count("\n") + 1
                snippet = lines[line_num - 1].strip() if 0 < line_num <= len(lines) else ""
                findings.append(
                    CheckerFinding(
                        category=self.CATEGORY,
                        severity="critical",
                        line_number=line_num,
                        end_line=line_num,
                        message="SQL injection risk: query built with string concatenation or f-string",
                        code_snippet=snippet,
                        suggestion="Use parameterized queries or ORM methods.",
                        rule_id=rule_id,
                    )
                )
        return findings

    def _check_xss(self, content: str, lines: List[str]) -> List[CheckerFinding]:
        findings: List[CheckerFinding] = []
        for pattern, rule_id in XSS_PATTERNS:
            for match in re.finditer(pattern, content, re.MULTILINE):
                line_num = content[: match.start()].count("\n") + 1
                snippet = lines[line_num - 1].strip() if 0 < line_num <= len(lines) else ""
                findings.append(
                    CheckerFinding(
                        category=self.CATEGORY,
                        severity="critical",
                        line_number=line_num,
                        end_line=line_num,
                        message="XSS vulnerability: unsanitized content assigned to DOM",
                        code_snippet=snippet,
                        suggestion="Use textContent for plain text or sanitize with DOMPurify.",
                        rule_id=rule_id,
                    )
                )
        return findings

    def _check_command_injection(self, content: str, language: str, lines: List[str]) -> List[CheckerFinding]:
        findings: List[CheckerFinding] = []
        for pattern, rule_id in COMMAND_INJECTION_PATTERNS:
            for match in re.finditer(pattern, content, re.MULTILINE):
                line_num = content[: match.start()].count("\n") + 1
                snippet = lines[line_num - 1].strip() if 0 < line_num <= len(lines) else ""
                if not self._is_in_comment(snippet, language):
                    findings.append(
                        CheckerFinding(
                            category=self.CATEGORY,
                            severity="critical",
                            line_number=line_num,
                            end_line=line_num,
                            message="Command injection risk: shell command executed with user-controlled input",
                            code_snippet=snippet,
                            suggestion="Avoid shell=True; pass arguments as a list and validate all input.",
                            rule_id=rule_id,
                        )
                    )
        return findings

    def _python_security_ast(self, parsed: ParseResult, lines: List[str]) -> List[CheckerFinding]:
        findings: List[CheckerFinding] = []
        tree = parsed.ast_tree

        class SecurityVisitor(ast.NodeVisitor):
            def __init__(self) -> None:
                self.findings: List[CheckerFinding] = []

            def visit_Call(self, node: ast.Call) -> None:
                func_name = ""
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    func_name = node.func.attr

                if func_name in ("eval", "exec", "compile"):
                    line = node.lineno
                    snippet = lines[line - 1].strip() if 0 < line <= len(lines) else ""
                    self.findings.append(
                        CheckerFinding(
                            category="security",
                            severity="critical",
                            line_number=line,
                            end_line=line,
                            message=f"`{func_name}()` executes arbitrary code",
                            code_snippet=snippet,
                            suggestion=f"Remove `{func_name}()`. Use safe alternatives.",
                            rule_id="PY-SEC-AST001",
                        )
                    )

                # Check for format string in database call
                if func_name in ("execute", "raw", "query"):
                    if node.args and isinstance(node.args[0], ast.JoinedStr):
                        line = node.lineno
                        snippet = lines[line - 1].strip() if 0 < line <= len(lines) else ""
                        self.findings.append(
                            CheckerFinding(
                                category="security",
                                severity="critical",
                                line_number=line,
                                end_line=line,
                                message="SQL injection: f-string used in database query",
                                code_snippet=snippet,
                                suggestion="Use parameterized queries.",
                                rule_id="PY-SEC-AST002",
                            )
                        )

                self.generic_visit(node)

        visitor = SecurityVisitor()
        visitor.visit(tree)
        return visitor.findings
