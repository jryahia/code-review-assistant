"""TypeScript-specific analysis rules."""

from __future__ import annotations

from src.analyzer.rules import Rule

RULES: list[Rule] = [
    # ── BUGS ──────────────────────────────────────────────────────────────────
    Rule(
        id="TS-BUG001",
        category="bugs",
        severity="critical",
        message="Non-null assertion `!` used — could throw at runtime if value is null",
        pattern=r"\w+!\.",
        suggestion="Add a proper null check instead of using non-null assertion.",
        languages=["typescript"],
    ),
    Rule(
        id="TS-BUG002",
        category="bugs",
        severity="warning",
        message="Using `any` type defeats TypeScript's type safety",
        pattern=r":\s*any\b|<any>|as\s+any\b",
        suggestion="Define a proper interface or use `unknown` with type guards.",
        languages=["typescript"],
    ),
    Rule(
        id="TS-BUG003",
        category="bugs",
        severity="warning",
        message="Type assertion `as Type` without runtime validation can hide bugs",
        pattern=r"\bas\s+[A-Z]\w+(?!\s+as\b)",
        suggestion="Validate the actual type at runtime with a type guard function.",
        languages=["typescript"],
    ),
    Rule(
        id="TS-BUG004",
        category="bugs",
        severity="warning",
        message="Optional chaining result not checked before use",
        pattern=r"\?\.\w+\s*\.\w+",
        suggestion="Check if the optional chain result is defined before chaining further.",
        languages=["typescript"],
    ),
    Rule(
        id="TS-BUG005",
        category="bugs",
        severity="critical",
        message="Unhandled Promise rejection",
        pattern=r"async\s+\w+[^{]*\{[^}]*await[^;]*\n(?!\s*(try|catch))",
        suggestion="Wrap await calls in try/catch or chain .catch().",
        languages=["typescript"],
    ),
    # ── SECURITY ──────────────────────────────────────────────────────────────
    Rule(
        id="TS-SEC001",
        category="security",
        severity="critical",
        message="`eval()` executes arbitrary code",
        pattern=r"\beval\s*\(",
        suggestion="Remove eval(). Use proper abstractions.",
        languages=["typescript"],
    ),
    Rule(
        id="TS-SEC002",
        category="security",
        severity="critical",
        message="`innerHTML` assignment may cause XSS",
        pattern=r"\.innerHTML\s*=",
        suggestion="Use textContent or sanitize with DOMPurify.",
        languages=["typescript"],
    ),
    Rule(
        id="TS-SEC003",
        category="security",
        severity="warning",
        message="Object spread with untrusted data may cause prototype pollution",
        pattern=r"\.\.\.\s*\w+Request|\.\.\.\s*req\.(body|query|params)",
        suggestion="Whitelist or validate properties before spreading untrusted data.",
        languages=["typescript"],
    ),
    # ── STYLE ─────────────────────────────────────────────────────────────────
    Rule(
        id="TS-STY001",
        category="style",
        severity="suggestion",
        message="Missing return type annotation on exported function",
        pattern=r"export\s+(async\s+)?function\s+\w+\s*\([^)]*\)\s*\{",
        suggestion="Add an explicit return type annotation for better API documentation.",
        languages=["typescript"],
    ),
    Rule(
        id="TS-STY002",
        category="style",
        severity="suggestion",
        message="Interface name should start with `I` prefix or be clearly named",
        pattern=r"interface\s+[a-z]\w*\s*\{",
        suggestion="Use PascalCase for interface names.",
        languages=["typescript"],
    ),
    Rule(
        id="TS-STY003",
        category="style",
        severity="suggestion",
        message="Enum member should be in UPPER_CASE or PascalCase",
        pattern=r"enum\s+\w+\s*\{[^}]*[a-z][a-z_]+\s*=",
        suggestion="Use PascalCase or SCREAMING_SNAKE_CASE for enum members.",
        languages=["typescript"],
    ),
    # ── PERFORMANCE ───────────────────────────────────────────────────────────
    Rule(
        id="TS-PERF001",
        category="performance",
        severity="warning",
        message="Avoid synchronous operations in async functions",
        pattern=r"async\s+\w+[^{]*\{[^}]*readFileSync|writeFileSync",
        suggestion="Use async fs.promises methods inside async functions.",
        languages=["typescript"],
    ),
    # ── ARCHITECTURE ──────────────────────────────────────────────────────────
    Rule(
        id="TS-ARCH001",
        category="architecture",
        severity="suggestion",
        message="TODO / FIXME comment in code",
        pattern=r"//\s*(TODO|FIXME|HACK|XXX)\b",
        suggestion="Resolve the issue or create a tracked ticket.",
        languages=["typescript"],
    ),
    Rule(
        id="TS-ARCH002",
        category="architecture",
        severity="suggestion",
        message="Console.log left in code",
        pattern=r"\bconsole\.(log|debug|warn|error)\s*\(",
        suggestion="Use a proper logging library and remove debug statements.",
        languages=["typescript"],
    ),
]
