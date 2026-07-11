"""
Zer0Fit model_manager.py — the Dynamic VRAM Governor.

Responsibilities:
  * Asynchronously load / evict TimesFM and TabFM foundation models.
  * Enforce mutual exclusion: only one foundation model hot in VRAM at a time.
  * TTL-based idle eviction: if no tool invocation touches the active model
    within ZER0FIT_VRAM_TTL seconds (default 300), automatically purge it,
    run gc.collect(), and call torch.cuda.empty_cache().
  * Provide a single async entry point (`get_model`) that callers use to
    request a model by name; the governor handles eviction transparently.

Design notes:
  * The actual heavy-lifting imports (timesfm, tabfm) are done lazily inside
    the loader coroutines so that the module imports cleanly even when those
    packages are not yet installed (e.g. during unit testing on this host).
  * All public methods are coroutines and are guarded by a single
    asyncio.Lock to serialise state transitions.
"""

from __future__ import annotations

import asyncio
import gc
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger("zer0fit.model_manager")


class ModelType(str, Enum):
    TIMESFM = "timesfm"
    TABFM = "tabfm"


class ModelState(str, Enum):
    IDLE = "IDLE"
    LOADING_TIMESFM = "LOADING_TIMESFM"
    LOADING_TABFM = "LOADING_TABFM"
    HOT_CACHED = "HOT_CACHED"
    MUTUAL_EXCLUSION_EVICTION = "MUTUAL_EXCLUSION_EVICTION"
    PURGED_TO_HOST = "PURGED_TO_HOST"


@dataclass
class _HotModel:
    model_type: ModelType
    instance: Any
    loaded_at: float
    last_used_at: float
    # metadata for TabFM (sklearn estimators)
    clf: Any = None
    reg: Any = None
    # TabFM task type this model was loaded for ("classification" or "regression").
    tabfm_task_type: str = ""


def _default_ttl() -> int:
    try:
        return int(os.environ.get("ZER0FIT_VRAM_TTL", "300"))
    except ValueError:
        return 300


