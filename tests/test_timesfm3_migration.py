"""Regression tests for the TimesFM 3.0 integration.

These tests stub the model loader/inference boundary so they run without a GPU
or downloading the TimesFM 3.0 checkpoint. A separate live smoke test is run
when the real dependency and model are available.
"""

from __future__ import annotations

import asyncio
import json
import sys
from types import ModuleType, SimpleNamespace

import numpy as np

import model_manager
import pipelines
import server


def test_timesfm_pipeline_uses_timesfm3_context_ceiling() -> None:
    assert pipelines.TIMESFM_MAX_CONTEXT == 15360


def test_model_manager_loads_timesfm3_checkpoint(monkeypatch) -> None:
    calls: dict[str, object] = {}

    class FakeEvaluator:
        @classmethod
        def from_pretrained(cls, checkpoint: str, **kwargs):
            calls["checkpoint"] = checkpoint
            calls["kwargs"] = kwargs
            return cls()

    fake_timesfm3 = ModuleType("timesfm3")
    fake_timesfm3.TimesFM3Evaluator = FakeEvaluator
    monkeypatch.setitem(sys.modules, "timesfm3", fake_timesfm3)

    manager = model_manager.ModelManager(ttl_seconds=60)
    loaded = asyncio.run(manager._load_timesfm_locked())

    assert isinstance(loaded, FakeEvaluator)
    assert calls["checkpoint"] == "google/timesfm-3.0-pytorch"
    assert calls["kwargs"] == {"per_core_batch_size": 4}


def test_forecast_serializes_timesfm3_forecast_output(monkeypatch) -> None:
    class FakeTimesFM3:
        def predict_batch(self, **kwargs):
            np.testing.assert_array_equal(
                kwargs["contexts"][0], np.array([1.0, 2.0], dtype=np.float32)
            )
            assert kwargs["horizon"] == 3
            assert kwargs["return_quantiles"] is True
            return iter(
                [
                    SimpleNamespace(
                        forecast=np.array([3.0, 4.0, 5.0], dtype=np.float32),
                        quantiles=np.arange(27, dtype=np.float32).reshape(3, 9),
                    )
                ]
            )

    async def fake_get_model(model_type):
        assert model_type is model_manager.ModelType.TIMESFM
        return FakeTimesFM3()

    monkeypatch.setattr(server, "_resolve_to_path", lambda **_: "/tmp/fake.csv")
    monkeypatch.setattr(server.pipelines, "make_timesfm_forecast_inputs", lambda *args: [
        np.array([1.0, 2.0], dtype=np.float32)
    ])
    monkeypatch.setattr(server._mgr, "get_model", fake_get_model)

    response = asyncio.run(
        server.call_tool(
            "zer0fit_forecast",
            {"file_path": "/tmp/fake.csv", "target_column": "value", "horizon": 3},
        )
    )
    payload = json.loads(response[0].text)

    assert payload["model"] == "timesfm-3.0-pytorch"
    assert payload["horizon"] == 3
    assert payload["point_forecast"] == [3.0, 4.0, 5.0]
    assert len(payload["quantile_forecast"]) == 3
    assert payload["series_length"] == 2
