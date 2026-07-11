# Disclaimer — Read Before Use

## No Warranty

Zer0Fit is provided **"AS IS"** under the Apache License, Version 2.0, **without warranties or conditions of any kind**, either express or implied. This includes (but is not limited to) implied warranties of merchantability, fitness for a particular purpose, title, and non-infringement. The developer makes no claim that this software will produce correct, accurate, reliable, or useful results.

## Research Use Only

Zer0Fit is intended for **research, educational, and experimental purposes only**. It is **not** a certified, regulated, or clinically validated tool. It must not be used as the sole basis for any decision involving:

- **Financial decisions** — forecasting, investment, trading, risk assessment
- **Medical or health-related decisions** — diagnosis, treatment, triage
- **Legal decisions** — evidence, compliance, adjudication
- **Safety-critical decisions** — autonomous systems, infrastructure, aviation
- **Employment, housing, insurance, or credit decisions** — or any other domain where incorrect predictions could harm individuals or groups

## Prediction Accuracy

Zer0Fit wraps third-party foundation models (Google TimesFM and Google TabFM) and exposes them through an LLM agent layer. Neither the developer of Zer0Fit nor the contributors:

- Guarantee the **accuracy, reliability, or validity** of any prediction, classification, forecast, or regression output
- Guarantee that the **LLM interpreting the results** will correctly understand, summarize, or act on the model's output
- Accept responsibility for **decisions made** based on predictions, metrics, or summaries produced by this software
- Accept responsibility for **errors, omissions, or artifacts** introduced by the underlying models, the data pipeline, the MCP transport layer, or the LLM's interpretation of results

## Limitation of Liability

To the maximum extent permitted by applicable law, neither the developer nor any contributor to Zer0Fit shall be liable for any direct, indirect, incidental, special, consequential, or punitive damages — including loss of profits, data, business, or goodwill — arising from the use of or inability to use this software, regardless of whether such damages were foreseeable or whether the developer was advised of the possibility of such damages.

## User Assumes All Risk

By installing, deploying, configuring, or using Zer0Fit — or by acting on any output it produces — you accept full responsibility for evaluating the accuracy and appropriateness of the results for your specific use case. **Use at your own risk.**

## Third-Party Models

Zer0Fit uses Google's TimesFM and TabFM models under their respective Apache 2.0 licenses. These models are independent works with their own licenses, limitations, and potential biases. The developer of Zer0Fit is not affiliated with or endorsed by Google. See [ATTRIBUTION.md](ATTRIBUTION.md) for model citations.