@dataclass
class ModelManager:
    ttl_seconds: int = field(default_factory=_default_ttl)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    _hot: Optional[_HotModel] = field(default=None, repr=False)
    _sweeper_task: Optional[asyncio.Task] = field(default=None, repr=False)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    @property
    def state(self) -> ModelState:
        if self._hot is None:
            return ModelState.IDLE
        return ModelState.HOT_CACHED

    @property
    def active_model_type(self) -> Optional[ModelType]:
        return self._hot.model_type if self._hot else None

    async def get_model(
        self,
        model_type: ModelType,
        task_type: str = "classification",
    ) -> Any:
        """Return the hot model instance for *model_type*, loading or
        evicting as necessary.  Resets the TTL timer on every call.

        ``task_type`` is passed through to the TabFM loader so the correct
        model weights are loaded; it is ignored for TimesFM.
        """
        async with self._lock:
            if self._hot is not None and self._hot.model_type == model_type:
                self._hot.last_used_at = time.monotonic()
                return self._hot.instance

            # Need to load a different model — evict current first.
            if self._hot is not None:
                await self._evict_locked(reason="mutual_exclusion")

            if model_type is ModelType.TIMESFM:
                instance = await self._load_timesfm_locked()
            else:
                instance = await self._load_tabfm_locked(task_type=task_type)

            self._hot = _HotModel(
                model_type=model_type,
                instance=instance,
                loaded_at=time.monotonic(),
                last_used_at=time.monotonic(),
            )
            self._ensure_sweeper()
            return instance

    async def get_tabfm_estimator(self, task_type: str) -> Any:
        """Return a TabFMClassifier or TabFMRegressor.

        `task_type` is 'classification' or 'regression'.
        The estimator is constructed once per load and cached on the hot
        model entry.  The base model is loaded with the correct
        model_type so weights match the task.
        """
        # Check if we need to evict or load, all under the lock to prevent
        # race conditions with the background sweeper and concurrent callers.
        need_load = False
        async with self._lock:
            if self._hot is not None and self._hot.model_type == ModelType.TABFM:
                if self._hot.tabfm_task_type != task_type:
                    # Wrong task type — evict and reload with correct weights.
                    await self._evict_locked(reason="tabfm_task_type_mismatch")
                    need_load = True
                else:
                    # Already hot with the right task — touch the TTL.
                    self._hot.last_used_at = time.monotonic()
            else:
                need_load = True

        # Load outside the lock — get_model acquires the lock internally and
        # _load_tabfm_locked uses asyncio.to_thread which must not run under lock.
        if need_load:
            model = await self.get_model(ModelType.TABFM, task_type=task_type)
        else:
            model = self._hot.instance  # type: ignore[union-attr]

        # Build and cache the estimator under the lock.
        async with self._lock:
            if self._hot is None or self._hot.model_type != ModelType.TABFM:
                raise RuntimeError("TabFM unexpectedly evicted mid-call")
            self._hot.last_used_at = time.monotonic()
            self._hot.tabfm_task_type = task_type
            if task_type == "classification":
                if self._hot.clf is None:
                    from tabfm import TabFMClassifier
                    self._hot.clf = TabFMClassifier(
                        model=model, n_estimators=8, batch_size=8,
                        max_num_rows=256,
                    )
                return self._hot.clf
            elif task_type == "regression":
                if self._hot.reg is None:
                    from tabfm import TabFMRegressor
                    self._hot.reg = TabFMRegressor(
                        model=model, n_estimators=8, batch_size=8,
                        max_num_rows=256,
                    )
                return self._hot.reg
            else:
                raise ValueError(f"Unknown task_type: {task_type!r}")

    async def purge(self) -> None:
        """Force-evict the current hot model immediately."""
        async with self._lock:
            if self._hot is not None:
                await self._evict_locked(reason="manual_purge")

    async def shutdown(self) -> None:
        """Clean shutdown — purge model and cancel sweeper."""
        await self.purge()
        if self._sweeper_task is not None:
            self._sweeper_task.cancel()
            try:
                await self._sweeper_task
            except asyncio.CancelledError:
                pass
            self._sweeper_task = None

    # ------------------------------------------------------------------ #
    # Internal helpers (must be called under self._lock)
    # ------------------------------------------------------------------ #

    async def _load_timesfm_locked(self) -> Any:
        logger.info("Loading TimesFM 2.5 (200M, PyTorch backend)...")

        def _load():
            import timesfm
            tfm = timesfm.TimesFM_2p5_200M_torch.from_pretrained(
                "google/timesfm-2.5-200m-pytorch"
            )
            tfm.compile(
                timesfm.ForecastConfig(
                    max_context=1024,
                    max_horizon=256,
                    normalize_inputs=True,
                    use_continuous_quantile_head=True,
                    force_flip_invariance=True,
                    infer_is_positive=True,
                    fix_quantile_crossing=True,
                )
            )
            return tfm

        # Offload to a thread so the async event loop is not blocked for
        # the (potentially minutes-long) PyTorch model load + compile.
        tfm = await asyncio.to_thread(_load)
        logger.info("TimesFM loaded and compiled successfully.")
        return tfm

    async def _load_tabfm_locked(self, task_type: str = "classification") -> Any:
        logger.info("Loading TabFM v1.0.0 (PyTorch backend, task=%s)...", task_type)

        def _load():
            from tabfm import tabfm_v1_0_0_pytorch
            return tabfm_v1_0_0_pytorch.load(model_type=task_type)

        # Offload to a thread so the async event loop is not blocked.
        model = await asyncio.to_thread(_load)
        logger.info("TabFM base model loaded successfully (task=%s).", task_type)
        return model

    async def _evict_locked(self, reason: str) -> None:
        if self._hot is None:
            return
        logger.info(
            "Evicting %s (reason=%s) — releasing VRAM...",
            self._hot.model_type.value,
            reason,
        )
        # Drop Python references.
        self._hot.instance = None
        self._hot.clf = None
        self._hot.reg = None
        self._hot = None
        # Force GC and clear CUDA cache.
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logger.info("torch.cuda.empty_cache() completed.")
        except Exception as exc:  # pragma: no cover — CUDA not present
            logger.debug("CUDA cache clear skipped: %s", exc)

    def _ensure_sweeper(self) -> None:
        if self._sweeper_task is None or self._sweeper_task.done():
            self._sweeper_task = asyncio.create_task(self._sweeper_loop())

    async def _sweeper_loop(self) -> None:
        """Background coroutine that evicts the hot model after TTL expiry."""
        while True:
            await asyncio.sleep(5)
            async with self._lock:
                if self._hot is None:
                    return  # nothing to sweep; exit
                idle = time.monotonic() - self._hot.last_used_at
                if idle >= self.ttl_seconds:
                    logger.info(
                        "TTL expired (%ds idle ≥ %ds) — auto-purging %s.",
                        int(idle),
                        self.ttl_seconds,
                        self._hot.model_type.value,
                    )
                    await self._evict_locked(reason="ttl_expiry")
                    return


# Module-level singleton — the rest of the app uses this instance.
manager = ModelManager()