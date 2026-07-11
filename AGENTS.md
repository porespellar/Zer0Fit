# Zer0Fit — Codex Project Instructions

## Project Overview

Zer0Fit is an MCP (Model Context Protocol) server that exposes Google's TimesFM 2.5 (time-series forecasting) and TabFM v1.0.0 (tabular classification/regression) foundation models to AI assistants. It runs on a GPU server (NVIDIA, 16GB+ VRAM) inside Docker, listening on port 8002 via Streamable HTTP + SSE.

## Repository Structure

```
server.py          → MCP server (Starlette, port 8002, SSE + Streamable HTTP)
model_manager.py   → VRAM governor (asyncio.Lock, TTL sweeper, mutual exclusion)
pipelines.py       → Data pipelines (downsampling for TimesFM, chunking for TabFM)
install.sh         → One-command installer (architecture-aware: ARM64 + x86_64)
Dockerfile         → Multi-arch Docker build (CUDA 12.4 x86_64, CUDA 13.2 ARM64 / cu130 wheels)
docker-compose.yml  → GPU profile, reads from .env
```

## Architecture

- **One model in VRAM at a time** — mutual exclusion via `asyncio.Lock`
- **TTL-based auto-unload** — background sweeper evicts idle models (default 300s)
- **asyncio.to_thread** — all PyTorch model loading is offloaded to prevent event-loop blocking
- **Path traversal protection** — `_resolve_path` restricts file access to `/app/data/` and `/app/webui_data/`
- **NaN sanitization** — `chunk_tabular` drops rows with missing targets before feeding to TabFM

## Code Conventions

- Python 3.13+, async/await throughout
- Logging via `logging.getLogger("zer0fit.<module>")`
- Lazy imports for heavy deps (timesfm, tabfm, torch) inside loader functions
- Type hints on all public functions
- No hardcoded secrets — all config via environment variables

## Inference Limits (server.py)

| Limit | Value | Constant |
|---|---|---|
| Forecast horizon | 1–256 | matches TimesFM `max_horizon` |
| Max tabular chunks | 10 (10K rows) | `MAX_CHUNKS_LIMIT` |
| Chunk size | 1,000 rows | `pipelines.TABFM_CHUNK_SIZE` |
| In-context size | 512 rows | `pipelines.TABFM_IN_CONTEXT_SIZE` |
| TimesFM context | 1,024 tokens | `ForecastConfig.max_context` |

See README.md → "Limits & Configurability" for how to change these.

## Common Commands

```bash
# Build and launch
docker compose --profile gpu up --build -d

# Health check
curl http://localhost:8002/health

# Stop
docker compose --profile gpu down

# Update from GitHub
git pull origin main
docker compose --profile gpu down
docker compose --profile gpu up --build -d
```

## Using Zer0Fit MCP Tools from Codex

Connect Codex to the Zer0Fit MCP server:

```bash
codex mcp add zerofit --url http://YOUR-SERVER-IP:8002/mcp
```

Then use the four MCP tools:
- `zer0fit_inspect(file_path)` — discover columns and data types (ALWAYS call first)
- `zer0fit_upload_csv(filename, content_base64)` — upload a file not on the server
- `zer0fit_forecast(file_path, target_column, horizon, datetime_column?)` — time-series forecasting
- `zer0fit_tabular(file_path, target_column, task_type, max_chunks?)` — classification or regression

### Workflow
1. Call `zer0fit_inspect` to discover column names and data types
2. Call `zer0fit_forecast` or `zer0fit_tabular` with the correct target column
3. Interpret the pre-computed metrics (accuracy, R², MAE, etc.) for the user

## Disclaimer

Zer0Fit is research-use-only software. No warranties. The developer is not responsible for prediction accuracy. See [DISCLAIMER.md](DISCLAIMER.md).