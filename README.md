# Reddit Skills

A modular collection of Reddit operation skills for AI agents. Each skill uses **Python + Rustwright** to browse Reddit like a human and exposes a clean tool interface through **MCP**, so you can automate discovery, publishing, interaction, and validation to operate a brand or product on Reddit.

## Why this exists

Reddit is one of the richest sources of product-market signal, but it is also one of the most hostile to bots and low-effort automation. This project makes it possible to:

- Explore communities, posts, and user profiles at human speed.
- Validate business ideas against real Reddit discussions.
- Publish content and interact with comments authentically.
- Run compound operations like trend tracking and engagement campaigns.

The goal is agentic operations: the agent decides what to do, the skill executes it in a browser, and the result is returned as structured output.

## Stack

- **Python 3.10+** — orchestration, data processing, and LLM integration.
- **Rustwright / Playwright** — realistic browser control with human-like input, scrolling, and navigation.
- **MCP (Model Context Protocol)** — standard tool interface so an AI agent can discover and call skills.
- **LLMs** — summarization, scoring, content generation, and report writing where appropriate.

## Skill catalog

| Skill | Status | Description | Core Capabilities |
| --- | --- | --- | --- |
| reddit-auth | Complete | Authentication and session management | Rustwright browser login, bearer token, PRAW script app, public fallback, session refresh, credential hygiene |
| reddit-validator | Complete | Idea validation via Reddit scraping and LLM analysis | Search, scrape, multi-agent analysis, scored HTML report, recovery |
| reddit-explore | Complete | Discovery and research | Search posts, browse subreddits, read post details with comments, view user profiles |
| reddit-publish | Complete | Content publishing | Research top content, draft in a chosen style, submit text/link/image posts (with `--dry-run`) |
| reddit-interact | Complete | Social interaction | Comment, reply, upvote, downvote, save |
| reddit-orchestrator | Complete | Compound operations and workflow orchestration | Hybrid planner (pattern + LLM), DAG execution with conditionals, retries, checkpoints, 4 pre-built workflows |

All six skills are runnable today.

## Installation

### Prerequisites

