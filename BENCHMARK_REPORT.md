# Benchmark Report

> **Status: in progress.** The structure is final; the results tables are filled from the
> `solution.json` files of the benchmark runs. Cells marked `—` have not been measured yet.

## 1. Setup

### Models and providers

All models are free tiers, called through their OpenAI-compatible API (see `models.json`).

| # | Model | Provider |
|---|---|---|
| 1 | `gemini-flash-lite-latest` | Google AI Studio |
| 2 | `nvidia/nemotron-3.5-lightning:free` | OpenRouter |
| 3 | `nvidia/nemotron-3-ultra-550b-a55b:free` | OpenRouter |
| 4 | `inclusionai/ling-3.2-flash:free` | OpenRouter |
| 5 | `baidu/ernie-5.5-flash-preview:free` | OpenRouter |

Backups, if a model becomes unavailable: `nvidia/nemotron-3.5-super-vl:free`,
`recursive/flint-v1.0:free` (OpenRouter).

### Tasks

| Task (SWE-bench Verified `instance_id`) | Repository | Why this task |
|---|---|---|
| — | — | — |
| — | — | — |
| — | — | — |

### How to reproduce

Each run uses the same task (fixed seed) and only changes the model:

```bash
make eval BENCH=swebench SEED=<seed> MODEL=<model>
make show BENCH=swebench
```

The `solution.json` of every run is kept in `benchmark/<model>/<instance_id>.json`.

## 2. Results

| Model | Task | Pass/Fail | Iterations | Input tokens | Output tokens | Time (s) |
|---|---|---|---|---|---|---|
| gemini-flash-lite-latest | — | — | — | — | — | — |
| nemotron-3.5-lightning | — | — | — | — | — | — |
| nemotron-3-ultra-550b | — | — | — | — | — | — |
| ling-3.2-flash | — | — | — | — | — | — |
| ernie-5.5-flash-preview | — | — | — | — | — | — |

## 3. Provider reliability

| Model / provider | Avg. response time per request | Retries needed | Availability during runs |
|---|---|---|---|
| gemini-flash-lite-latest / Google AI Studio | — | — | — |
| nemotron-3.5-lightning / OpenRouter | — | — | — |
| nemotron-3-ultra-550b / OpenRouter | — | — | — |
| ling-3.2-flash / OpenRouter | — | — | — |
| ernie-5.5-flash-preview / OpenRouter | — | — | — |

### Observations during model selection (2026-11-25)

Before the benchmark, each candidate was probed with a short request (`Say hi`). These failures
decided which models were kept:

| Model | Provider | Result |
|---|---|---|
| `gemini-2.5-flash` | Google AI Studio | HTTP 404: model retired |
| `gemini-3.8-flash` | Google AI Studio | HTTP 503 "high demand", later HTTP 429 "exceeded your current quota" |
| `gemini-flash-latest` | Google AI Studio | read timeout / HTTP 503 |
| `gemini-3-flash-preview` | Google AI Studio | HTTP 200 once in 55 s, then HTTP 503 |
| `gemma-4-31b-it` | Google AI Studio | HTTP 400 when `reasoning_effort` is sent; HTTP 200 without it but in 46.8 s; later HTTP 503 |
| `google/gemma-4-31b-it:free`, `google/gemma-4-26b-a4b-it:free` | OpenRouter | HTTP 429: rate limited upstream |
| Mistral (`mistral-small-latest`) | Mistral | HTTP 402: the free plan has no API budget |
| Groq | Groq | account creation blocked (`signup_blocked`) |
| the 5 selected models and 2 backups | | HTTP 200 in 0.4 s to 5.7 s |

## 4. Intermediary metrics

Measured by reading the steps of each `solution.json` (`make show`).

| Model | Task | Step of first read/edit of the patched file | Iterations between tests passing and `final_answer` |
|---|---|---|---|
| — | — | — | — |

## 5. Ablation study

**Change tested:** —

**Same model, same tasks, before / after:**

| Version | Task | Pass/Fail | Iterations | Input tokens | Output tokens |
|---|---|---|---|---|---|
| before | — | — | — | — | — |
| after | — | — | — | — | — |

A first candidate, seen on MBPP task 252 with `nvidia/nemotron-3.5-lightning:free`: the model is a
reasoning model and spent each call's 400-token cap on hidden reasoning. Every reply was empty
(`No valid code block was found`), and the 1,500-token output budget was used up after 4 steps.
Changing `max_tokens_per_call` and `reasoning_effort` for this model is a before/after
comparison to measure.

## 6. Conclusions

—
