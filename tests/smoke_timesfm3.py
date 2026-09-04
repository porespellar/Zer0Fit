#!/usr/bin/env python3
"""Opt-in live TimesFM 3.0 checkpoint smoke test.

This intentionally downloads model weights and is not part of the offline test
suite. Run it only on a host with enough memory/VRAM and network access.
"""

from __future__ import annotations

import numpy as np

# Allow `python tests/smoke_timesfm3.py` from the repository root without
# requiring the project to be installed as a package.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from model_manager import TIMESFM_CHECKPOINT_REVISION
from timesfm3 import TimesFM3Evaluator


CONTEXT = np.asarray(
    [112, 118, 132, 129, 121, 135, 148, 148, 136, 119, 104, 118],
    dtype=np.float32,
)


def main() -> None:
    model = TimesFM3Evaluator.from_pretrained(
        "google/timesfm-3.0-pytorch",
        per_core_batch_size=1,
        revision=TIMESFM_CHECKPOINT_REVISION,
    )
    outputs = list(
        model.predict_batch(
            contexts=[CONTEXT],
            horizon=3,
            return_quantiles=True,
            use_symmetric_averaging=True,
            make_positive=True,
            sort_quantiles=True,
            padding_mode="none",
        )
    )
    assert len(outputs) == 1
    output = outputs[0]
    if output.forecast is None or output.quantiles is None:
        raise AssertionError("TimesFM returned missing forecast or quantiles")
    forecast = np.asarray(output.forecast)
    quantiles = np.asarray(output.quantiles)
    assert forecast.shape == (3,)
    assert quantiles.shape == (3, 9)
    assert np.isfinite(forecast).all()
    assert np.isfinite(quantiles).all()
    print(
        "TimesFM smoke test passed:",
        f"revision={TIMESFM_CHECKPOINT_REVISION}",
        f"forecast_shape={forecast.shape}",
        f"quantiles_shape={quantiles.shape}",
    )


if __name__ == "__main__":
    main()
