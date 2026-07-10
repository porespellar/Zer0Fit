# Attribution & Third-Party Licenses

Zer0Fit is licensed under the **Apache License, Version 2.0** (see [LICENSE](LICENSE)).

This project makes use of the following third-party models and libraries, each with their own licenses. We are grateful to the respective authors for their work.

---

## Google TimesFM 2.5

- **Source**: [https://github.com/google-research/timesfm](https://github.com/google-research/timesfm)
- **License**: Apache License, Version 2.0
- **Copyright**: 2024 Google LLC
- **Citation**:
  > Das, A., et al. "A decoder-only foundation model for time-series forecasting."
  > arXiv preprint arXiv:2310.10688, 2024.

### TimesFM License Notice

```
Copyright 2024 Google LLC

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

TimesFM is used as an unmodified dependency. Model weights are downloaded at runtime from Hugging Face Hub under the TimesFM model card terms.

---

## Google TabFM v1.0.0

- **Source**: [https://github.com/google-research/tabfm](https://github.com/google-research/tabfm)
- **License**: Apache License, Version 2.0
- **Copyright**: 2024 Google LLC

### TabFM License Notice

```
Copyright 2024 Google LLC

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

TabFM is used as an unmodified dependency cloned from the [google-research/tabfm](https://github.com/google-research/tabfm) repository at build time. Model weights are downloaded at runtime under the TabFM model card terms.

---

## Python Dependencies

This project depends on several open-source Python packages, each under their own licenses (predominantly MIT, Apache 2.0, and BSD). Key dependencies include:

| Package | License |
|---------|---------|
| PyTorch | BSD-style |
| pandas | BSD-3-Clause |
| scikit-learn | BSD-3-Clause |
| huggingface_hub | Apache 2.0 |
| MCP (Python SDK) | MIT |
| Starlette / Uvicorn | BSD-3-Clause |
| accelerate | Apache 2.0 |
| einops | MIT |
| openpyxl | MIT |
| xlrd | BSD-3-Clause |

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
