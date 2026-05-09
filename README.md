# Code Review Assistant Pro

A production-quality, AI-powered code review automation tool with a dark-themed desktop UI.

## Features

- **PR Analysis** — Paste a GitHub PR URL to fetch diffs and analyze all changed files
- **Multi-Language Support** — Python, JavaScript, TypeScript, Go, Rust, Java, Ruby, Solidity
- **5 Analyzer Categories** — Bugs, Security, Style, Performance, Architecture
- **AI Review** — Optional semantic review via OpenAI GPT or Anthropic Claude
- **Score Gauge** — Composite 0-100 score with color bands (red/yellow/blue/green)
- **Per-File Breakdown** — Line numbers, severity badges, code snippets, fix suggestions
- **Export** — Markdown report, PDF report, or GitHub PR comment
- **History** — All past reviews with search, filter, and re-run
- **Projects** — Monitored repos with auto-watch and webhook receiver
- **Settings** — Token management, AI config, custom ignore patterns

## Screenshots

```
┌─────────────────────────────────────────────────────────────────┐
│  ⚡ Code Review Assistant                            API :8765  │
├──────────────┬──────────────────────────────────────────────────┤
│  Dashboard   │  Dashboard                         [New Review]  │
│  New Review  │                                                   │
│  History     │  📋 Total    📊 Avg    🔴 Critical  🟡 Warnings  │
│  Projects    │  42 reviews  76.3     12 issues    34 warnings   │
│  Settings    │                                                   │
│              │  Recent Reviews                                   │
│              │  ┌─────────────────────────────────────────────┐ │
│              │  │ feat: add auth middleware           92 ✅   │ │
│              │  │ myorg/api • #142 • 2025-01-15  completed    │ │
│              │  └─────────────────────────────────────────────┘ │
└──────────────┴──────────────────────────────────────────────────┘
```

## Quick Start

### Standalone (SQLite)

```bash
# Clone and install
cd ~/.hermes/profiles/codex/workspace/projects/code-review-assistant
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env: set GITHUB_TOKEN at minimum

# Launch
python main.py
```

### Docker (PostgreSQL)

```bash
cp .env.example .env
# Set GITHUB_TOKEN in .env

docker-compose up --build
```

The API runs at `http://localhost:8765`.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GITHUB_TOKEN` | — | GitHub PAT with `repo` scope (required) |
| `GITHUB_WEBHOOK_SECRET` | — | Webhook HMAC secret (optional) |
| `AI_PROVIDER` | `off` | `openai` \| `claude` \| `off` |
| `OPENAI_API_KEY` | — | OpenAI key (if using GPT) |
| `CLAUDE_API_KEY` | — | Anthropic key (if using Claude) |
| `DATABASE_URL` | SQLite | PostgreSQL URL for Docker |
| `API_PORT` | `8765` | API server port |
| `LOG_LEVEL` | `INFO` | `DEBUG` \| `INFO` \| `WARNING` |

## API Reference

### Reviews

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/reviews` | Start a new PR review |
| `GET` | `/api/reviews` | List reviews (paginated, filterable) |
| `GET` | `/api/reviews/{id}` | Get full review details |
| `DELETE` | `/api/reviews/{id}` | Delete a review |
| `POST` | `/api/reviews/{id}/rerun` | Re-run analysis |
| `POST` | `/api/reviews/{id}/export` | Export (`markdown`/`pdf`/`github_comment`) |

### Projects

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/projects` | Add a monitored repository |
| `GET` | `/api/projects` | List all projects |
| `PATCH` | `/api/projects/{id}` | Update project settings |
| `DELETE` | `/api/projects/{id}` | Remove project |
| `GET` | `/api/projects/{id}/reviews` | Reviews for this project |

### Settings & Webhooks

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/settings` | Get current settings |
| `PUT` | `/api/settings` | Update settings |
| `POST` | `/api/webhooks/github` | GitHub webhook receiver |
| `GET` | `/api/stats` | Global analysis statistics |
| `GET` | `/health` | Health check |

