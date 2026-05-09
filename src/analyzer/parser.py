"""Language detection and code parsing."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

EXTENSION_MAP: Dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".sol": "solidity",
    ".kt": "kotlin",
    ".swift": "swift",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".php": "php",
    ".scala": "scala",
    ".ex": "elixir",
    ".exs": "elixir",
    ".sh": "bash",
    ".bash": "bash",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".json": "json",
    ".md": "markdown",
    ".sql": "sql",
}

SUPPORTED_LANGUAGES = {
    "python", "javascript", "typescript", "go", "rust", "java", "ruby", "solidity"
}


@dataclass
class CodeLine:
    number: int
    content: str
    is_added: bool = False
    is_removed: bool = False


@dataclass
class ParsedFunction:
    name: str
    start_line: int
    end_line: int
    body: str
    params: List[str] = field(default_factory=list)
    decorators: List[str] = field(default_factory=list)


@dataclass
class ParseResult:
    language: str
    lines: List[CodeLine]
    raw_content: str
    functions: List[ParsedFunction] = field(default_factory=list)
    classes: List[str] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    ast_tree: Optional[Any] = None
    parse_error: Optional[str] = None

    def get_line(self, number: int) -> Optional[str]:
        for line in self.lines:
            if line.number == number:
                return line.content
        return None

    def get_context(self, line_number: int, context: int = 2) -> str:
        start = max(1, line_number - context)
        end = line_number + context
        result = []
        for line in self.lines:
            if start <= line.number <= end:
                result.append(f"{line.number:4d}: {line.content}")
        return "\n".join(result)


def detect_language(filename: str) -> str:
    """Detect programming language from file extension."""
    path = Path(filename)
    ext = path.suffix.lower()
    return EXTENSION_MAP.get(ext, "unknown")


def is_supported(language: str) -> bool:
    return language in SUPPORTED_LANGUAGES


def parse_patch(patch: str) -> List[CodeLine]:
    """Parse a unified diff patch into CodeLine objects."""
    lines: List[CodeLine] = []
    current_line = 0

    for raw_line in patch.splitlines():
        if raw_line.startswith("@@"):
            match = re.search(r"\+(\d+)", raw_line)
            if match:
                current_line = int(match.group(1)) - 1
            continue

        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            current_line += 1
            lines.append(CodeLine(number=current_line, content=raw_line[1:], is_added=True))
        elif raw_line.startswith("-") and not raw_line.startswith("---"):
            lines.append(CodeLine(number=current_line, content=raw_line[1:], is_removed=True))
        else:
            current_line += 1
            lines.append(CodeLine(number=current_line, content=raw_line.lstrip(" ")))

    return lines


def parse_content(content: str, language: str) -> ParseResult:
    """Parse source content for the given language."""
    raw_lines = content.splitlines()
    code_lines = [CodeLine(number=i + 1, content=ln) for i, ln in enumerate(raw_lines)]
    result = ParseResult(language=language, lines=code_lines, raw_content=content)

    if language == "python":
        _parse_python(content, result)
    elif language in ("javascript", "typescript"):
        _parse_js_ts(content, result)
    elif language == "java":
        _parse_java(content, result)
    elif language == "go":
        _parse_go(content, result)
    else:
        _parse_generic(content, result)

    return result


def _parse_python(content: str, result: ParseResult) -> None:
    """Parse Python using the built-in AST module."""
    try:
        tree = ast.parse(content)
        result.ast_tree = tree

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start = node.lineno
                end = node.end_lineno or start
                body_lines = content.splitlines()[start - 1 : end]
                params = [arg.arg for arg in node.args.args]
                decorators = [
                    ast.unparse(d) if hasattr(ast, "unparse") else d.__class__.__name__
                    for d in node.decorator_list
                ]
                result.functions.append(
                    ParsedFunction(
                        name=node.name,
                        start_line=start,
                        end_line=end,
                        body="\n".join(body_lines),
                        params=params,
                        decorators=decorators,
                    )
                )
            elif isinstance(node, ast.ClassDef):
                result.classes.append(node.name)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        result.imports.append(alias.name)
                else:
                    module = node.module or ""
                    for alias in node.names:
                        result.imports.append(f"{module}.{alias.name}")
    except SyntaxError as e:
        result.parse_error = str(e)
        _parse_generic(content, result)


def _parse_js_ts(content: str, result: ParseResult) -> None:
    """Parse JavaScript/TypeScript using regex."""
    func_pattern = re.compile(
        r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(|"
        r"(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>|"
        r"(\w+)\s*\([^)]*\)\s*\{",
        re.MULTILINE,
    )
    lines = content.splitlines()
    for match in func_pattern.finditer(content):
        name = match.group(1) or match.group(2) or match.group(3)
        if name and not name[0].isupper():
            start_line = content[: match.start()].count("\n") + 1
            result.functions.append(
                ParsedFunction(name=name, start_line=start_line, end_line=start_line, body="")
            )

    import_pattern = re.compile(r"import\s+.*?from\s+['\"]([^'\"]+)['\"]", re.MULTILINE)
    for m in import_pattern.finditer(content):
        result.imports.append(m.group(1))

    class_pattern = re.compile(r"class\s+(\w+)", re.MULTILINE)
    for m in class_pattern.finditer(content):
        result.classes.append(m.group(1))


def _parse_java(content: str, result: ParseResult) -> None:
    """Parse Java using regex."""
    method_pattern = re.compile(
        r"(?:public|private|protected|static|\s)+[\w<>\[\]]+\s+(\w+)\s*\([^)]*\)\s*(?:throws\s+\w+\s*)?\{",
        re.MULTILINE,
    )
    for match in method_pattern.finditer(content):
        name = match.group(1)
        start_line = content[: match.start()].count("\n") + 1
        result.functions.append(
            ParsedFunction(name=name, start_line=start_line, end_line=start_line, body="")
        )

    class_pattern = re.compile(r"(?:public\s+)?class\s+(\w+)", re.MULTILINE)
    for m in class_pattern.finditer(content):
        result.classes.append(m.group(1))

    import_pattern = re.compile(r"^import\s+([\w.]+)\s*;", re.MULTILINE)
    for m in import_pattern.finditer(content):
        result.imports.append(m.group(1))


def _parse_go(content: str, result: ParseResult) -> None:
    """Parse Go using regex."""
    func_pattern = re.compile(r"func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\s*\(", re.MULTILINE)
    for match in func_pattern.finditer(content):
        name = match.group(1)
        start_line = content[: match.start()].count("\n") + 1
        result.functions.append(
            ParsedFunction(name=name, start_line=start_line, end_line=start_line, body="")
        )

    import_pattern = re.compile(r'"([\w./]+)"', re.MULTILINE)
    for m in import_pattern.finditer(content):
        result.imports.append(m.group(1))

    struct_pattern = re.compile(r"type\s+(\w+)\s+struct", re.MULTILINE)
    for m in struct_pattern.finditer(content):
        result.classes.append(m.group(1))


def _parse_generic(content: str, result: ParseResult) -> None:
    """Generic parsing — extract imports and rough function signatures."""
    lines = content.splitlines()
    in_function = False
    func_start = 0
    func_name = ""
    brace_depth = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        if re.match(r"(def |function |func |fn |public |private |protected )", stripped):
            name_match = re.search(r"[\s(](\w+)\s*\(", stripped)
            if name_match:
                func_name = name_match.group(1)
                func_start = i + 1
                in_function = True
                brace_depth = stripped.count("{") - stripped.count("}")

        elif in_function:
            brace_depth += line.count("{") - line.count("}")
            if brace_depth <= 0:
                result.functions.append(
                    ParsedFunction(
                        name=func_name,
                        start_line=func_start,
                        end_line=i + 1,
                        body="\n".join(lines[func_start - 1 : i + 1]),
                    )
                )
                in_function = False


def compute_cyclomatic_complexity(content: str, language: str) -> int:
    """Estimate cyclomatic complexity from branch points."""
    branch_keywords: Dict[str, List[str]] = {
        "python": [r"\bif\b", r"\belif\b", r"\bfor\b", r"\bwhile\b", r"\band\b", r"\bor\b", r"\bexcept\b", r"\bcase\b"],
        "javascript": [r"\bif\b", r"\belse if\b", r"\bfor\b", r"\bwhile\b", r"&&", r"\|\|", r"\bcase\b", r"\bcatch\b"],
        "typescript": [r"\bif\b", r"\belse if\b", r"\bfor\b", r"\bwhile\b", r"&&", r"\|\|", r"\bcase\b", r"\bcatch\b"],
        "java": [r"\bif\b", r"\belse if\b", r"\bfor\b", r"\bwhile\b", r"&&", r"\|\|", r"\bcase\b", r"\bcatch\b"],
        "go": [r"\bif\b", r"\bfor\b", r"&&", r"\|\|", r"\bcase\b"],
        "rust": [r"\bif\b", r"\bfor\b", r"\bwhile\b", r"&&", r"\|\|", r"\bmatch\b"],
        "ruby": [r"\bif\b", r"\bunless\b", r"\bwhile\b", r"\buntil\b", r"\bfor\b", r"&&", r"\|\|", r"\bcase\b"],
        "solidity": [r"\bif\b", r"\bfor\b", r"\bwhile\b", r"&&", r"\|\|", r"\brequire\b"],
    }

    keywords = branch_keywords.get(language, branch_keywords["javascript"])
    count = 1
    for kw in keywords:
        count += len(re.findall(kw, content, re.IGNORECASE))
    return count


def measure_max_nesting(content: str) -> int:
    """Measure maximum indentation depth (proxy for nesting level)."""
    max_depth = 0
    for line in content.splitlines():
        if not line.strip():
            continue
        spaces = len(line) - len(line.lstrip())
        depth = spaces // 4
        max_depth = max(max_depth, depth)
    return max_depth


def count_function_lines(func: ParsedFunction) -> int:
    return func.end_line - func.start_line + 1
