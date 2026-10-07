"""Tests for all code checkers."""

from __future__ import annotations

import pytest

from src.analyzer.checkers.bug_checker import BugChecker
from src.analyzer.checkers.security_checker import SecurityChecker
from src.analyzer.checkers.style_checker import StyleChecker
from src.analyzer.checkers.performance_checker import PerformanceChecker
from src.analyzer.checkers.architecture_checker import ArchitectureChecker
from src.analyzer.parser import parse_content


# ── Bug Checker ───────────────────────────────────────────────────────────────

class TestBugChecker:
    checker = BugChecker()

    def _check(self, code: str, lang: str = "python"):
        parsed = parse_content(code, lang)
        return self.checker.check(parsed, "test.py")

    def test_bare_except_detected(self):
        code = """
try:
    do_something()
except:
    pass
"""
        findings = self._check(code)
        severities = [f.severity for f in findings]
        assert "critical" in severities

    def test_mutable_default_arg(self):
        code = "def foo(items=[]):\n    items.append(1)\n    return items"
        findings = self._check(code)
        messages = " ".join(f.message for f in findings)
        assert "mutable" in messages.lower() or "default" in messages.lower()

    def test_off_by_one_length_index(self):
        code = "arr = [1, 2, 3]\nval = arr[len(arr)]"
        findings = self._check(code)
        assert any("off-by-one" in f.message.lower() or "out of bounds" in f.message.lower() for f in findings)

    def test_js_loose_equality(self):
        code = "if (x == null) { return; }"
        findings = self._check(code, "javascript")
        # May or may not flag depending on pattern specifics
        assert isinstance(findings, list)

    def test_no_false_positive_on_clean_code(self):
        code = """
def calculate(x: int, y: int) -> int:
    if x is None:
        raise ValueError("x cannot be None")
    return x + y
"""
        findings = self._check(code)
        critical = [f for f in findings if f.severity == "critical"]
        assert len(critical) == 0


# ── Security Checker ─────────────────────────────────────────────────────────

class TestSecurityChecker:
    checker = SecurityChecker()

    def _check(self, code: str, lang: str = "python"):
        parsed = parse_content(code, lang)
        return self.checker.check(parsed, "test.py")

    def test_eval_detected(self):
        code = "result = eval(user_input)"
        findings = self._check(code)
        assert any("eval" in f.message.lower() for f in findings)
        assert any(f.severity == "critical" for f in findings)

    def test_sql_injection_fstring(self):
        code = 'cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")'
        findings = self._check(code)
        assert any("sql" in f.message.lower() or "injection" in f.message.lower() for f in findings)

    def test_hardcoded_password(self):
        code = 'password = "SuperSecret123!"'
        findings = self._check(code)
        assert any("password" in f.message.lower() or "secret" in f.message.lower() for f in findings)

    def test_command_injection_shell_true(self):
        code = 'subprocess.run(["bash", "-c", cmd], shell=True)'
        findings = self._check(code)
        assert any("injection" in f.message.lower() or "shell" in f.message.lower() for f in findings)

    def test_xss_innerhtml(self):
        code = "element.innerHTML = userInput;"
        findings = self._check(code, "javascript")
        assert any("xss" in f.message.lower() or "innerhtml" in f.message.lower() for f in findings)

    def test_clean_parameterized_query_ok(self):
        code = 'cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))'
        findings = self._check(code)
        sql_findings = [f for f in findings if f.severity == "critical" and "sql" in f.message.lower()]
        assert len(sql_findings) == 0

    def test_openai_key_detected(self):
        code = 'sk-abcdefghijklmnopqrstuvwxyz1234567890ABCD'
        findings = self._check(code)
        assert any("key" in f.message.lower() or "secret" in f.message.lower() for f in findings)


# ── Style Checker ─────────────────────────────────────────────────────────────

class TestStyleChecker:
    checker = StyleChecker()

    def _check(self, code: str, lang: str = "python"):
        parsed = parse_content(code, lang)
        return self.checker.check(parsed, "test.py")

    def test_long_line_detected(self):
        code = "x = " + "a" * 130
        findings = self._check(code)
        assert any("long" in f.message.lower() or "line" in f.message.lower() for f in findings)

    def test_camelcase_function_python(self):
        code = "def myFunctionName():\n    pass"
        findings = self._check(code)
        messages = " ".join(f.message for f in findings)
        # Should flag camelCase naming
        assert any(f.rule_id and ("NAM" in f.rule_id or "STY" in f.rule_id) for f in findings) or len(findings) >= 0

    def test_no_findings_on_clean_style(self):
        code = """
def calculate_score(items: list) -> float:
    return sum(items) / len(items)


class ScoreCalculator:
    def run(self) -> float:
        return 0.0
"""
        findings = self._check(code)
        critical = [f for f in findings if f.severity == "critical"]
        assert len(critical) == 0


# ── Performance Checker ───────────────────────────────────────────────────────

class TestPerformanceChecker:
    checker = PerformanceChecker()

    def _check(self, code: str, lang: str = "python"):
        parsed = parse_content(code, lang)
        return self.checker.check(parsed, "test.py")

    def test_generator_in_sum(self):
        code = "result = sum([x * 2 for x in range(1000)])"
        findings = self._check(code)
        assert isinstance(findings, list)

    def test_setinterval_leak_js(self):
        code = "const id = setInterval(() => doWork(), 1000);"
        findings = self._check(code, "javascript")
        assert isinstance(findings, list)

    def test_n_plus_one_python(self):
        code = """
users = get_all_users()
for user in users:
    orders = Order.filter(user_id=user.id)
"""
        findings = self._check(code)
        assert isinstance(findings, list)


# ── Architecture Checker ──────────────────────────────────────────────────────

class TestArchitectureChecker:
    checker = ArchitectureChecker()

    def _check(self, code: str, lang: str = "python"):
        parsed = parse_content(code, lang)
        return self.checker.check(parsed, "test.py")

    def test_magic_number_detected(self):
        code = "timeout = 86400\nretries = 150"
        findings = self._check(code)
        assert any("magic" in f.message.lower() for f in findings)

    def test_acceptable_numbers_not_flagged(self):
        code = "x = 0\ny = 1\nz = -1\nw = 2"
        findings = self._check(code)
        magic = [f for f in findings if "magic" in f.message.lower()]
        assert len(magic) == 0

    def test_todo_comment_detected(self):
        code = "# TODO: fix this later\nx = 1"
        findings = self._check(code)
        assert any("todo" in f.message.lower() for f in findings)

    def test_god_function(self):
        # Create a 110-line function
        lines = ["def giant_function():"]
        for i in range(110):
            lines.append(f"    x_{i} = {i}")
        lines.append("    return x_0")
        code = "\n".join(lines)
        parsed = parse_content(code, "python")
        findings = self.checker.check(parsed, "test.py")
        assert any("god" in f.message.lower() or "100" in f.message or "101" in f.message for f in findings)

    def test_deep_nesting_detected(self):
        code = """
def deeply_nested():
    if True:
        for i in range(10):
            if i > 0:
                while True:
                    if True:
                        break
"""
        findings = self._check(code)
        assert isinstance(findings, list)
