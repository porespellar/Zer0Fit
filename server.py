"""
Zer0Fit server.py — the Enterprise SSE-MCP Bridge.

Exposes four MCP tools to upstream LLM agents (e.g. Open WebUI):

  * zer0fit_inspect(file_path)
  * zer0fit_upload_csv(filename, content_base64)
  * zer0fit_forecast(file_path, target_column, horizon, datetime_column?)
  * zer0fit_tabular(file_path, target_column, task_type, max_chunks?)

Communication uses MCP SSE + Streamable HTTP over a Starlette/FastAPI
application, strictly bound to 0.0.0.0:8002.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
import base64
import glob
from typing import Any

import numpy as np
import pandas as pd
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Mount, Route
from starlette.responses import JSONResponse

from model_manager import ModelManager, ModelType, manager as _mgr
import pipelines

logging.basicConfig(
    level=os.environ.get("ZER0FIT_LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
logger = logging.getLogger("zer0fit.server")

# Directory for uploaded files (auto-cleaned on TTL).
UPLOAD_DIR = os.environ.get("ZER0FIT_UPLOAD_DIR", "/app/data/uploads")
UPLOAD_TTL_HOURS = int(os.environ.get("ZER0FIT_UPLOAD_TTL_HOURS", "6"))


def _cleanup_uploads() -> int:
    """Delete uploaded files older than UPLOAD_TTL_HOURS.

    Called on every upload to keep the directory from growing unbounded.
    Returns the number of files deleted.
    """
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    cutoff = time.time() - (UPLOAD_TTL_HOURS * 3600)
    upload_real = os.path.realpath(UPLOAD_DIR)
    deleted = 0
    for path in glob.glob(os.path.join(UPLOAD_DIR, "*")):
        try:
            # Resolve symlinks and verify the real path stays within
            # UPLOAD_DIR — prevents symlink-following attacks that could
            # delete arbitrary files outside the upload directory.
            real = os.path.realpath(path)
            if not real.startswith(upload_real + os.sep):
                logger.warning("Skipping cleanup of symlink escape: %s -> %s", path, real)
                continue
            if os.path.getmtime(real) < cutoff:
                os.remove(real)
                deleted += 1
        except OSError:
            pass
    if deleted:
        logger.info("Cleaned up %d expired upload(s) (TTL=%dh).", deleted, UPLOAD_TTL_HOURS)
    return deleted


app_server = Server("zer0fit-mcp")


def _json_safe(v):
    """Convert a numpy/pandas scalar to a JSON-serializable Python value."""
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, pd.Timestamp):
        return str(v)
    if pd.isna(v):
        return None
    return v


# ---------------------------------------------------------------------------
# MCP tool handlers
# ---------------------------------------------------------------------------

@app_server.list_tools()
async def list_tools() -> Any:  # noqa: ANN201
    from mcp.types import Tool
    return [
        Tool(
            name="zer0fit_upload_csv",
            description=(
                "Upload a data file to the Zer0Fit server for processing. "
                "Supports CSV, XLS, XLSX, JSON, and JSONL formats. "
                "The content_base64 parameter must contain the ACTUAL FILE BYTES "
                "encoded as base64 (e.g. base64.b64encode(open(path,'rb').read())). "
                "Do NOT pass a file ID, URL, UUID, or filename as content_base64. "
                "NOTE: If the file was attached in Open WebUI, you can pass the "
                "file ID directly as file_path to zer0fit_forecast or zer0fit_tabular "
                "— no upload needed. This tool is only for files not already "
                "available as attachments. Uploaded files are auto-deleted after 6 hours."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Name for the file on the server (e.g. 'sales.csv', 'data.xlsx', 'records.json'). Must end in .csv, .xls, .xlsx, .json, or .jsonl.",
                    },
                    "content_base64": {
                        "type": "string",
                        "description": "Base64-encoded content of the file.",
                    },
                },
                "required": ["filename", "content_base64"],
            },
        ),
        Tool(
            name="zer0fit_inspect",
            description=(
                "Inspect a data file to discover its column names, data types, "
                "and row count. Use this BEFORE calling zer0fit_forecast or "
                "zer0fit_tabular to find the correct target_column name. "
                "Accepts the same file_path formats as the other tools "
                "(Open WebUI file ID, upload path, or /app/data filename)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the data file. Accepts: (a) an Open WebUI file attachment ID (e.g. 'c9677920-a59f-4c4f-...'), (b) a path returned by zer0fit_upload_csv, or (c) a filename in /app/data/. When a user attaches a file in the chat, use the file ID from the attachment as file_path.",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="zer0fit_forecast",
            description=(
                "Zero-shot time-series forecasting via Google TimesFM 2.5. "
                "Pass a file path (CSV, XLS, XLSX, JSON, or JSONL), the target "
                "numeric column to forecast, and the forecast horizon (number "
                "of future points). Returns a JSON object with point forecasts "
                "and quantile forecasts."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the data file. Accepts: (a) an Open WebUI file attachment ID (e.g. 'c9677920-a59f-4c4f-...'), (b) a path returned by zer0fit_upload_csv, or (c) a filename in /app/data/. When a user attaches a file in the chat, use the file ID from the attachment as file_path — the server will resolve it automatically.",
                    },
                    "target_column": {
                        "type": "string",
                        "description": "Name of the numeric column to forecast.",
                    },
                    "horizon": {
                        "type": "integer",
                        "description": "Number of future time steps to forecast.",
                        "default": 12,
                    },
                    "datetime_column": {
                        "type": "string",
                        "description": "Optional datetime column for temporal downsampling.",
                    },
                },
                "required": ["file_path", "target_column", "horizon"],
            },
        ),
        Tool(
            name="zer0fit_tabular",
            description=(
                "Zero-shot tabular classification or regression via Google "
                "TabFM v1.0.0. Pass a file path (CSV, XLS, XLSX, JSON, or "
                "JSONL), the target column, and task_type ('classification' "
                "or 'regression'). Returns predictions and (for "
                "classification) class probabilities."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the data file. Accepts: (a) an Open WebUI file attachment ID (e.g. 'c9677920-a59f-4c4f-...'), (b) a path returned by zer0fit_upload_csv, or (c) a filename in /app/data/. When a user attaches a file in the chat, use the file ID from the attachment as file_path.",
                    },
                    "target_column": {
                        "type": "string",
                        "description": "Name of the target column to predict.",
                    },
                    "task_type": {
                        "type": "string",
                        "enum": ["classification", "regression"],
                        "description": "Type of prediction task.",
                    },
                    "max_chunks": {
                        "type": "integer",
                        "description": "Max number of 1,000-row chunks to process (default 1, max 10, set to 0 for maximum).",
                        "default": 1,
                    },
                },
                "required": ["file_path", "target_column", "task_type"],
            },
        ),
    ]


def _resolve_path(file_path: str) -> str:
    """Resolve a file path to an actual file on disk.

    Security: only resolves exact file names, never directory listings.
    Checks (in order):
      1. Absolute path — if it exists and is a file
      2. Open WebUI uploads — match by file ID prefix (e.g. c9677920-...)
      3. ZeroFit uploads directory (for files uploaded via zer0fit_upload_csv)
      4. /app/data/ (for pre-placed files)
    The caller must provide the exact filename or full path — no globbing.
    """
    # Absolute path — only if it exists, is a file, and is within an
    # approved data directory.  This prevents path-traversal attacks that
    # could read arbitrary files (e.g. /etc/passwd, /app/.env) via
    # zer0fit_inspect.
    ALLOWED_ABS_DIRS = (
        "/app/data/",
        "/app/webui_data/",
        os.path.abspath(UPLOAD_DIR) + "/",
    )
    if os.path.isabs(file_path):
        real = os.path.realpath(file_path)
        if not any(
            real == d.rstrip("/") or real.startswith(d) for d in ALLOWED_ABS_DIRS
        ):
            raise ValueError(
                "Access to paths outside of approved data directories "
                f"({', '.join(ALLOWED_ABS_DIRS)}) is prohibited."
            )
        if os.path.isfile(real):
            return real
        raise FileNotFoundError(f"File not found: {file_path}")

    basename = os.path.basename(file_path)
    if not basename:
        raise FileNotFoundError(f"Invalid file path: {file_path!r}")

    # Open WebUI uploads: files are stored as {file_id}_{original_filename}
    # The LLM often passes just the file_id (e.g. "c9677920-...") which is the
    # Open WebUI attachment ID. We match by prefix in the webui uploads dir.
    # Security: require a minimum prefix length (UUID-sized) to prevent IDOR —
    # a short prefix like "0" would match any file starting with "0".
    WEBUI_UPLOAD_DIR = os.environ.get(
        "ZER0FIT_WEBUI_DIR", "/app/webui_data/uploads"
    )
    if os.path.isdir(WEBUI_UPLOAD_DIR):
        webui_real = os.path.realpath(WEBUI_UPLOAD_DIR)
        for fname in os.listdir(WEBUI_UPLOAD_DIR):
            if len(basename) >= 8 and fname.startswith(basename):
                candidate = os.path.join(WEBUI_UPLOAD_DIR, fname)
                # Resolve symlinks and verify the real path stays within
                # the WebUI upload directory (prevent symlink escape).
                candidate_real = os.path.realpath(candidate)
                if not candidate_real.startswith(webui_real + os.sep) \
                        and candidate_real != webui_real:
                    continue
                if os.path.isfile(candidate):
                    return candidate

    # Check ZeroFit uploads directory (exact filename match only)
    uploads_candidate = os.path.join(UPLOAD_DIR, basename)
    if os.path.isfile(uploads_candidate):
        return uploads_candidate

    # Check /app/data (exact filename match only)
    data_candidate = os.path.join("/app/data", basename)
    if os.path.isfile(data_candidate):
        return data_candidate

    raise FileNotFoundError(f"Could not resolve file_path: {file_path}")


@app_server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> Any:  # noqa: ANN201
    from mcp.types import TextContent

    logger.info("call_tool name=%s args=%s", name, arguments)

    def _error(msg: str, **extra) -> list:
        """Return a JSON error as TextContent so the LLM sees a useful
        message instead of the MCP session crashing silently."""
        payload = {"error": msg, **extra}
        logger.warning("Tool %s error: %s %s", name, msg, extra)
        return [TextContent(type="text", text=json.dumps(payload, indent=2))]

    try:

        if name == "zer0fit_upload_csv":
            filename = arguments["filename"]
            content_b64 = arguments["content_base64"]

            # Sanitise filename — strip any path components
            safe_name = os.path.basename(filename)

            # Validate and normalise extension
            allowed_extensions = {".csv", ".xls", ".xlsx", ".json", ".jsonl"}
            ext = os.path.splitext(safe_name)[1].lower()
            if ext not in allowed_extensions:
                # Default to .csv if no recognised extension
                safe_name = safe_name + ".csv"
                ext = ".csv"

            # Security: generate a random UUID-based filename so users cannot
            # guess or browse other users' uploads. The original name is
            # preserved in the response for the LLM's reference, but the
            # actual file on disk uses the UUID.
            file_id = uuid.uuid4().hex
            stored_name = f"{file_id}_{safe_name}"

            # Clean up old uploads before writing the new one (offloaded to
            # avoid blocking the async event loop with filesystem I/O).
            await asyncio.to_thread(_cleanup_uploads)
            os.makedirs(UPLOAD_DIR, exist_ok=True)

            # Security: enforce max upload size to prevent OOM/disk exhaustion.
            # Base64 is ~33% larger than the raw file; 50MB raw ≈ 67MB base64.
            MAX_UPLOAD_BYTES = int(os.environ.get("ZER0FIT_MAX_UPLOAD_MB", "50")) * 1024 * 1024
            if len(content_b64) > MAX_UPLOAD_BYTES * 1.34:
                return _error(
                    f"Upload too large. Base64 content is {len(content_b64) // (1024*1024)}MB, "
                    f"exceeds the {MAX_UPLOAD_BYTES // (1024*1024)}MB limit. "
                    f"Set ZER0FIT_MAX_UPLOAD_MB to increase.",
                    filename=safe_name,
                )

            # Decode base64 and validate
            try:
                raw = base64.b64decode(content_b64, validate=True)
            except Exception as exc:
                return _error(
                    f"Invalid base64 content: {exc}. "
                    f"The content_base64 parameter must be the actual file "
                    f"contents encoded as base64, NOT a file ID, URL, or UUID. "
                    f"Encode the file bytes with base64.b64encode(file_bytes).",
                    filename=safe_name,
                )

            if len(raw) < 10:
                return _error(
                    f"Decoded content is only {len(raw)} bytes — too small to "
                    f"be a valid data file. The content_base64 parameter must "
                    f"contain the actual file contents encoded as base64, "
                    f"NOT a file ID, URL, or UUID.",
                    filename=safe_name,
                )

            # Write the file
            file_path = os.path.join(UPLOAD_DIR, stored_name)
            with open(file_path, "wb") as f:
                f.write(raw)

            # Validate the file can actually be parsed by pandas.
            # Read only the first 5 rows to avoid OOM on large uploads
            # (CSV and Excel only — JSON formats don't support nrows).
            try:
                if ext in (".csv", ".xls", ".xlsx"):
                    test_df = pipelines._read_tabular_file(file_path, nrows=5)
                else:
                    # JSON / JSONL — must read in full (typically small)
                    test_df = pipelines._read_tabular_file(file_path)
            except Exception as exc:
                os.remove(file_path)
                return _error(
                    f"File was decoded and written but could not be parsed as "
                    f"a valid {ext} file: {exc}. "
                    f"This usually means the content_base64 parameter did not "
                    f"contain the actual file contents.",
                    filename=safe_name,
                )

            size_kb = os.path.getsize(file_path) / 1024
            # test_df may be a partial read (nrows=5) — only use it for
            # column validation, not as an accurate row count.
            n_cols = len(test_df.columns)
            col_names = list(test_df.columns)
            logger.info("Uploaded %s as %s (%.1f KB, %d cols) → %s",
                        safe_name, stored_name, size_kb,
                        n_cols, file_path)

            result = {
                "file_path": file_path,
                "original_filename": safe_name,
                "stored_filename": stored_name,
                "size_kb": round(size_kb, 1),
                "n_columns": n_cols,
                "columns": col_names,
                "message": (
                    f"File uploaded successfully to {file_path}. "
                    f"Use this exact path as file_path in zer0fit_forecast or "
                    f"zer0fit_tabular. The file will be auto-deleted after "
                    f"{UPLOAD_TTL_HOURS} hours."
                ),
            }
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "zer0fit_inspect":
            file_path = _resolve_path(arguments["file_path"])
            # Read only the first 10,000 rows to prevent OOM on large files.
            # Column metadata (names, dtypes, sample values) is accurate
            # from a partial read; n_rows reflects the capped count.
            df_ext = os.path.splitext(file_path)[1].lower()
            if df_ext in (".csv", ".xls", ".xlsx"):
                df = pipelines._read_tabular_file(file_path, nrows=10000)
            else:
                df = pipelines._read_tabular_file(file_path)
            result = {
                "file_path": file_path,
                "filename": os.path.basename(file_path),
                "n_rows": len(df),
                "n_columns": len(df.columns),
                "columns": [
                    {
                        "name": col,
                        "dtype": str(df[col].dtype),
                        "n_non_null": int(df[col].notna().sum()),
                        "n_unique": int(df[col].nunique()),
                        "sample_values": [
                            _json_safe(v) for v in df[col].dropna().head(3).tolist()
                        ],
                    }
                    for col in df.columns
                ],
            }
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "zer0fit_forecast":
            file_path = _resolve_path(arguments["file_path"])
            target_column = arguments["target_column"]
            horizon = int(arguments["horizon"])
            if horizon <= 0 or horizon > 256:
                raise ValueError("horizon must be an integer between 1 and 256 (got %d)" % horizon)
            datetime_column = arguments.get("datetime_column")

            inputs = pipelines.make_timesfm_forecast_inputs(
                file_path, target_column, datetime_column
            )
            tfm = await _mgr.get_model(ModelType.TIMESFM)
            point_forecast, quantile_forecast = tfm.forecast(
                horizon=horizon, inputs=inputs
            )
            result = {
                "model": "timesfm-2.5-200m-pytorch",
                "horizon": horizon,
                "point_forecast": point_forecast.tolist(),
                "quantile_forecast": quantile_forecast.tolist(),
                "series_length": len(inputs[0]),
            }
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "zer0fit_tabular":
            file_path = _resolve_path(arguments["file_path"])
            target_column = arguments["target_column"]
            task_type = arguments["task_type"]
            # How many chunks to predict (default: 1).  Set to 0 or -1 for all.
            # Cap at 10 to prevent OOM and massive JSON responses on large files.
            MAX_CHUNKS_LIMIT = 10
            max_chunks_raw = arguments.get("max_chunks")
            max_chunks = int(max_chunks_raw) if max_chunks_raw is not None else 1
            if max_chunks <= 0:
                max_chunks = MAX_CHUNKS_LIMIT
            else:
                max_chunks = min(max_chunks, MAX_CHUNKS_LIMIT)

            estimator = await _mgr.get_tabfm_estimator(task_type)

            df = pipelines.load_tabular(file_path, target_column)
            chunks = pipelines.chunk_tabular(
                df, target_column, chunk_size=1000,
                in_context_size=pipelines.TABFM_IN_CONTEXT_SIZE
            )
            if not chunks:
                min_rows = pipelines.TABFM_IN_CONTEXT_SIZE + 4
                return _error(
                    f"Not enough rows in the file to produce a prediction chunk. "
                    f"Need at least {min_rows} rows ({pipelines.TABFM_IN_CONTEXT_SIZE} "
                    f"in-context + 4 test rows). Try a larger file."
                )

            # Determine how many chunks to process.
            if max_chunks and max_chunks > 0:
                chunks = chunks[:max_chunks]

            all_preds: list = []
            all_truth: list = []
            total_train = 0
            total_test = 0

            for X_train, y_train, X_test, y_test in chunks:
                estimator.fit(X_train, y_train)
                # Predict in small batches to avoid OOM / timeouts on the GPU.
                PRED_BATCH = 128
                preds_list: list = []
                for i in range(0, len(X_test), PRED_BATCH):
                    X_batch = X_test.iloc[i : i + PRED_BATCH]
                    batch_preds = estimator.predict(X_batch)
                    preds_list.extend(np.asarray(batch_preds).tolist())
                all_preds.extend(preds_list)
                all_truth.extend(np.asarray(y_test).tolist())
                total_train += len(X_train)
                total_test += len(X_test)

            result: dict[str, Any] = {
                "model": "tabfm-1.0.0-pytorch",
                "task_type": task_type,
                "predictions": all_preds,
                "ground_truth": all_truth,
                "n_train": total_train,
                "n_test": total_test,
                "n_chunks": len(chunks),
                "in_context_size": pipelines.TABFM_IN_CONTEXT_SIZE,
            }

            # --- Summary metrics ---
            if task_type == "classification":
                preds_arr = np.asarray(all_preds)
                truth_arr = np.asarray(all_truth)
                n_correct = int(np.sum(preds_arr == truth_arr))
                n_total = len(all_preds)
                accuracy = round(n_correct / n_total, 4) if n_total > 0 else 0.0

                # Per-class metrics — stringify arrays so label comparisons work
                # regardless of whether the model returned strings or numpy types.
                preds_str = np.asarray([str(v) for v in preds_arr])
                truth_str = np.asarray([str(v) for v in truth_arr])
                classes = sorted(set(np.concatenate([truth_str, preds_str])))
                class_metrics = []
                for cls in classes:
                    tp = int(np.sum((preds_str == cls) & (truth_str == cls)))
                    fp = int(np.sum((preds_str == cls) & (truth_str != cls)))
                    fn = int(np.sum((preds_str != cls) & (truth_str == cls)))
                    precision = round(tp / (tp + fp), 4) if (tp + fp) > 0 else 0.0
                    recall = round(tp / (tp + fn), 4) if (tp + fn) > 0 else 0.0
                    f1 = round(2 * precision * recall / (precision + recall), 4) if (precision + recall) > 0 else 0.0
                    class_metrics.append({
                        "class": cls,
                        "precision": precision,
                        "recall": recall,
                        "f1_score": f1,
                        "support": int(np.sum(truth_str == cls)),
                    })

                # Confusion matrix
                confusion = {}
                for t, p in zip(truth_str, preds_str):
                    key = f"{t}→{p}"
                    confusion[key] = confusion.get(key, 0) + 1

                result["metrics"] = {
                    "accuracy": accuracy,
                    "n_correct": n_correct,
                    "n_total": n_total,
                    "per_class": class_metrics,
                    "confusion": confusion,
                }

                # Probabilities (last batch only, memory-safe)
                if hasattr(estimator, "predict_proba"):
                    try:
                        probs = estimator.predict_proba(X_test.iloc[:32])
                        result["probabilities"] = np.asarray(probs).tolist()
                    except Exception as exc:
                        result["probabilities_error"] = str(exc)

            elif task_type == "regression":
                preds_arr = np.asarray(all_preds, dtype=float)
                truth_arr = np.asarray(all_truth, dtype=float)
                residuals = truth_arr - preds_arr
                n = len(all_preds)

                mae = float(np.mean(np.abs(residuals)))
                rmse = float(np.sqrt(np.mean(residuals ** 2)))
                ss_res = float(np.sum(residuals ** 2))
                ss_tot = float(np.sum((truth_arr - np.mean(truth_arr)) ** 2))
                r2 = round(1 - ss_res / ss_tot, 4) if ss_tot > 0 else 0.0
                mape_values = np.abs(residuals / np.where(truth_arr != 0, truth_arr, 1e-10))
                mape = float(np.mean(mape_values)) * 100

                result["metrics"] = {
                    "r_squared": r2,
                    "mae": round(mae, 4),
                    "rmse": round(rmse, 4),
                    "mape_pct": round(mape, 2),
                    "n": n,
                    "prediction_range": [round(float(np.min(preds_arr)), 4), round(float(np.max(preds_arr)), 4)],
                    "ground_truth_range": [round(float(np.min(truth_arr)), 4), round(float(np.max(truth_arr)), 4)],
                }

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        else:
            return _error(f"Unknown tool: {name}")

    except FileNotFoundError as exc:
        return _error(
            str(exc),
            hint=(
                "The file_path must be either (a) a path returned by "
                "zer0fit_upload_csv, (b) a filename that exists in "
                "/app/data/ on the Zer0Fit server, or (c) an Open WebUI "
                "file attachment ID (if the Open WebUI uploads volume is "
                "mounted). If the file is not accessible, upload it first "
                "using zer0fit_upload_csv with the actual file content "
                "as base64."
            ),
        )
    except ValueError as exc:
        return _error(str(exc))
    except Exception as exc:
        logger.exception("Unhandled error in call_tool %s", name)
        return _error(f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Starlette / Transport plumbing (SSE + Streamable HTTP)
# ---------------------------------------------------------------------------

# SSE transport (for older MCP clients and direct SSE connections)
sse = SseServerTransport("/messages/")

# Streamable HTTP transport (for Open WebUI v0.10+ which uses streamablehttp_client)
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from contextlib import asynccontextmanager

# The session manager handles multiple HTTP requests within the same MCP session.
# It takes the MCP server app directly and manages the transport lifecycle.
http_session_manager = StreamableHTTPSessionManager(
    app=app_server,
    json_response=False,
)


@asynccontextmanager
async def lifespan(app):
    """Start the streamable HTTP session manager on app startup."""
    async with http_session_manager.run():
        yield


class StreamableHTTPASGIApp:
    """Raw ASGI app that delegates to the StreamableHTTPSessionManager.

    This must be mounted as an ASGI app (not a Starlette endpoint function)
    because handle_request writes directly to the ASGI send channel and
    does not return a Starlette Response object.  Using ``endpoint=``
    causes Starlette's request_response wrapper to call the return value
    (None) as an ASGI app, producing:
        TypeError: 'NoneType' object is not callable
    """

    def __init__(self, session_manager: StreamableHTTPSessionManager):
        self.session_manager = session_manager

    async def __call__(self, scope, receive, send) -> None:
        await self.session_manager.handle_request(scope, receive, send)


streamable_http_asgi_app = StreamableHTTPASGIApp(http_session_manager)


async def handle_sse(request):
    async with sse.connect_sse(request.scope, request.receive, request._send) as (read_stream, write_stream):
        init_options = InitializationOptions(
            server_name="zer0fit-mcp",
            server_version="1.0.0",
            capabilities=app_server.get_capabilities(
                notification_options=NotificationOptions(),
                experimental_capabilities=None,
            ),
        )
        await app_server.run(read_stream, write_stream, init_options)


async def health(request):
    """Lightweight health endpoint used by Docker HEALTHCHECK."""
    state = _mgr.state.value
    active = _mgr.active_model_type.value if _mgr.active_model_type else None
    return JSONResponse(
        {"status": "healthy", "state": state, "active_model": active}
    )


def create_starlette_app() -> Starlette:
    routes = [
        # SSE transport (legacy / direct connection)
        Route("/sse", endpoint=handle_sse),
        Mount("/messages/", app=sse.handle_post_message),
        # Streamable HTTP transport (Open WebUI v0.10+)
        # Route with a class-instance endpoint — Starlette detects it's
        # not a function/method and uses it as a raw ASGI app, bypassing
        # the request_response wrapper that caused the NoneType crash.
        Route("/mcp", endpoint=streamable_http_asgi_app, methods=["GET", "POST", "DELETE"]),
        # Health check
        Route("/health", endpoint=health),
    ]
    return Starlette(
        routes=routes,
        debug=os.environ.get("ZER0FIT_DEBUG", "false").lower() in ("1", "true", "yes"),
        lifespan=lifespan,
    )


app = create_starlette_app()


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8002)


if __name__ == "__main__":
    main()