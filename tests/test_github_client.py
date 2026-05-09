"""Tests for the GitHub client."""

from __future__ import annotations

import pytest

from src.github_client import parse_pr_url, parse_repo_url


@pytest.mark.parametrize(
    "url,expected",
    [
        (
            "https://github.com/octocat/Hello-World/pull/42",
            ("octocat", "Hello-World", 42),
        ),
        (
            "github.com/torvalds/linux/pull/9999",
            ("torvalds", "linux", 9999),
        ),
        (
            "https://github.com/my-org/my.repo/pull/1",
            ("my-org", "my.repo", 1),
        ),
    ],
)
def test_parse_pr_url_valid(url: str, expected: tuple) -> None:
    owner, repo, number = parse_pr_url(url)
    assert owner == expected[0]
    assert repo == expected[1]
    assert number == expected[2]


@pytest.mark.parametrize(
    "url",
    [
        "https://gitlab.com/org/repo/merge_requests/1",
        "https://github.com/org/repo",
        "not-a-url",
        "",
    ],
)
def test_parse_pr_url_invalid(url: str) -> None:
    with pytest.raises(ValueError):
        parse_pr_url(url)


@pytest.mark.parametrize(
    "url,expected",
    [
        (
            "https://github.com/octocat/Hello-World",
            ("octocat", "Hello-World"),
        ),
        (
            "https://github.com/octocat/Hello-World.git",
            ("octocat", "Hello-World"),
        ),
        (
            "github.com/my-org/my-repo/",
            ("my-org", "my-repo"),
        ),
    ],
)
def test_parse_repo_url_valid(url: str, expected: tuple) -> None:
    owner, repo = parse_repo_url(url)
    assert owner == expected[0]
    assert repo == expected[1]


def test_parse_repo_url_invalid() -> None:
    with pytest.raises(ValueError):
        parse_repo_url("https://gitlab.com/org/repo")


def test_webhook_signature_verification() -> None:
    from src.webhook_handler import verify_signature

    payload = b'{"action": "opened"}'
    secret = "mysecret"

    import hashlib
    import hmac
    expected_sig = "sha256=" + hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()

    assert verify_signature(payload, expected_sig, secret) is True
    assert verify_signature(payload, "sha256=wrong", secret) is False
    assert verify_signature(payload, "", secret) is False


def test_webhook_signature_no_secret() -> None:
    from src.webhook_handler import verify_signature
    assert verify_signature(b"payload", "", "") is True


def test_scoring_calculate() -> None:
    from src.analyzer.checkers import CheckerFinding
    from src.scoring import calculate_score, get_score_band, get_score_color

    no_findings: list = []
    assert calculate_score(no_findings) == 100.0

    one_critical = [CheckerFinding("security", "critical", 1, 1, "SQL injection")]
    score = calculate_score(one_critical)
    assert score == 90.0

    many_critical = [CheckerFinding("security", "critical", i, i, "Issue") for i in range(11)]
    score = calculate_score(many_critical)
    assert score == 0.0

    mixed = [
        CheckerFinding("bugs", "critical", 1, 1, "Critical bug"),
        CheckerFinding("style", "warning", 2, 2, "Style warning"),
        CheckerFinding("architecture", "suggestion", 3, 3, "Suggestion"),
    ]
    score = calculate_score(mixed)
    assert score == 84.0  # 100 - 10 - 5 - 1

    label, color = get_score_band(95.0)
    assert label == "Excellent"
    assert color == "#22c55e"

    label, color = get_score_band(75.0)
    assert label == "Good"
    assert color == "#4f8cff"

    label, color = get_score_band(55.0)
    assert label == "Needs Work"
    assert color == "#fbbf24"

    label, color = get_score_band(20.0)
    assert label == "Poor"
    assert color == "#ef4444"
