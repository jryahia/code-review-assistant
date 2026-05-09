"""GitHub API client — fetch PRs, post comments, clone repos."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger(__name__)

GITHUB_API_BASE = "https://api.github.com"


@dataclass
class PRFile:
    filename: str
    status: str
    additions: int
    deletions: int
    changes: int
    patch: Optional[str] = None
    raw_url: Optional[str] = None
    blob_url: Optional[str] = None
    sha: Optional[str] = None
    contents_url: Optional[str] = None


@dataclass
class PRInfo:
    number: int
    title: str
    body: Optional[str]
    state: str
    html_url: str
    head_ref: str
    base_ref: str
    head_sha: str
    repo_owner: str
    repo_name: str
    additions: int
    deletions: int
    changed_files: int
    files: List[PRFile] = field(default_factory=list)
    labels: List[str] = field(default_factory=list)
    draft: bool = False


class GitHubClient:
    """Async GitHub API client with rate limit handling."""

    def __init__(self, token: str = "") -> None:
        self.token = token
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "CodeReviewAssistant/1.0",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.AsyncClient(
            base_url=GITHUB_API_BASE,
            headers=headers,
            timeout=30.0,
        )

    async def __aenter__(self) -> "GitHubClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._client.aclose()

    async def close(self) -> None:
        await self._client.aclose()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def _get(self, path: str, params: Optional[Dict] = None) -> Any:
        response = await self._client.get(path, params=params)

        if response.status_code == 401:
            raise GitHubAuthError("Invalid or missing GitHub token")
        if response.status_code == 403:
            remaining = response.headers.get("X-RateLimit-Remaining", "?")
            raise GitHubRateLimitError(f"Rate limited. Remaining: {remaining}")
        if response.status_code == 404:
            raise GitHubNotFoundError(f"Resource not found: {path}")
        response.raise_for_status()
        return response.json()

    async def _post(self, path: str, json: Dict) -> Any:
        response = await self._client.post(path, json=json)
        if response.status_code == 401:
            raise GitHubAuthError("Invalid or missing GitHub token")
        response.raise_for_status()
        return response.json()

    async def get_pr(self, owner: str, repo: str, pr_number: int) -> PRInfo:
        """Fetch PR metadata."""
        data = await self._get(f"/repos/{owner}/{repo}/pulls/{pr_number}")
        files = await self.get_pr_files(owner, repo, pr_number)
        return PRInfo(
            number=data["number"],
            title=data["title"],
            body=data.get("body"),
            state=data["state"],
            html_url=data["html_url"],
            head_ref=data["head"]["ref"],
            base_ref=data["base"]["ref"],
            head_sha=data["head"]["sha"],
            repo_owner=data["base"]["repo"]["owner"]["login"],
            repo_name=data["base"]["repo"]["name"],
            additions=data.get("additions", 0),
            deletions=data.get("deletions", 0),
            changed_files=data.get("changed_files", 0),
            files=files,
            labels=[lbl["name"] for lbl in data.get("labels", [])],
            draft=data.get("draft", False),
        )

    async def get_pr_files(self, owner: str, repo: str, pr_number: int) -> List[PRFile]:
        """Fetch all changed files in a PR (handles pagination)."""
        files: List[PRFile] = []
        page = 1
        while True:
            data = await self._get(
                f"/repos/{owner}/{repo}/pulls/{pr_number}/files",
                params={"per_page": 100, "page": page},
            )
            if not data:
                break
            for f in data:
                files.append(
                    PRFile(
                        filename=f["filename"],
                        status=f["status"],
                        additions=f.get("additions", 0),
                        deletions=f.get("deletions", 0),
                        changes=f.get("changes", 0),
                        patch=f.get("patch"),
                        raw_url=f.get("raw_url"),
                        blob_url=f.get("blob_url"),
                        sha=f.get("sha"),
                        contents_url=f.get("contents_url"),
                    )
                )
            if len(data) < 100:
                break
            page += 1
        return files

    async def get_file_content(
        self, owner: str, repo: str, path: str, ref: Optional[str] = None
    ) -> str:
        """Fetch raw file content from a specific ref."""
        params: Dict = {}
        if ref:
            params["ref"] = ref
        data = await self._get(f"/repos/{owner}/{repo}/contents/{path}", params=params)
        if isinstance(data, dict) and data.get("encoding") == "base64":
            import base64
            return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        return ""

    async def post_pr_comment(
        self, owner: str, repo: str, pr_number: int, body: str
    ) -> Dict:
        """Post a comment on a PR."""
        return await self._post(
            f"/repos/{owner}/{repo}/issues/{pr_number}/comments",
            json={"body": body},
        )

    async def post_pr_review(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        body: str,
        event: str = "COMMENT",
        comments: Optional[List[Dict]] = None,
    ) -> Dict:
        """Post a formal PR review with inline comments."""
        payload: Dict = {"body": body, "event": event}
        if comments:
            payload["comments"] = comments
        return await self._post(
            f"/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
            json=payload,
        )

    async def list_open_prs(
        self, owner: str, repo: str, base: Optional[str] = None
    ) -> List[Dict]:
        """List open PRs for a repository."""
        params: Dict = {"state": "open", "per_page": 50}
        if base:
            params["base"] = base
        return await self._get(f"/repos/{owner}/{repo}/pulls", params=params)

    async def get_repo_info(self, owner: str, repo: str) -> Dict:
        """Fetch repository metadata."""
        return await self._get(f"/repos/{owner}/{repo}")

    async def verify_token(self) -> Dict:
        """Verify the token by fetching authenticated user info."""
        return await self._get("/user")


def parse_pr_url(url: str) -> tuple[str, str, int]:
    """Parse a GitHub PR URL into (owner, repo, pr_number)."""
    # Supports: https://github.com/owner/repo/pull/123
    # or: github.com/owner/repo/pull/123
    pattern = re.compile(
        r"(?:https?://)?github\.com/([^/]+)/([^/]+)/pull/(\d+)",
        re.IGNORECASE,
    )
    match = pattern.search(url)
    if not match:
        raise ValueError(f"Cannot parse GitHub PR URL: {url!r}")
    owner, repo, number = match.group(1), match.group(2), int(match.group(3))
    # Remove .git suffix if present
    repo = repo.rstrip("/").removesuffix(".git")
    return owner, repo, number


def parse_repo_url(url: str) -> tuple[str, str]:
    """Parse a GitHub repo URL into (owner, repo)."""
    pattern = re.compile(
        r"(?:https?://)?github\.com/([^/]+)/([^/\s]+?)(?:\.git)?/?$",
        re.IGNORECASE,
    )
    match = pattern.search(url)
    if not match:
        raise ValueError(f"Cannot parse GitHub repo URL: {url!r}")
    return match.group(1), match.group(2)


class GitHubAuthError(Exception):
    pass


class GitHubRateLimitError(Exception):
    pass


class GitHubNotFoundError(Exception):
    pass
