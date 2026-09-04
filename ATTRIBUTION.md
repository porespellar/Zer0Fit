# Attribution & Third-Party Licenses

Zer0Fit is licensed under the **Apache License, Version 2.0** (see [LICENSE](LICENSE)).

This project makes use of the following third-party models and libraries, each with their own licenses. We are grateful to the respective authors for their work.

---

## Google TimesFM 3.0

- **Source code**: [google-research/timesfm](https://github.com/google-research/timesfm)
- **Package**: `timesfm==3.0.1`
- **Checkpoint**: [google/timesfm-3.0-pytorch](https://huggingface.co/google/timesfm-3.0-pytorch)
- **Source license**: Apache License, Version 2.0
- **Pretrained-weight license**: [TimesFM Non-Commercial License v1.0](https://huggingface.co/google/timesfm-3.0-pytorch/blob/main/LICENSE); restricted to non-commercial, non-production use
- **Copyright**: 2024–2026 Google LLC
- **Citation**:
  > Das, A., et al. "A decoder-only foundation model for time-series forecasting."
  > ICML 2024. https://openreview.net/forum?id=jn2iTJas6h

### TimesFM Source License Notice

```
Copyright 2024–2026 Google LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```

Zer0Fit uses the unmodified TimesFM 3.0 package and downloads its pretrained weights at runtime. The source code and the pretrained weights have separate license terms; the TimesFM 3.0 weights must not be used for commercial or production purposes.

---

## Google TabFM v1.0.0

- **Source**: [https://github.com/google-research/tabfm](https://github.com/google-research/tabfm)
- **License**: TabFM Non-Commercial License v1.0 (model weights); Apache License, Version 2.0 (source code)
- **Copyright**: 2026 Google LLC
- **Citation**:
  > Google Research. "TabFM: A Zero-Shot Foundation Model for Tabular Data." 2026.
  > https://research.google/blog/introducing-tabfm-a-zero-shot-foundation-model-for-tabular-data/

### TabFM License Notice

```
Copyright 2026 Google LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```

TabFM is used as an unmodified dependency. Model weights are downloaded at runtime from Hugging Face Hub under the [TabFM Non-Commercial License v1.0](https://huggingface.co/google/tabfm-1.0.0-pytorch/blob/main/LICENSE). The source code is cloned from [google-research/tabfm](https://github.com/google-research/tabfm) under Apache 2.0.

> **Note:** The TabFM Non-Commercial License restricts commercial use of the model weights. Ensure your use case complies with the license terms before deployment.

---

## TabFM update status

The latest official TabFM release remains **v1.0.1**, and the pinned source commit `fbb665569425fd2f490c6576b3af967876fe11ff` is identical to the current upstream `main` branch as checked for this release. TabFM still loads the v1.0.0 pretrained weights; no newer official model-weight release was found.

## Python Dependencies

This project depends on several open-source Python packages, each under their own licenses (predominantly MIT, Apache 2.0, and BSD). Key dependencies include:

| Package | License |
|---------|---------|
| PyTorch | BSD-style |
| pandas | BSD-3-Clause |
| scikit-learn | BSD-3-Clause |
| huggingface_hub | Apache 2.0 |
| MCP (Python SDK) | MIT |
| FastAPI | MIT |
| Starlette / Uvicorn | BSD-3-Clause |
| accelerate | Apache 2.0 |
| einops | MIT |
| openpyxl | MIT |
| xlrd | BSD-3-Clause |
| absl-py | Apache 2.0 |
| TimesFM | Apache 2.0 |

---

## Sample Datasets

The sample datasets included in `data/` are public domain or openly licensed benchmark datasets:

| Dataset | Source | License |
|---------|--------|---------|
| **Iris** | R.A. Fisher, 1936 | Public domain |
| **Airline Passengers** | Box & Jenkins, 1976 | Public domain |
| **California Housing** | Pace & Barry, 1997 | Public domain |

---

## General Notice

Zer0Fit is **not affiliated with or endorsed by Google LLC**. TimesFM and TabFM are trademarks of their respective owners. This project is an independent integration layer that provides an MCP transport for these open-source models.

If you believe any attribution is missing or incorrect, please open an issue.
