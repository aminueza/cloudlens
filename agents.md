# AI Agent Rules — CloudLens

> Read this FIRST before touching any code. These rules prevent the mistakes that matter.

---

## Core Principles

- **Simplicity First** — Make every change as simple as possible. Minimal code impact.
- **No Laziness** — Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact** — Only touch what's necessary. Don't introduce bugs.
- **Prove It Works** — Never say "done" without running tests or showing evidence.

---

## The Project

AI-powered multi-cloud network intelligence platform for SREs — monitors topology across AWS, Azure, and GCP, detects changes, evaluates compliance, analyzes blast radius, manages incidents, and provides AI-powered insights via Claude API. Not a dashboard — a network operations copilot.

**Stack:** Python 3.12 · FastAPI · D3.js · boto3 (AWS) · Azure Resource Graph (Azure) · GCP Compute (stub) · aiosqlite · Anthropic Claude · Pydantic · Prometheus · SlowAPI · Black (formatter)

**Architecture:** `config/ → providers/ → graph/ → api/ → frontend` + `db/` (persistence) + `engine/` (analysis) + `ai/` (intelligence)

---

## Hard Rules (Break These = Break the Project)

| Rule | Why |
|---|---|
| Never import cloud SDKs outside `providers/` | One coupling point per provider. Core logic is cloud-agnostic. |
| Provider modules implement `ProviderInterface` | Swap or add providers without touching core code. |
| Never return raw dicts from API routes | Pydantic response models on every endpoint. |
| Never duplicate resource-mapping logic | It lives once in `graph/helpers.py`. |
| Never duplicate constants | Icons, colors, labels → `graph/constants.py`. |
| Never hardcode config | All settings via `pydantic-settings` from env vars. |
| Range-pin every dependency | `>=X,<Y` in `pyproject.toml`. Cloud SDKs are optional extras. |
| Python ≥ 3.12 | Use `X | Y` unions, f-strings, type hints everywhere. |
| Async-first | Blocking cloud SDK calls go through `asyncio.to_thread`. |
| Ruff target py312, line length 120 | `ruff check .` must pass clean. |
| Black for formatting | `black --check .` must pass clean. |
| Never block startup on auth | Provider clients init without validating credentials. |
| Never swallow auth errors silently | Auth failures propagate to frontend via provider error state. |
| Single uvicorn worker | BackgroundFetcher + SQLite are not multi-process safe. |
| AI reads settings, not os.environ | Use `settings.ANTHROPIC_API_KEY` and `settings.AI_MODEL`. |

---

## Project Layout

```
config/            Settings (pydantic-settings), accounts.yaml, structured logging
providers/         Cloud provider abstraction layer
  base.py            ProviderInterface ABC + NetworkResource/NetworkPeering dataclasses
  registry.py        Auto-discovers and loads enabled providers
  fetcher.py         BackgroundFetcher — polls, caches, persists, runs analysis, SSE
  aws/client.py      AWS EC2/VPC API queries → normalized NetworkResource
  azure/client.py    Azure Resource Graph KQL → normalized NetworkResource
  azure/queries.py   KQL strings + AZURE_TYPE_MAP
  gcp/client.py      GCP stub (returns empty lists when SDK not installed)
graph/             Cloud-agnostic graph builders, constants, helpers
  builder.py         build_graph() [flat] + build_structured_graph() [hierarchical]
  constants.py       TYPE_LABELS, TYPE_ICONS, TYPE_COLORS, PROVIDER_COLORS, ENV_COLORS
  helpers.py         safe_id, find_network_for_resource, build_resource_index
db/                SQLite persistence via aiosqlite
  session.py         Schema (7 tables), connection management, default compliance rules
  repository.py      CRUD for snapshots, changes, incidents, compliance, health, AI
engine/            Cloud-agnostic analysis engines
  diff.py            Topology diff — compares snapshots, detects changes with severity
  health.py          10 health checks + A-F scoring
  compliance.py      Configurable rules engine (6 rule types)
  blast_radius.py    Impact analysis + Tarjan's algorithm for critical nodes
ai/                Claude API integration
  analyzer.py        NL queries, change analysis, anomaly detection, incident RCA, compliance recs
api/               FastAPI app, routes, middleware, models
  app.py             Lifespan (DB init, provider registry, fetcher), middleware stack
  auth.py            Pluggable auth middleware (API key / disabled for dev)
  errors.py          CloudLensError + exception handlers
  models.py          Pydantic response models
  ratelimit.py       slowapi limiter
  routes/            accounts, topology, export, changes, health_checks, compliance, incidents, ai_routes
exporters/         SVG diagram renderer
templates/         index.html — Jinja2 SPA
static/css/        dashboard.css (dark/light, 14px base)
static/js/         graph.js — D3.js viz, provider badges, AI chat, incidents
tests/             pytest — 32 tests across 7 files
```

