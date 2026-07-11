# Zer0Fit MCP — Complete Deployment & Usage Guide

## What Is Zer0Fit?

Zer0Fit is a server that exposes two of Google's foundation models to AI assistants (like Open WebUI) via the Model Context Protocol (MCP):

| Model | What It Does | Best For |
|---|---|---|
| **TimesFM 2.5** (200M) | Forecasts future values in a time series | "What will sales look like next quarter?" |
| **TabFM v1.0.0** | Classifies or predicts values in a table | "Will this customer churn?" or "What will this house sell for?" |

Both models are **zero-shot** — they don't need to be trained on your data. You just give them examples and they make predictions immediately. No machine learning expertise required.

> ⚠️ **Use at Your Own Risk** — Zer0Fit is intended for research and educational purposes only. Predictions may be inaccurate. The developer is not responsible for decisions made based on model output. See the full [Disclaimer](../DISCLAIMER.md).

---

## How It Works

### The Chat-Attached File Flow (Recommended)

1. **Attach a CSV file** directly in the Open WebUI chat
2. Open WebUI injects a `<file type=file url=FILE_ID name=your.csv/>` tag into the message
3. The LLM calls `zer0fit_inspect` with the `FILE_ID` to discover:
   - Column names, data types, unique values
   - Row count and non-null counts
4. The LLM calls the appropriate prediction tool with the same `FILE_ID`:
   - `zer0fit_forecast` for time-series forecasting
   - `zer0fit_tabular` for classification or regression
5. Both tools return **pre-computed metrics** alongside raw predictions

**No `/app/data/` paths needed.** The server resolves Open WebUI file IDs automatically.

### The Upload Flow (Fallback)

For files not attached in chat, the LLM calls `zer0fit_upload_csv` with the file's base64 content, gets back a server-side path, and passes it to the prediction tools.

---

## System Requirements

### The Zer0Fit Server (GPU Host)
- **GPU**: NVIDIA GPU with at least 16GB VRAM (tested on DGX Spark GB10, RTX 3090, H100)
- **OS**: Ubuntu 24.04 (ARM64 or x86_64)
- **Docker**: 24.0+ with NVIDIA Container Toolkit
- **Docker Compose**: v2+

### The Client (Where Open WebUI Runs)
- Open WebUI 0.5+ (for MCP SSE transport) or 0.10+ (for Streamable HTTP)
- Network access to the Zer0Fit server's IP on port 8002

---

## Part 1: Deploying the Zer0Fit Server

### Step 1: Clone the Repository

Clone the repo onto your GPU server:

```bash
git clone https://github.com/porespellar/Zer0Fit.git
cd Zer0Fit
```

The project structure:
```
Zer0Fit/
├── data/                  # Put CSV files here (optional — use chat attach)
├── Dockerfile             # Multi-architecture Docker build
├── docker-compose.yml     # Docker Compose configuration
├── requirements.txt       # Python dependencies
├── model_manager.py       # VRAM management (auto-unloads idle models)
├── pipelines.py           # Data preprocessing (chunking, downsampling)
├── server.py              # MCP server (Streamable HTTP + SSE)
├── README.md              # Quick reference
├── ARCHITECTURE.md        # Technical design
├── DISCLAIMER.md          # No warranty, use-at-your-own-risk
├── CLAUDE.md             # Claude Code project context
├── AGENTS.md             # Codex CLI project instructions
├── .claude/skills/        # Claude Code skill for Zer0Fit tools
├── openwebui/
│   └── skill_content.md   # Open WebUI skill
└── install.sh             # One-command installer
```

### Step 2: Build and Launch

```bash
./install.sh
```

The installer detects your architecture, selects the correct CUDA base image and PyTorch wheels, builds the Docker image, and launches the server. First build takes 5-10 minutes.

### Step 3: Verify the Server Is Running

```bash
curl http://localhost:8002/health

# Expected response:
# {"status":"healthy","state":"IDLE","active_model":null}
```

### Step 4: (Optional) Pre-Load Sample Data

```bash
scp iris.csv your-server:Zer0Fit/data/
```

---

## How to Update Zer0Fit

When a new version of Zer0Fit is released, update your server with:

```bash
cd Zer0Fit

# 1. Pull the latest code from GitHub
git pull origin main

# 2. Stop the running container
docker compose --profile gpu down

# 3. Rebuild and restart (detects your architecture automatically)
docker compose --profile gpu up --build -d

# 4. Verify the update
curl http://localhost:8002/health
```

**If you have local changes** (e.g. configuration tweaks), stash them first:

```bash
git stash
git pull origin main
git stash pop
# Then proceed with steps 2-4 above
```

After updating, the Open WebUI connection and skill remain configured — no reconfiguration needed.

