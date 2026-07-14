"""Tests for the analysis engine."""

from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio

from src.analyzer.engine import AnalysisEngine


@pytest.mark.asyncio
async def test_engine_empty_files():
    engine = AnalysisEngine()
    result = await engine.analyze_files([])
    assert result.total_score == 100.0
    assert result.files_analyzed == 0
    assert result.total_findings == 0


@pytest.mark.asyncio
async def test_engine_single_python_file():
    files = [
        {
            "filename": "test_file.py",
            "status": "modified",
            "additions": 20,
            "deletions": 5,
            "patch": """@@ -1,5 +1,20 @@
+import os
+
+def process_data(items=None):
+    if items is None:
+        items = []
+    result = eval(user_input)
+    return result

+def clean_function(x: int) -> int:
+    return x * 2
""",
        }
    ]
    engine = AnalysisEngine(enabled_categories=["bugs", "security"])
    result = await engine.analyze_files(files)
    assert result.files_analyzed == 1
    assert result.total_findings > 0
    assert result.critical_count > 0
    assert result.total_score < 100.0


@pytest.mark.asyncio
async def test_engine_skips_removed_files():
    files = [
        {
            "filename": "deleted.py",
            "status": "removed",
            "additions": 0,
            "deletions": 50,
            "patch": None,
        }
    ]
    engine = AnalysisEngine()
    result = await engine.analyze_files(files)
    assert result.files_analyzed == 0
    assert result.files_skipped == 0  # removed files don't count as skipped


@pytest.mark.asyncio
async def test_engine_skips_unsupported_language():
    files = [
        {
            "filename": "styles.css",
            "status": "modified",
            "additions": 10,
            "deletions": 0,
            "patch": "@@ -1 +1 @@\n+.container { color: red; }",
        }
    ]
    engine = AnalysisEngine()
    result = await engine.analyze_files(files)
    assert result.files_analyzed == 0


@pytest.mark.asyncio
async def test_engine_respects_ignore_patterns():
    files = [
        {
            "filename": "test_something.py",
            "status": "modified",
            "additions": 5,
            "deletions": 0,
            "patch": "@@ -1 +5 @@\n+eval(user_input)\n+subprocess.call('ls', shell=True)",
        }
    ]
    engine = AnalysisEngine(ignore_patterns=[r"test_.*\.py"])
    result = await engine.analyze_files(files)
    assert result.files_analyzed == 0


@pytest.mark.asyncio
async def test_engine_respects_category_filter():
    files = [
        {
            "filename": "app.py",
            "status": "modified",
            "additions": 10,
            "deletions": 0,
            "patch": "@@ -1 +10 @@\n+eval(user_input)\n+password = 'hardcoded'\n+def myFunction():\n+    pass",
        }
    ]
    engine = AnalysisEngine(enabled_categories=["security"])
    result = await engine.analyze_files(files)
    categories = {f.category for fr in result.files for f in fr.findings}
    assert "security" in categories
    assert "style" not in categories


@pytest.mark.asyncio
async def test_engine_score_calculation():
    from src.analyzer.engine import _extract_content_from_patch
    patch = "@@ -1,3 +1,5 @@\n+eval(x)\n+os.system(cmd)\n+password = 'abc123'\n context\n-old"
    content = _extract_content_from_patch(patch)
    assert "eval" in content
    assert "password" in content


def test_extract_content_from_patch():
    from src.analyzer.engine import _extract_content_from_patch
    patch = """@@ -1,4 +1,6 @@
 context line
+added line 1
+added line 2
-removed line
 another context
"""
    content = _extract_content_from_patch(patch)
    assert "added line 1" in content
    assert "added line 2" in content
    assert "removed line" not in content


def test_deduplicate_findings():
    from src.analyzer.checkers import CheckerFinding
    from src.analyzer.engine import _deduplicate_findings

    findings = [
        CheckerFinding("bugs", "critical", 10, 10, "Same message", rule_id="R001"),
        CheckerFinding("bugs", "critical", 10, 10, "Same message", rule_id="R001"),
        CheckerFinding("security", "warning", 20, 20, "Different", rule_id="R002"),
    ]
    deduped = _deduplicate_findings(findings)
    assert len(deduped) == 2