### Example: Start a Review

```bash
curl -X POST http://localhost:8765/api/reviews \
  -H "Content-Type: application/json" \
  -d '{
    "pr_url": "https://github.com/octocat/Hello-World/pull/1",
    "categories": ["bugs", "security", "style"],
    "ai_review": false
  }'
```

### Example: Export as Markdown

```bash
curl -X POST http://localhost:8765/api/reviews/{id}/export \
  -H "Content-Type: application/json" \
  -d '{"format": "markdown"}'
```

## Analyzer Categories

### 🐛 Bugs
- Bare `except:` clauses
- Mutable default arguments
- Off-by-one errors (indexing with `.length`)
- Potential null/nil dereferences
- Infinite loops without exit conditions
- Silent exception suppression

### 🔒 Security
- SQL injection via string formatting/f-strings
- XSS via `innerHTML` assignment
- Command injection (`shell=True`, `os.system`)
- Hardcoded secrets, passwords, API keys
- `eval()` / `exec()` usage
- Insecure deserialization

### ✨ Style
- Naming convention violations (snake_case/camelCase/PascalCase)
- Line length > 120 characters
- Function length > 60 lines (warning)
- High cyclomatic complexity (≥10)
- Duplicate code blocks

### ⚡ Performance
- N+1 query patterns (DB query inside loop)
- Memory leaks (unclosed resources, event listeners)
- String concatenation in loops (O(n²))
- Triple-nested loops (O(n³))
- Sorting to find min/max instead of min()/max()

### 🏗 Architecture
- God functions (>100 lines)
- Deep nesting (>4 levels)
- Magic numbers (unexplained numeric literals)
- God classes (>20 methods)
- Missing error handling
- TODO/FIXME/HACK comments

## Score Bands

| Score | Label | Color |
|-------|-------|-------|
| 90-100 | Excellent | 🟢 Green |
| 70-89 | Good | 🔵 Blue |
| 40-69 | Needs Work | 🟡 Yellow |
| 0-39 | Poor | 🔴 Red |

**Severity weights:**
- Critical: -10 points each
- Warning: -5 points each
- Suggestion: -1 point each

## GitHub Webhook Setup

1. Go to your repository → Settings → Webhooks → Add webhook
2. Set **Payload URL**: `http://your-server:8765/api/webhooks/github`
3. Set **Content type**: `application/json`
4. Set **Secret**: Same as `GITHUB_WEBHOOK_SECRET` in your config
5. Select events: **Pull requests** and **Pushes**

## Running Tests

```bash
pip install pytest pytest-asyncio pytest-cov
pytest tests/ -v --cov=src --cov-report=term-missing
```

## Project Structure

```
code-review-assistant/
├── main.py                    # Entry: launches FastAPI + Flet
├── requirements.txt
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── README.md
└── src/
    ├── config.py              # Pydantic Settings
    ├── database.py            # SQLAlchemy async
    ├── models.py              # ORM models
    ├── schemas.py             # Pydantic v2 schemas
    ├── api_server.py          # FastAPI routes
    ├── github_client.py       # GitHub API client
    ├── ai_reviewer.py         # OpenAI/Claude integration
    ├── scoring.py             # Score calculation
    ├── report_generator.py    # Markdown + PDF
    ├── export.py              # Export functions
    ├── webhook_handler.py     # GitHub webhooks
    ├── analyzer/
    │   ├── engine.py          # Orchestrator
    │   ├── parser.py          # Language detection + AST
    │   ├── checkers/          # 5 analyzer categories
    │   └── rules/             # Per-language rule definitions
    └── ui/
        ├── app.py             # Flet shell + routing
        ├── components.py      # Shared widgets
        ├── dashboard.py       # Dashboard view
        ├── review_view.py     # Review detail view
        ├── project_view.py    # Projects management
        ├── history_view.py    # Review history
        └── settings_view.py   # Settings panel
```

## License

MIT License — use freely in personal and commercial projects.
