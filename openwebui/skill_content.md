---
name: zerofit-workflow
description: "Automated workflow for ZeroFit forecasting and tabular prediction tools. Inspects attached files and selects correct columns."
---

# ZeroFit MCP Workflow

## Workflow when a user asks to forecast, classify, or analyze data

### Step 1: Find the file ID
Look in the user's message for `<file>` tags. Example: `<file type=file url=abc123... name=data.csv/>` — the file ID is `abc123...`.

### Step 2: Inspect the file
Call `zer0fit_inspect` with `file_path` set to the file ID from Step 1. This returns column names, row count, data types, and sample values.

### Step 3: Run the prediction
- **Classification**: Call `zer0fit_tabular` with `task_type: "classification"`, the `target_column`, and `file_path` (the file ID).
- **Regression**: Call `zer0fit_tabular` with `task_type: "regression"`, the `target_column`, and `file_path` (the file ID).
- **Forecasting**: Call `zer0fit_forecast` with `file_path`, `target_column`, and `horizon` (number of future steps).

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

**For forecasting** (`metrics` includes):
- `trend` — overall direction (increasing/decreasing)
- `forecast_range` — min to max forecast value
- `summary` — one-line plain English description of the forecast

When presenting results, include the key metrics so the user understands quality. Don't just say the predictions — say *how good* they were.

## Rules
- ALWAYS call `zer0fit_inspect` FIRST. Never skip this step.
- `file_path` accepts the file ID from `<file>` tags directly.
- The `metrics` object is pre-computed and reliable — use it instead of trying to calculate metrics yourself.