---

## Part 2: Connecting to Open WebUI

### Option A: Same Host (Recommended for Testing)

If Open WebUI runs in Docker on the same machine as Zer0Fit:

1. **Admin Settings → Integrations → Manage Tool Servers → Add Connection**
2. **URL**: `http://host.docker.internal:8002/mcp` (Streamable HTTP, preferred)
   - Fallback: `http://host.docker.internal:8002/sse`
3. **Type**: MCP / Streamable HTTP
4. Save

### Option B: Different Host

1. **Admin Settings → Integrations → Manage Tool Servers → Add Connection**
2. **URL**: `http://YOUR-SERVER-IP:8002/mcp`
3. **Type**: MCP / Streamable HTTP
4. Save

### Co-Located Deployment with Open WebUI

If Zer0Fit runs on the same Docker network as Open WebUI, add a named volume mount:

```yaml
# In docker-compose.yml, add this volume:
volumes:
  - open-webui:/app/webui_data:ro   # Optional — enables file ID resolution
```

This lets the Zer0Fit server resolve Open WebUI file attachment IDs directly, so users can attach files in chat without needing to upload them separately.

### Verify the Connection

After saving, you should see four tools registered:
- `zer0fit_inspect` — discover column names and data types
- `zer0fit_upload_csv` — upload data files from chat (fallback)
- `zer0fit_forecast` — time-series forecasting
- `zer0fit_tabular` — classification and regression

### Install the Zer0Fit Skill (Recommended)

1. **Workspace → Skills → Import Skill**
2. Upload `openwebui/skill_content.md` from the project directory
3. Attach the skill to your model in **Admin Settings → Models**

---

## Part 3: Using Zer0Fit — Examples

### Example 1: Classification (Iris Flower Species)

**What you do:**
1. Select the model with Zer0Fit tools + skill attached
2. Upload `iris.csv` as a chat attachment
3. Type: *"Classify the species."*

**What happens:**
1. The LLM extracts the file ID from the `<file>` tag
2. Calls `zer0fit_inspect` → discovers columns: `sepal_length`, `sepal_width`, `petal_length`, `petal_width`, `species`
3. Calls `zer0fit_tabular` with `task_type: "classification"` and `target_column: "species"`
4. TabFM processes 75 training rows + 75 test rows

**What you get back:**
```json
{
  "model": "tabfm-1.0.0-pytorch",
  "task_type": "classification",
  "n_train": 75,
  "n_test": 75,
  "metrics": {
    "accuracy": 0.9467,
    "n_correct": 71,
    "n_total": 75,
    "per_class": [
      {"class": "setosa", "precision": 1.0, "recall": 1.0, "f1_score": 1.0, "support": 21},
      {"class": "versicolor", "precision": 1.0, "recall": 0.8519, "f1_score": 0.92, "support": 27},
      {"class": "virginica", "precision": 0.871, "recall": 1.0, "f1_score": 0.9311, "support": 27}
    ],
    "confusion": {
      "setosa→setosa": 21,
      "versicolor→versicolor": 23,
      "versicolor→virginica": 4,
      "virginica→virginica": 27
    }
  }
}
```

The LLM summarizes: *"94.67% accuracy. Setosa is perfectly classified. Versicolor has 4 misclassified as virginica (92% F1). Virginica has 87% precision (some versicolor predicted as virginica but no false negatives)."*

### Example 2: Regression (California Housing)

**What you do:**
1. Attach `california_housing_small.csv`
2. Type: *"Run a regression on this data predicting MedHouseVal."*

**What happens:**
1. `zer0fit_inspect` discovers 9 columns including `MedHouseVal` (target)
2. `zer0fit_tabular` with `task_type: "regression"` and `target_column: "MedHouseVal"`
3. TabFM processes with 512 training rows + remainder as test rows

**What you get back:**
```json
{
  "model": "tabfm-1.0.0-pytorch",
  "task_type": "regression",
  "n_train": 512,
  "n_test": 488,
  "metrics": {
    "r_squared": 0.8820,
    "mae": 0.2042,
    "rmse": 0.3035,
    "mape_pct": 12.1,
    "prediction_range": [0.72, 4.98],
    "ground_truth_range": [0.69, 5.01]
  }
}
```

The LLM summarizes: *"R² of 0.88 — the model explains 88% of the variation in housing prices. Average error is $20,420 (MAE). Predictions closely track the actual range."*

### Example 3: Forecasting (Airline Passengers)

**What you do:**
1. Attach `airline_passengers.csv`
2. Type: *"Forecast the next 12 months."*

