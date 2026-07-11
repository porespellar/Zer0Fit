"""
Zer0Fit pipelines.py — the OOM-Safe Data Streamers.

Responsibilities:
  * Temporal downsampler for TimesFM: if a univariate time series exceeds the
    1,024 context window, aggregate it to a lower frequency so the model
    never receives more tokens than its context window.
  * Tabular ensemble batcher for TabFM: slice arbitrarily large CSVs into
    1,000-row blocks so that in-context learning never OOMs the GPU.
  * Provide thin convenience wrappers that turn a CSV file path + column name
    into the numpy / pandas structures the two models expect.
"""

from __future__ import annotations

import logging
import math
import os
from typing import List, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger("zer0fit.pipelines")

# TimesFM 2.5 supports up to 16k context, but the compiled ForecastConfig in
# model_manager uses max_context=1024 (matching the build spec). We respect
# that ceiling here.
TIMESFM_MAX_CONTEXT = 1024
TABFM_CHUNK_SIZE = 1000
TABFM_IN_CONTEXT_SIZE = 512

# Supported file extensions for tabular data.
SUPPORTED_EXTENSIONS = {".csv", ".xls", ".xlsx", ".json", ".jsonl"}


def _read_tabular_file(file_path: str) -> pd.DataFrame:
    """Read a CSV, Excel (.xls/.xlsx), or JSON file into a pandas DataFrame.

    The format is detected by the file extension.
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".csv":
        return pd.read_csv(file_path)
    elif ext in (".xls", ".xlsx"):
        # openpyxl for .xlsx, xlrd for legacy .xls
        engine = "xlrd" if ext == ".xls" else None
        return pd.read_excel(file_path, engine=engine)
    elif ext == ".json":
        # JSON can be array of objects or nested — try records first
        try:
            return pd.read_json(file_path, orient="records")
        except ValueError:
            return pd.read_json(file_path)
    elif ext == ".jsonl":
        # JSON Lines: one JSON object per line
        return pd.read_json(file_path, lines=True)
    else:
        raise ValueError(
            f"Unsupported file format: {ext!r}. "
            f"Supported formats: {SUPPORTED_EXTENSIONS}"
        )


# ---------------------------------------------------------------------------
# TimesFM pipeline
# ---------------------------------------------------------------------------

def load_time_series(
    file_path: str,
    target_column: str,
    datetime_column: str | None = None,
) -> pd.Series:
    """Load a CSV or Excel file and return the target column as a sorted
    pandas Series."""
    df = _read_tabular_file(file_path)
    if target_column not in df.columns:
        raise ValueError(
            f"target_column {target_column!r} not found in {file_path}; "
            f"columns: {list(df.columns)}"
        )
    series = df[target_column].astype(float)
    if datetime_column:
        if datetime_column in df.columns:
            series.index = pd.to_datetime(df[datetime_column])
            series = series.sort_index()
        else:
            logger.warning(
                "datetime_column %r not found in columns %s — "
                "proceeding without temporal ordering",
                datetime_column, list(df.columns),
            )
    return series


def downsample_for_timesfm(series: pd.Series) -> Tuple[np.ndarray, str]:
    """Return a 1-D numpy array suitable for TimesFM, downsampling if the
    series exceeds the 1,024-token context window.

    Returns a tuple of (array, note) where *note* describes any downsampling
    that was applied (empty string if none).
    """
    arr = series.dropna().to_numpy(dtype=np.float32)
    note = ""
    if len(arr) <= TIMESFM_MAX_CONTEXT:
        return arr, note

    # Try pandas-frequency downsampling if we have a DatetimeIndex.
    if isinstance(series.index, pd.DatetimeIndex):
        # Pick a coarser frequency roughly proportional to the overshoot.
        overshoot = len(arr) / TIMESFM_MAX_CONTEXT
        # candidate frequencies from fine to coarse
        candidates = ["min", "5min", "10min", "H", "D", "W"]
        rule = candidates[min(len(candidates) - 1, int(math.log2(overshoot)) + 1)]
        resampled = series.dropna().resample(rule).mean()
        arr = resampled.dropna().to_numpy(dtype=np.float32)
        note = f"downsampled to {rule} mean (n={len(arr)})"
        if len(arr) <= TIMESFM_MAX_CONTEXT:
            logger.info("Downsampled series to %d points (%s).", len(arr), note)
            return arr, note

    # Fallback: evenly-spaced stride sampling.
    stride = math.ceil(len(arr) / TIMESFM_MAX_CONTEXT)
    arr = arr[::stride]
    note = f"stride-sampled every {stride} rows (n={len(arr)})"
    logger.info("Downsampled series to %d points (%s).", len(arr), note)
    return arr, note


def make_timesfm_forecast_inputs(
    file_path: str,
    target_column: str,
    datetime_column: str | None = None,
) -> List[np.ndarray]:
    """Convenience: load + downsample → list with a single numpy array ready
    for TimesFM `model.forecast(inputs=...)`."""
    series = load_time_series(file_path, target_column, datetime_column)
    arr, _note = downsample_for_timesfm(series)
    return [arr]


# ---------------------------------------------------------------------------
# TabFM pipeline
# ---------------------------------------------------------------------------

def load_tabular(
    file_path: str,
    target_column: str,
) -> pd.DataFrame:
    """Load a CSV, Excel, or JSON file and return the full DataFrame."""
    df = _read_tabular_file(file_path)
    if target_column not in df.columns:
        raise ValueError(
            f"target_column {target_column!r} not found in {file_path}; "
            f"columns: {list(df.columns)}"
        )
    return df


def chunk_tabular(
    df: pd.DataFrame,
    target_column: str,
    chunk_size: int = TABFM_CHUNK_SIZE,
    in_context_size: int = TABFM_IN_CONTEXT_SIZE,
    random_state: int = 42,
) -> List[Tuple[pd.DataFrame, np.ndarray, pd.DataFrame, np.ndarray]]:
    """Split a DataFrame into (X_train, y_train, X_test, y_test) chunks.

    TabFM is a zero-shot in-context learner — it does NOT train on the
    data.  The `fit()` method only prepares feature encoders; at inference
    time the model reads the training rows as *context* and predicts the
    test rows in a single forward pass.

    CRITICAL: The data is **shuffled** before splitting so that the
    in-context window contains a representative sample of all classes /
    target values.  Without shuffling, a sorted CSV (e.g. Iris grouped by
    species) would put only one class in the context, making zero-shot
    prediction impossible.

    The chunking strategy:
      1. Shuffle the full DataFrame (reproducible via random_state).
      2. Read in 1,000-row blocks (memory-friendly for large files).
      3. Use the first `in_context_size` rows of each block as context.
      4. Predict the remaining rows in the block as test rows.
    """
    # Shuffle to ensure class diversity in the context window.
    df = df.sample(frac=1, random_state=random_state).reset_index(drop=True)

    chunks: List[Tuple[pd.DataFrame, np.ndarray, pd.DataFrame, np.ndarray]] = []
    n = len(df)
    for start in range(0, n, chunk_size):
        block = df.iloc[start : start + chunk_size]
        # Cap context size to half the block so we always have test rows.
        effective_ctx = min(in_context_size, len(block) // 2)
        if len(block) < effective_ctx + 4:  # need context + some test rows
            continue
        train = block.iloc[:effective_ctx]
        test = block.iloc[effective_ctx:]
        X_train = train.drop(columns=[target_column])
        y_train = train[target_column].to_numpy()
        X_test = test.drop(columns=[target_column])
        y_test = test[target_column].to_numpy()
        chunks.append((X_train, y_train, X_test, y_test))
    return chunks