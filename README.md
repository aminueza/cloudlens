# CloudLens — AI-Powered Multi-Cloud Network Intelligence

Network observability and intelligence platform for SREs. Monitors topology across AWS, Azure, and GCP — detects changes, evaluates compliance, analyzes blast radius, manages incidents, and provides AI-powered insights.

## Quick Start

```bash
pip install ".[dev]"
CLOUDLENS_AUTH_DISABLED=true python3 main.py
# http://localhost:8050
```

### With AI

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
CLOUDLENS_AUTH_DISABLED=true python3 main.py
```

### Docker

```bash
docker build -t cloudlens .
docker run -p 8050:8050 -e CLOUDLENS_AUTH_DISABLED=true cloudlens
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `ENABLED_PROVIDERS` | `azure` | Comma-separated: aws, azure, gcp |
| `CLOUDLENS_POLL_INTERVAL` | `300` | Background poll interval (seconds) |
| `CLOUDLENS_AUTH_DISABLED` | `false` | Disable auth for local dev |
| `ANTHROPIC_API_KEY` | `""` | Claude API key (optional) |
| `AI_MODEL` | `claude-sonnet-4-20250514` | Claude model |
| `DB_PATH` | `data/cloudlens.db` | SQLite path |

## Features

- Multi-cloud topology visualization (D3.js force-directed graph)
- Change tracking with timeline navigation
- 10 automated health checks with A-F scoring
- Configurable compliance rules engine
- Blast radius analysis (Tarjan's algorithm)
- Incident management with auto-enrichment
- AI assistant (Claude) with graceful fallback
- SSE real-time updates
- Provider-aware auth error handling
