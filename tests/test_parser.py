"""Tests for the language detection and parsing module."""

from __future__ import annotations

import pytest

from src.analyzer.parser import (
    compute_cyclomatic_complexity,
    detect_language,
    is_supported,
    measure_max_nesting,
    parse_content,
    parse_patch,
)


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("main.py", "python"),
        ("app.js", "javascript"),
        ("app.jsx", "javascript"),
        ("component.ts", "typescript"),
        ("component.tsx", "typescript"),
        ("main.go", "go"),
        ("lib.rs", "rust"),
        ("Main.java", "java"),
        ("app.rb", "ruby"),
        ("Contract.sol", "solidity"),
        ("README.md", "markdown"),
        ("Makefile", "unknown"),
        ("image.png", "unknown"),
    ],
)
def test_detect_language(filename: str, expected: str) -> None:
    assert detect_language(filename) == expected


@pytest.mark.parametrize(
    "language,supported",
    [
        ("python", True),
        ("javascript", True),
        ("typescript", True),
        ("go", True),
        ("rust", True),
        ("java", True),
        ("ruby", True),
        ("solidity", True),
        ("markdown", False),
        ("unknown", False),
        ("json", False),
    ],
)
def test_is_supported(language: str, supported: bool) -> None:
    assert is_supported(language) == supported


def test_parse_python_basic() -> None:
    code = '''
def hello(name: str) -> str:
    return f"Hello, {name}"

class Greeter:
    def greet(self) -> None:
        pass
'''
    result = parse_content(code, "python")
    assert result.language == "python"
    assert result.ast_tree is not None
    assert result.parse_error is None
    func_names = [f.name for f in result.functions]
    assert "hello" in func_names
    assert "greet" in func_names
    assert "Greeter" in result.classes


def test_parse_python_syntax_error() -> None:
    code = "def broken(:\n    pass"
    result = parse_content(code, "python")
    assert result.parse_error is not None


def test_parse_javascript_basic() -> None:
    code = """
import React from 'react';

function MyComponent(props) {
    return <div>{props.children}</div>;
}

const arrowFunc = (x) => x * 2;
"""
    result = parse_content(code, "javascript")
    assert result.language == "javascript"
    assert "react" in result.imports


def test_parse_go_basic() -> None:
    code = """
package main

import (
    "fmt"
    "os"
)

func main() {
    fmt.Println("Hello")
}

func (s *Server) HandleRequest(w http.ResponseWriter, r *http.Request) {
    // ...
}
"""
    result = parse_content(code, "go")
    assert result.language == "go"
    func_names = [f.name for f in result.functions]
    assert "main" in func_names


def test_parse_patch_basic() -> None:
    patch = """@@ -10,6 +10,8 @@
 context line
+added line 1
+added line 2
-removed line
 another context
"""
    lines = parse_patch(patch)
    added = [l for l in lines if l.is_added]
    removed = [l for l in lines if l.is_removed]
    assert len(added) == 2
    assert len(removed) == 1


def test_cyclomatic_complexity_python() -> None:
    simple = "def foo():\n    return 1"
    complex_code = """
def foo(x):
    if x > 0:
        for i in range(x):
            if i % 2 == 0:
                pass
            elif i % 3 == 0:
                pass
        while x > 0:
            x -= 1
    return x
"""
    assert compute_cyclomatic_complexity(simple, "python") <= 2
    assert compute_cyclomatic_complexity(complex_code, "python") > 5


def test_measure_max_nesting() -> None:
    shallow = "def foo():\n    x = 1\n    return x"
    deep = "def foo():\n    if a:\n        for i in range(10):\n            if b:\n                while c:\n                    pass"
    assert measure_max_nesting(shallow) < 4
    assert measure_max_nesting(deep) >= 4