- **Python 3.10+** (check with `python --version`)
- **uv** — fast Python package installer (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- **Node.js 18+** — only needed if installing skills via `skills.sh`
- A Reddit account (for browser-based auth) or Reddit API credentials (for PRAW/token auth)
- Optional: `OPENAI_API_KEY` or `OPENROUTER_API_KEY` for LLM-powered features (idea analysis, content drafting, orchestrator fallback planning)

### Option A — Install via skills.sh

This project is compatible with [skills.sh](https://skills.sh). Install individual skills into your project:

```bash
# Install a single skill
npx skills add lingoforge-ai/reddit-skills --skill reddit-auth

# Install multiple skills
npx skills add lingoforge-ai/reddit-skills --skill reddit-auth --skill reddit-validator --skill reddit-orchestrator

# Install all skills
npx skills add lingoforge-ai/reddit-skills --all
```

Installed skills land in `skills/<skill-name>/` with a `SKILL.md` contract that AI agents can discover and invoke.

### Option B — Clone and run directly

```bash
git clone https://github.com/lingoforge-ai/reddit-skills.git
cd reddit-skills
```

### Set up a virtual environment

```bash
uv venv
source .venv/bin/activate    # macOS / Linux
# .venv\Scripts\activate     # Windows
```

### Install dependencies

Each skill has its own `requirements.txt`. Install all at once:

```bash
for skill in skills/*/; do
  [ -f "$skill/requirements.txt" ] && uv pip install -r "$skill/requirements.txt"
done
```

Or install individually:

```bash
uv pip install -r skills/reddit-auth/requirements.txt
uv pip install -r skills/reddit-validator/requirements.txt
uv pip install -r skills/reddit-orchestrator/requirements.txt
```

### Configure environment variables

Copy the example env file and fill in your Reddit credentials:

```bash
cp skills/reddit-auth/.env.example .env
```

Edit `.env`:

```env
# Authentication method: rustwright (browser) | token | praw
REDDIT_LOGIN_METHOD=rustwright

# Optional: for token/praw methods
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
REDDIT_USER_AGENT=script:reddit-skills:v0.1 (by /u/your_username)

# Optional: for PRAW script apps only
REDDIT_USERNAME=
REDDIT_PASSWORD=
```

For LLM-powered features, set one of these as shell environment variables (dotenv does not overwrite existing env vars):

```bash
export OPENAI_API_KEY="sk-..."
# or
export OPENROUTER_API_KEY="sk-or-..."
```

## How it works

1. **Browser layer**: Rustwright drives a real Chromium browser, with human-like delays, scrolls, and clicks to avoid bot detection.
2. **Skill layer**: Each skill is a self-contained module with a `SKILL.md` contract and a `pipeline/` of Python scripts.
3. **MCP layer**: Skills expose entrypoints an AI agent can call, returning JSON or rendered reports.
4. **Orchestration layer**: `reddit-orchestrator` composes skills into multi-step workflows — a hybrid planner matches known requests to pre-built templates or falls back to an LLM, then a DAG runner executes steps with conditionals, retries, and checkpoints.

## Quickstart

### Step 1 — Authenticate

Authenticate once with `reddit-auth`, then any other skill reuses the saved session:

```bash
python skills/reddit-auth/scripts/preflight.py
python skills/reddit-auth/scripts/login.py
```

### Step 2 — Run a skill

Every skill has a `preflight.py` that checks dependencies and credentials. Run it first, then the skill's main script:

```bash
# reddit-validator — validate an idea and produce a scored HTML report
python skills/reddit-validator/scripts/preflight.py
python skills/reddit-validator/scripts/run_pipeline.py "your idea" --profile standard
python skills/reddit-validator/scripts/extract_report.py --run-id <run_id>

# reddit-explore — search, browse, read posts, look up users
python skills/reddit-explore/scripts/preflight.py
python skills/reddit-explore/scripts/search.py "<query>"
python skills/reddit-explore/scripts/subreddit.py "<name>"
python skills/reddit-explore/scripts/post.py "<url_or_id>"
python skills/reddit-explore/scripts/user.py "<name>"

# reddit-publish — research, draft, and submit a post
python skills/reddit-publish/scripts/preflight.py
python skills/reddit-publish/scripts/research.py "<topic>" [--subreddit ...] [--suggest-subreddit]
python skills/reddit-publish/scripts/draft.py path/to/research.json [--style ...]
python skills/reddit-publish/scripts/publish.py path/to/draft.json [--dry-run]

# reddit-interact — comment, reply, vote, save (all support --dry-run)
python skills/reddit-interact/scripts/preflight.py
python skills/reddit-interact/scripts/comment.py "<post_url_or_id>" --text "..." [--text-file path] [--dry-run]
python skills/reddit-interact/scripts/reply.py "<comment_url_or_id>" --text "..." [--text-file path] [--dry-run]
python skills/reddit-interact/scripts/upvote.py "<url_or_id>" [--dry-run]
python skills/reddit-interact/scripts/downvote.py "<url_or_id>" [--dry-run]
python skills/reddit-interact/scripts/save.py "<url_or_id>" [--unsave] [--dry-run]

# reddit-orchestrator — plan and execute compound workflows
python skills/reddit-orchestrator/scripts/preflight.py
python skills/reddit-orchestrator/scripts/plan.py "validate my idea: AI tutor for kids" [--workflow name] [--out plan.json]
python skills/reddit-orchestrator/scripts/run.py --plan plan.json [--dry-run]
python skills/reddit-orchestrator/scripts/run.py --request "validate my idea: AI tutor for kids" --dry-run
```

### Orchestrator workflows

The orchestrator ships with four pre-built workflows. It pattern-matches your request (English or Chinese) and dispatches the right skills automatically:

| Trigger phrase | Workflow | Skills used |
| --- | --- | --- |
| "validate my idea: X" | `validate_idea` | reddit-validator |
| "grow my brand X on subreddits Y, Z" | `brand_growth` | reddit-explore → reddit-publish → reddit-interact |
| "track trends for X" | `track_trends` | reddit-explore |
| "engage with communities about X" | `engage_community` | reddit-explore → reddit-interact |

For novel requests that don't match any pattern, the orchestrator falls back to an LLM to generate a custom plan.

### Dry-run mode

Most skills support `--dry-run` to preview actions without executing them. Always use it before the first real run in a session:

```bash
python skills/reddit-orchestrator/scripts/run.py --request "grow my brand Acme on subreddits r/SaaS, r/startups" --dry-run
```

## Project structure

```text
reddit-skills/
├── skills/                        # Self-contained skill modules
│   ├── reddit-auth/               # Authentication & session management
│   │   ├── SKILL.md               # Skill contract
│   │   ├── pipeline/
│   │   │   └── auth.py            # Core auth logic (Rustwright, PRAW, token)
│   │   ├── scripts/
│   │   │   ├── preflight.py       # Dependency & credential checks
│   │   │   └── login.py           # Interactive browser login
│   │   ├── tests/
│   │   │   └── test_auth.py
│   │   ├── requirements.txt
│   │   └── .env.example
│   ├── reddit-validator/          # Idea validation via Reddit scraping + LLM
│   │   ├── SKILL.md
│   │   ├── pipeline/
│   │   │   ├── analyzer.py        # Multi-agent LLM analysis
│   │   │   ├── config.py          # Profiles & parameters
│   │   │   ├── report.py          # HTML report generation
│   │   │   ├── runner.py          # Pipeline orchestration
│   │   │   └── scraper.py         # Reddit discussion scraping
│   │   ├── scripts/
│   │   │   ├── preflight.py
│   │   │   ├── run_pipeline.py    # Main entrypoint
│   │   │   ├── extract_report.py  # Extract report from run
│   │   │   ├── render_report.py   # Re-render HTML report
│   │   │   └── recover.py         # Recovery from failed runs
│   │   ├── resources/             # Agent guides (CLAUDE.md, DEVIN.md, failure-recovery, param-matrix, report-anatomy)
│   │   ├── tests/                 # 11 test files
│   │   ├── requirements.txt
│   │   └── .env.example
│   ├── reddit-explore/            # Discovery & research
│   │   ├── SKILL.md
│   │   ├── pipeline/
│   │   │   ├── client.py          # Reddit API client
│   │   │   ├── explorer.py        # Search, subreddit, post, user logic
│   │   │   ├── records.py         # Output record management
│   │   │   └── paths.py           # Skill-specific paths
│   │   ├── scripts/
│   │   │   ├── preflight.py
│   │   │   ├── search.py          # Search posts
│   │   │   ├── subreddit.py       # Browse a subreddit
│   │   │   ├── post.py            # Read post + comments
│   │   │   └── user.py            # View user profile
│   │   ├── resources/             # Agent guides (CLAUDE.md, DEVIN.md, failure-recovery)
│   │   ├── tests/                 # 9 test files
│   │   ├── requirements.txt
│   │   └── .env.example
│   ├── reddit-publish/            # Content publishing
│   │   ├── SKILL.md
│   │   ├── pipeline/
│   │   │   ├── researcher.py      # Research top content in a topic
│   │   │   ├── drafter.py         # LLM-powered draft generation
│   │   │   ├── imager.py          # Image post handling
│   │   │   ├── publisher.py       # Submit posts (text/link/image)
│   │   │   ├── prompts.py         # LLM prompt templates
│   │   │   └── paths.py
│   │   ├── scripts/
│   │   │   ├── preflight.py
│   │   │   ├── research.py        # Research a topic
│   │   │   ├── draft.py           # Draft a post from research
│   │   │   └── publish.py         # Submit (supports --dry-run)
│   │   ├── resources/             # Agent guides (CLAUDE.md, DEVIN.md, failure-recovery)
│   │   ├── tests/                 # 10 test files
│   │   ├── requirements.txt
│   │   └── .env.example
│   ├── reddit-interact/           # Social interaction
│   │   ├── SKILL.md
│   │   ├── pipeline/
│   │   │   ├── interactor.py      # Comment, reply, vote, save logic
│   │   │   └── paths.py
│   │   ├── scripts/
│   │   │   ├── preflight.py
│   │   │   ├── comment.py         # Comment on a post
│   │   │   ├── reply.py           # Reply to a comment
│   │   │   ├── upvote.py          # Upvote
│   │   │   ├── downvote.py        # Downvote
│   │   │   └── save.py            # Save / unsave
│   │   ├── resources/             # Agent guides (CLAUDE.md, DEVIN.md, failure-recovery)
│   │   ├── tests/                 # 7 test files
│   │   ├── requirements.txt
│   │   └── .env.example
│   └── reddit-orchestrator/       # Compound workflow orchestration
│       ├── SKILL.md
│       ├── pipeline/
│       │   ├── planner.py         # Hybrid planner (pattern matching + LLM fallback)
│       │   ├── runner.py          # DAG executor with conditionals, retries, checkpoints
│       │   ├── workflows.py       # 4 pre-built workflow templates
│       │   ├── skill_catalog.py   # Static skill metadata
│       │   ├── state.py           # Plan state persistence for resume
│       │   └── paths.py           # Output directory helpers
│       ├── scripts/
│       │   ├── preflight.py       # Check all skill dirs + auth
│       │   ├── plan.py            # Generate plan JSON from a request
│       │   └── run.py             # Execute a plan, streaming JSONL events
│       ├── tests/                 # 8 test files (64 tests total)
│       └── requirements.txt
├── src/common/                    # Shared libraries across all skills
│   ├── paths.py                   # Output dirs (.reddit-skills/), version constant
│   └── llm.py                     # Shared LLM client (OpenAI / OpenRouter)
├── docs/                          # Design specs & implementation plans
├── VERSION                        # Project version (single source of truth)
├── AGENTS.md                      # Agent notes for AI coding assistants
└── README.md                      # You are here
```

### Runtime outputs

All skills write runtime artifacts (reports, logs, checkpoints, records) to a single `.reddit-skills/` directory in the current working directory. This keeps generated content out of the skill source tree and git repo.

## Testing

Each skill includes a `tests/` directory with pytest tests. Run all tests:

```bash
python -m pytest skills/reddit-orchestrator/tests/ -v
```

Run a specific skill's tests:

```bash
cd skills/reddit-orchestrator && python -m pytest tests/ -v
```

The orchestrator has 64 tests covering: skill catalog, workflow templates, planner (pattern matching + LLM fallback), DAG runner (topological sort, placeholder resolution, conditionals, retries, checkpoints), preflight, plan CLI, and run CLI.

## Adding a new skill

1. Create `skills/<skill-name>/`.
2. Write a `SKILL.md` describing purpose, prerequisites, workflow, error recovery, and operating principles.
3. Implement the `pipeline/` in Python, using Rustwright for browser work.
4. Add `requirements.txt` and a `preflight.py` script.
5. Write tests in `tests/` using pytest.
6. Expose an MCP-friendly entrypoint via `scripts/`.
7. If the skill should be orchestratable, add it to `pipeline/skill_catalog.py` in `reddit-orchestrator`.

## Contributing

- Follow the existing skill structure: `SKILL.md` contract + `pipeline/` + `scripts/` + `tests/`.
- Run `python -m pytest` before submitting changes.
- Use `--dry-run` flags for any skill that modifies Reddit state.
- Respect Reddit rate limits — never bypass them.
- Keep `SKILL.md` files as the single source of truth for each skill's contract.

## License

[MIT](LICENSE)