**What happens:**
1. `zer0fit_inspect` discovers `Month` (date) and `Passengers` (target) columns
2. `zer0fit_forecast` with `target_column: "Passengers"`, `horizon: 12`, `datetime_column: "Month"`
3. TimesFM returns point forecasts + quantile confidence intervals

**What you get back:**
```json
{
  "model": "timesfm-2.5-200m-pytorch",
  "horizon": 12,
  "point_forecast": [441.5, 406.1, 459.1, ...],
  "quantile_forecast": [[...], [...], ...],
  "series_length": 144
}
```

The LLM summarizes: *"The upward trend continues with a clear seasonal pattern — peak summer months and a winter dip. The forecast for month 12 is ~432 passengers, up from ~397 in the same period last year."*

---

## Part 4: Understanding the Tools

### `zer0fit_inspect`

**When to use:** Always call this first. It discovers column names, data types, unique value counts, and sample values — so the LLM can pick the correct `target_column` and decide between classification vs regression.

### `zer0fit_forecast`

**Best for:** Data with a time dimension where you want to predict the future.

**Limit:** `horizon` must be between 1 and 256 (matching TimesFM's compiled `max_horizon`). See [Limits & Configurability](../README.md#limits--configurability) to increase this.

**Tip:** If your data has a datetime column, pass it as `datetime_column` — it helps the model understand temporal spacing (e.g., gaps, irregular intervals).

### `zer0fit_tabular`

**Best for:** Any row-based prediction — classifying categories or predicting continuous numbers.

**Limit:** `max_chunks` is capped at 10 (10,000 rows max per request) to prevent GPU OOM and oversized responses. Set `max_chunks=0` for the maximum. See [Limits & Configurability](../README.md#limits--configurability) to increase this.

**Two modes:**
- `task_type: "classification"` → predicts labels, returns per-class metrics
- `task_type: "regression"` → predicts numbers, returns R²/MAE/RMSE

---

## Part 5: Tips for Best Results

### CSV Formatting
- Include a **header row** with column names
- For time-series: include a **datetime column** (e.g., "2025-01-01")
- For tabular: mix numeric and categorical columns freely
- No encoding, scaling, or missing-value imputation required

### Getting Better Accuracy
- **More rows = better predictions** (up to 512 in-context rows for TabFM)
- **For classification**: ensure all classes have multiple examples
- **Be specific in your prompt**: "Classify the species" vs "Analyze this data"

### When to Use Zer0Fit vs Traditional ML
- **Use Zer0Fit** when you want fast predictions without training or ML expertise
- **Use XGBoost/sklearn** when you need maximum accuracy and can afford to tune

---

## Part 6: Other Client Integrations

Zer0Fit's MCP server works with any client that supports standard MCP SSE or Streamable HTTP transport.

### Claude Code

```bash
claude mcp add --transport sse zer0fit http://YOUR-SERVER-IP:8002/sse
```

Or add to `~/.claude/settings.json`:
```json
{
  "mcpServers": {
    "zer0fit": {
      "transport": "sse",
      "url": "http://YOUR-SERVER-IP:8002/sse"
    }
  }
}
```

### Codex CLI

```bash
codex mcp add zer0fit --url http://YOUR-SERVER-IP:8002/mcp
```

Then use with `codex exec`:
```bash
codex exec "Use zer0fit to inspect the data and classify the species."
```

### OpenCode

Not supported natively — OpenCode's MCP support is limited to stdio transport only and does not accept remote SSE/HTTP URLs.

---

## Part 7: Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| "Connection refused" | Server not running or port blocked | Check `curl http://localhost:8002/health` |
| Tools not showing in Open WebUI | Wrong URL or transport type | Try `http://host.docker.internal:8002/mcp` for Streamable HTTP |
| "Could not resolve file_path" | File ID not found on server | Server needs Open WebUI volume mount for file ID resolution (see Part 2) |
| Poor accuracy | Noisy data or weak target-feature relationship | Try a different target or add more columns |
| Prediction takes long | First run downloads model weights | Wait ~60s for model load; subsequent calls are faster |
| Not enough rows | CSV too small for train/test split | Minimum ~10 rows, recommended 100+ |
| "horizon must be an integer between 1 and 256" | Requested forecast beyond TimesFM's compiled limit | Use a smaller horizon, or increase `max_horizon` in both `server.py` and `model_manager.py` |
| "max_chunks capped" / large request fails | `max_chunks` exceeds the 10-chunk limit | Reduce to 10 or fewer, or increase `MAX_CHUNKS_LIMIT` in `server.py` |

### VRAM Management
- Models auto-unload after 5 minutes of inactivity (`ZER0FIT_VRAM_TTL`)
- Only one model (TimesFM or TabFM) loaded at a time
- Switching models triggers auto-eviction
