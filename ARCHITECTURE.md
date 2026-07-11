# Zer0Fit — Technical Architecture

## 1. Component Overview

```
                    ┌────────────────────────────────────────────────┐
                    │              server.py (MCP Bridge)              │
                    │                                                │
  Open WebUI ──SSE──▶  Starlette app on 0.0.0.0:8002                 │
                    │     ├── /sse          (SseServerTransport)     │
                    │     ├── /messages/    (POST back-channel)       │
                    │     ├── /mcp          (Streamable HTTP, v0.10+)  │
                    │     └── /health       (liveness probe)          │
                    └───────────┬───────────────────┬────────────────┘
                                │                   │
                     ┌──────────▼──────┐  ┌─────────▼──────────┐
                     │  model_manager  │  │     pipelines       │
                     │  .py            │  │  .py                │
                     │                 │  │                     │
                     │  asyncio.Lock   │  │  load_time_series() │
                     │  TTL sweeper    │  │  downsample_for…()  │
                     │  mutual exclus. │  │  chunk_tabular()    │
                     └────────┬────────┘  └─────────────────────┘
                              │
                    ┌─────────▼──────────┐
                    │  GPU VRAM          │
                    │  ┌──────────────┐  │
                    │  │ TimesFM 200M │  │  ← only ONE hot at a time
                    │  │   OR         │  │
                    │  │ TabFM v1.0   │  │
                    │  └──────────────┘  │
                    └────────────────────┘
```

## 2. VRAM State Machine

The `ModelManager` class in `model_manager.py` enforces a strict state machine for GPU memory:

```
  ┌──────────────────────────────────────────────────────────────────┐
  │                                                                  │
  │  IDLE                                                            │
  │    │ get_model(TIMESFM)                                          │
  │    ▼                                                             │
  │  LOADING_TIMESFM ──── from_pretrained() + compile() ────┐        │
  │                                                          ▼        │
  │  LOADING_TABFM ──── tabfm_v1_0_0_pytorch.load() ────┐   │        │
  │                                                      ▼   ▼        │
  │                                                    HOT_CACHED      │
  │                                                    (single model)  │
  │                                                      │            │
  │              ┌───────────────────────────────────────┤            │
  │              │                                       │            │
  │       TTL expiry                                get_model(OTHER)  │
  │              │                                       │            │
  │              ▼                                       ▼            │
  │    MUTUAL_EXCLUSION_EVICTION               MUTUAL_EXCLUSION_EVICTION
  │              │                                       │            │
  │              └───────────────┬───────────────────────┘            │
  │                              ▼                                    │
  │                        PURGED_TO_HOST                              │
  │                   del model; gc.collect();                         │
  │                   torch.cuda.empty_cache()                         │
  │                              │                                    │
  │                              ▼                                    │
  │                           IDLE                                    │
  │                                                                   │
  └───────────────────────────────────────────────────────────────────┘
```

### State definitions

| State | Description |
|---|---|
| `IDLE` | No model loaded. VRAM is free. |
| `LOADING_TIMESFM` | TimesFM weights being downloaded / moved to GPU. |
| `LOADING_TABFM` | TabFM base model being loaded. |
| `HOT_CACHED` | A single foundation model is resident in VRAM and ready for inference. |
| `MUTUAL_EXCLUSION_EVICTION` | Active model being evicted because the other foundation type was requested, or TTL expired. |
| `PURGED_TO_HOST` | References dropped, Python GC collected, CUDA cache cleared. Transient — immediately returns to `IDLE`. |

### TTL sweeper

A background `asyncio.Task` (`_sweeper_loop`) runs every 5 seconds. If the hot model has not been touched within `ZER0FIT_VRAM_TTL` seconds (default 300), it auto-purges the model and frees VRAM. The sweeper self-terminates when no model is hot.

### Mutual exclusion

`get_model()` checks the currently hot model type. If the request is for the *other* foundation type, the current model is evicted (state → `MUTUAL_EXCLUSION_EVICTION`) before the new one is loaded. This guarantees only one foundation model occupies VRAM at any time.

---

## 3. Data Pipeline Topologies

### 3.1 TimesFM temporal downsampler

```
  CSV file
    │
    ▼
  load_time_series(file_path, target_column, datetime_column?)
    │  → pd.Series (sorted by datetime if available)
    ▼
  downsample_for_timesfm(series)
    │
    ├── len ≤ 1024?  ──yes──▶ return raw np.float32 array
    │
    ├── has DatetimeIndex?
    │     yes ──▶ resample to coarser rule (min/5min/10min/H/D/W)
    │              → take mean
    │              → if still > 1024, fall through
    │
    └── stride sampling
          arr[::ceil(n/1024)]
          → return downsampled np.float32 array
    │
    ▼
  [np.ndarray]  → model.forecast(horizon=H, inputs=[arr])
    │
    ▼
  (point_forecast, quantile_forecast)
```

The compiled `ForecastConfig` uses `max_context=1024`, so the downsampler targets that ceiling. The 16k context capability of TimesFM 2.5 can be unlocked by raising `max_context` in `model_manager._load_timesfm_locked()`.

### 3.2 TabFM tabular batcher

```
  CSV file
    │
    ▼
  load_tabular(file_path, target_column)
    │  → pd.DataFrame
    ▼
  chunk_tabular(df, target_column, chunk_size=1000)
    │
    ├── block[0:1000]  →  first 512 rows = context, rest = test
    ├── block[1000:2000] →  first 512 rows = context, rest = test
    ├── ...
    │
    ▼
  [(X_train, y_train, X_test, y_test), ...]
    │
    ▼
  estimator.fit(X_train, y_train)
  estimator.predict(X_test)
  estimator.predict_proba(X_test)  [classification only]
```

For very large files, `iter_tabular_chunks()` streams the CSV with `pd.read_csv(chunksize=1000)` to avoid loading the entire dataset into host RAM.

---

## 4. Hardware Matrix

| Component | x86_64 (CUDA 12.4) | ARM64 (CUDA 13.0 nightly) |
|---|---|---|
| Base image | `nvidia/cuda:12.4.1-base-ubuntu24.04` | `nvidia/cuda:13.2.0-base-ubuntu24.04` |
| Torch index | `download.pytorch.org/whl/cu124` | `download.pytorch.org/whl/nightly/cu130` |
| Torch channel | stable | nightly (pre) |
| TabFM backend | `tabfm_v1_0_0_pytorch` | `tabfm_v1_0_0_pytorch` |
| TimesFM backend | `TimesFM_2p5_200M_torch` | `TimesFM_2p5_200M_torch` |

The Dockerfile `TARGETARCH` routing matrix selects the correct wheel set at build time. No code changes are needed between architectures.