---

## Key Data Flow

```
accounts.yaml
    ↓
Settings (pydantic-settings, env vars)
    ↓
ProviderRegistry (loads enabled providers: aws, azure, gcp)
    ↓
BackgroundFetcher._poll_loop()
    ↓
┌─────────────┬───────────────────┬──────────────┐
│ AWS EC2 API │ Azure Resource    │ GCP Compute  │
│ (boto3)     │ Graph (KQL)       │ (stub)       │
└──────┬──────┴────────┬──────────┴──────┬───────┘
       └───────────────┼─────────────────┘
                       ↓
              Normalizer (NetworkResource dataclass)
                       ↓
       ┌───────────────┼───────────────┐
       ↓                               ↓
Graph Builders              Analysis Engine
(D3.js hierarchical)        (diff, health, compliance, blast radius)
       ↓                               ↓
       └──────── FastAPI Routes ───────┘
                       ↓
       SQLite (snapshots, changes, incidents, compliance, health)
                       ↓
       D3.js Frontend (SSE auto-refresh, AI chat panel)
                       ↓
       Claude AI (NL queries, change analysis, RCA, anomaly detection)
```

---

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `ENABLED_PROVIDERS` | `azure` | Comma-separated: aws, azure, gcp |
| `CLOUDLENS_POLL_INTERVAL` | `300` | Background fetch interval (seconds) |
| `CLOUDLENS_AUTH_DISABLED` | `false` | Skip auth (for local dev) |
| `CLOUDLENS_AUTH_PUBLIC_PATHS` | `/health,/metrics,/static,...,/api/events,/api/auth/status` | Auth-exempt paths |
| `CLOUDLENS_CORS_ORIGINS` | `*` | Allowed CORS origins |
| `ANTHROPIC_API_KEY` | `""` | Claude API key (optional) |
| `AI_MODEL` | `claude-sonnet-4-20250514` | Claude model |
| `DB_PATH` | `data/cloudlens.db` | SQLite database path |
| `SNAPSHOT_RETENTION` | `100` | Max snapshots per scope |

## Commands

```bash
CLOUDLENS_AUTH_DISABLED=true python3 main.py                    # Run locally
ANTHROPIC_API_KEY=sk-... CLOUDLENS_AUTH_DISABLED=true python3 main.py  # With AI
pytest tests/ -v                                                 # Tests
ruff check .                                                     # Lint
black --check .                                                  # Format check
mypy config graph db engine ai api providers exporters           # Type check
docker build -t cloudlens .                                      # Build container
```

---

## Playbooks

### Add a New Cloud Provider
1. Create `providers/{name}/client.py` implementing `ProviderInterface`
2. Add optional dep in `pyproject.toml`: `[project.optional-dependencies.{name}]`
3. Register in `providers/registry.py`
4. Add account config section in `config/accounts.yaml`
5. No changes needed in graph/, engine/, ai/, api/ — they're cloud-agnostic

### Add a New Resource Type
1. `graph/constants.py` — add to TYPE_LABELS, TYPE_ICONS, TYPE_COLORS
2. `providers/{cloud}/client.py` — normalize to existing or new type in fetch methods
3. `graph/builder.py` — already handles any type via constants lookup

### Add a Compliance Rule Type
1. `engine/compliance.py` — add handler function + register in `_RULE_HANDLERS`
2. `db/session.py` — optionally add a default rule in `DEFAULT_RULES`

### Add a Health Check
1. `engine/health.py` — add `_check_*` function + call from `run_health_checks`

---

## Gotchas

- `graph.js` is ~400 lines — search within it, don't read fully
- Accounts load at import time from `config/accounts.yaml` — missing file = crash
- BackgroundFetcher pauses per-provider on auth failure (60s retry)
- Cloud SDKs are optional: `pip install cloudlens[aws]`, `cloudlens[azure]`, `cloudlens[all-providers]`
- GCP is a stub — returns empty lists, no actual API calls
- AI degrades gracefully without ANTHROPIC_API_KEY
- `data/cloudlens.db` is gitignored — created at runtime
- Provider-specific code NEVER leaks into graph/, engine/, ai/, or api/
