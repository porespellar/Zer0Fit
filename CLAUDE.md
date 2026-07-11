# Zer0Fit — Claude Code Project Context

## What Is This Repo?

Zer0Fit is an MCP (Model Context Protocol) server that exposes Google's TimesFM 2.5 (time-series forecasting) and TabFM v1.0.0 (tabular classification/regression) foundation models to AI assistants. It runs on a GPU server (NVIDIA, 16GB+ VRAM) inside Docker, listening on port 8002 via Streamable HTTP + SSE.

## Architecture

```
server.py          → MCP server (Starlette, port 8002, SSE + Streamable HTTP)
model_manager.py   → VRAM governor (asyncio.Lock, TTL sweeper, mutual exclusion)
pipelines.py       → Data pipelines (downsampling for TimesFM, chunking for TabFM)
```

### Key Design Patterns
- **One model in VRAM at a time** — mutual exclusion via `asyncio.Lock`
- **TTL-based auto-unload** — background sweeper evicts idle models (default 300s)
- **asyncio.to_thread** — all PyTorch model loading is offloaded to prevent event-loop blocking
- **tabfm_task_type on _HotModel dataclass** — tracks which TabFM weights are loaded (classification vs regression)
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

## Common Tasks

### Running locally for development
```bash
cd ~/zerofit_project
source .venv/bin/activate
python server.py  # needs GPU + model deps installed
```

### Building the Docker image
```bash
docker compose --profile gpu up --build -d
```

### Health check
```bash
curl http://localhost:8002/health
```

### Testing the MCP tools
```bash
# Inspect a CSV
echo '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"zer0fit_inspect","arguments":{"file_path":"data/iris.csv"}},"id":1}' | \
  curl -s -X POST http://localhost:8002/mcp -H "Content-Type: application/json" -d @-
```

## Disclaimer

Zer0Fit is research-use-only software. No warranties. The developer is not responsible for prediction accuracy. See [DISCLAIMER.md](DISCLAIMER.md).