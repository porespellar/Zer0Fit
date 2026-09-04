# Zer0Fit MCP Workflow — Using Zer0Fit Forecasting & Tabular Tools

## When to use this skill

Use this skill when a user asks to forecast, classify, predict, or analyze tabular or time-series data and a Zer0Fit MCP server is connected.

## Prerequisites

Zer0Fit MCP server must be connected to Claude Code:

```bash
# Add the Zer0Fit MCP server (SSE transport)
claude mcp add --transport sse zerofit http://YOUR-SERVER-IP:8002/sse

# Or via Streamable HTTP (preferred for newer setups)
claude mcp add zerofit --url http://YOUR-SERVER-IP:8002/mcp
```

Verify connection:
```bash
claude mcp list
# Should show "zerofit" with 4 tools
```

## Available MCP Tools

| Tool | Purpose |
|---|---|
| `zer0fit_inspect` | Discover column names, data types, row count from a file |
| `zer0fit_upload_csv` | Upload a data file (CSV, XLS, XLSX, JSON, JSONL) via base64 |
| `zer0fit_forecast` | Zero-shot time-series forecasting via TimesFM 3.0 |
| `zer0fit_tabular` | Zero-shot classification or regression via TabFM v1.0.0 |

## Workflow

### Step 1: Get the file

If the user provides a file path directly, you can use it with `file_path`.
If the file was shared in the conversation (e.g. the user pasted CSV text or shared a file), use `file_data`:

```
zer0fit_inspect(file_data="column1,column2\nvalue1,value2\n...")
```

If the user has a local file on disk that isn't accessible to the Zer0Fit server, upload it:

```
zer0fit_upload_csv(filename="data.csv", content_base64=<base64-encoded file bytes>)
```

To base64-encode a local file:
```bash
base64 -i data.csv
```

### Step 2: Inspect the file

ALWAYS call `zer0fit_inspect` first to discover columns and data types:

```
zer0fit_inspect(file_path="data/iris.csv")       # for files on the server
zer0fit_inspect(file_data="col1,col2\n1,2\n3,4") # for inline/shared data
```

Returns: column names, dtypes, non-null counts, unique counts, sample values.

### Step 3: Run the prediction

Based on the user's request:

- **Classification**: `zer0fit_tabular(file_path="...", target_column, task_type="classification")` or `zer0fit_tabular(file_data="...", target_column, task_type="classification")`
- **Regression**: `zer0fit_tabular(file_path="...", target_column, task_type="regression")` or `zer0fit_tabular(file_data="...", target_column, task_type="regression")`
- **Forecasting**: `zer0fit_forecast(file_path="...", target_column, horizon=N, datetime_column="...")` or `zer0fit_forecast(file_data="...", target_column, horizon=N, datetime_column="...")`

### Step 4: Interpret results

The tools return pre-computed metrics. Use these directly:

**Classification** (`metrics` block):
- `accuracy` — overall percent correct (0–1)
- `per_class` — per-class precision, recall, F1, support
- `confusion` — misclassification counts

**Regression** (`metrics` block):
- `r_squared` — coefficient of determination (1.0 = perfect)
- `mae` — mean absolute error (in target units)
- `rmse` — root mean squared error
- `mape_pct` — mean absolute percentage error

**Forecasting** (no metrics block):
- `point_forecast` — predicted future values
- `quantile_forecast` — confidence intervals (10th–90th percentile)
- `series_length` — number of data points used

## Limits

| Parameter | Range | Notes |
|---|---|---|
| `horizon` | 1–256 | Zer0Fit service safety cap; TimesFM 3.0 uses evaluator-managed patch-rounded decode windows |
| `max_chunks` | 0–10 | 0 = maximum (10). Each chunk = 1,000 rows. |
| `target_column` | must exist | Discovered via `zer0fit_inspect` |
| File size | unlimited on disk | But only 10K rows processed per tabular request |

## Rules

1. ALWAYS call `zer0fit_inspect` FIRST — never skip this step
2. Never guess column names — always inspect first
3. Use `file_data` (inline CSV text) when the file content is available in the conversation; use `file_path` only when a file is already on the server
4. Include the pre-computed metrics when presenting results
5. For forecasting, describe the trend and pattern, not just numbers
6. For classification/regression, say *how good* the predictions were (accuracy, R², etc.)
7. If the user asks for more than 10 chunks, warn them about the limit and suggest processing in batches