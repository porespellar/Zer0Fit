---
name: zerofit-workflow
description: "Automated workflow for Zer0Fit forecasting and tabular prediction tools. Inspects attached files and selects correct columns."
---

# Zer0Fit MCP Workflow

## Workflow when a user asks to forecast, classify, or analyze data

### Step 1: Get the file content
When the user attaches a file in the chat, the file content is available to you directly.
If you can see the raw CSV/table content in the conversation context, use the
`file_data` parameter instead of `file_path` — this avoids needing a shared
volume mount between Open WebUI and the Zer0Fit server.

If the file ID is available but not the full file content, look in the user's
message for `<file>` tags. Example: `<file type=file url=abc123... name=data.csv/>`
— the file ID is `abc123...`.

### Step 2: Inspect the file
Call `zer0fit_inspect` with the file content or ID:

- **Best (no volume needed):** `file_data="column1,column2\n1.0,2.0\n..."` — pass
  the raw CSV text you see in the conversation context. Optionally include
  `file_name="data.csv"` for display.
- **Fallback (needs volume):** `file_path="abc123..."` — pass the file ID from
  the `<file>` tags. Only works if the Open WebUI uploads volume is mounted.

This returns column names, row count, data types, and sample values.

### Step 3: Run the prediction
- **Classification**: Call `zer0fit_tabular` with `task_type: "classification"`,
  `target_column`, and either `file_data` or `file_path`.
- **Regression**: Call `zer0fit_tabular` with `task_type: "regression"`,
  `target_column`, and either `file_data` or `file_path`.
- **Forecasting**: Call `zer0fit_forecast` with either `file_data` or `file_path`,
  `target_column`, and `horizon` (number of future steps).

### Step 4: Interpret the results
The tool returns a `metrics` object with pre-computed summary statistics. Use these directly:

**For classification** (`metrics` includes):
- `accuracy` — overall percent correct (e.g. 0.9467 = 94.67%)
- `n_correct` / `n_total` — raw counts
- `per_class` — array of per-class metrics: `class`, `precision`, `recall`, `f1_score`, `support`
- `confusion` — easy-to-read misclassification counts

**For regression** (`metrics` includes):
- `r_squared` — how well the model explains variance (1.0 = perfect, 0.0 = baseline)
- `mae` — mean absolute error (in target units)
- `rmse` — root mean squared error (in target units)
- `mape_pct` — mean absolute percentage error
- `prediction_range` / `ground_truth_range` — min/max of predicted vs actual values

**For forecasting** (no metrics block — the forecast result contains):
- `point_forecast` — predicted future values (one per time step)
- `quantile_forecast` — confidence intervals (10th-90th percentile)
- `series_length` — number of data points used (after any downsampling)

When presenting results, include the key metrics so the user understands quality. Don't just say the predictions — say *how good* they were (for classification and regression). For forecasting, describe the trend and pattern.

## Rules
- ALWAYS call `zer0fit_inspect` FIRST. Never skip this step.
- Use `file_data` (raw CSV text) when the file content is visible in the conversation.
  Use `file_path` (file ID) only when the content is not directly accessible.
- The `metrics` object is pre-computed and reliable — use it instead of trying to calculate metrics yourself.
