# JEV-Local: System-1 Decision Engine for Local LLMs

A lightweight Python library that mimics **TypefAI's JEV (Journal Entry Voucher / System-1)** behavior on local LLMs via Ollama, vLLM, or llama.cpp.

> **What is JEV?** TypefAI's [JEV](https://typesafe.ai) is a cloud API that returns **structured decisions only** — no chatter, no reasoning tokens, just calibrated probabilities in ~70-500ms. This library brings that pattern to local models.

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| **Structured Output Only** | Returns JSON: `{choice, probabilities, confidence}` — no explanations |
| **Multiple Question Types** | `choice` (pick one), `score` (0-10), `noul` (yes/no gate) |
| **Parallel Questions** | Ask multiple questions in a single LLM call |
| **Backend Agnostic** | Works with **Ollama**, **vLLM**, **llama.cpp** (OpenAI-compatible) |
| **Auto-Detection** | Detects backend from endpoint port automatically |
| **Robust JSON Parsing** | Handles fenced blocks, thinking tokens, partial output |
| **Calibrated Confidence** | Probabilities sum to 1.0, confidence ∈ [0,1] |
| **Zero Dependencies** | Only `httpx` + `pydantic` (std-lib compatible) |

---

## 🚀 Quick Start

### Install
```bash
pip install httpx pydantic --break-system-packages
```

### Run llama.cpp server (GPU recommended)
```bash
llama-server -m qwen2.5-coder-7b-instruct-q4_k_m.gguf -c 4096 -ngl 99 --port 8080
```

### Use as CLI
```bash
python3 jev_local.py \
  --state "Browser on login page with email, password, submit button" \
  --questions '{"action": {"type": "choice", "instructions": "Next step?", "criteria": {"fill_email": "Type email", "fill_password": "Type password", "click_submit": "Click login"}}}' \
  --model qwen2.5-coder-7b-instruct-q4_k_m \
  --endpoint http://localhost:8080 \
  --backend openai
```

**Output:**
```json
{
  "answers": {
    "action": {
      "choice": "fill_email",
      "probabilities": {"fill_email": 0.6, "fill_password": 0.2, "click_submit": 0.2},
      "confidence": 0.85
    }
  }
}
```

### Use as Library
```python
from jev_local import JEVLocal, QuestionSpec, decide_action

# Quick helper
result = decide_action(
    state="Checkout page, user clicked 'Pay'",
    actions=["fill_card", "fill_expiry", "fill_cvc", "click_pay"],
    endpoint="http://localhost:8080",
    model="qwen2.5-coder-7b-instruct-q4_k_m"
)
print(result.choice)  # "fill_card"

# Full control
jev = JEVLocal(endpoint="http://localhost:8080", model="qwen2.5-coder-7b-instruct-q4_k_m")
result = jev.decide(
    state="Page shows captcha challenge",
    questions={
        "is_captcha": QuestionSpec(type="noul", instructions="Is this a captcha?"),
        "action": QuestionSpec(type="choice", instructions="What to do?", criteria={
            "solve": "Solve captcha", "refresh": "Refresh page", "abort": "Give up"
        })
    }
)
```

---

## 📋 Question Types

### 1. Choice (pick one)
```python
QuestionSpec(
    type="choice",
    instructions="Select next browser action",
    criteria={
        "click_login": "Click login button",
        "fill_email": "Type email address",
        "fill_password": "Type password"
    }
)
```

### 2. Score (numeric 0-10)
```python
QuestionSpec(
    type="score",
    instructions="Risk level for this payment page",
    min_value=0,
    max_value=10
)
# Returns: {"choice": "5.0", "probabilities": {"5.0": 1.0}, "confidence": 0.8, "score": 5.0, "range": [0,10]}
```

### 3. NOUL (binary gate — yes/no)
```python
QuestionSpec(
    type="noul",
    instructions="Is this a login page?"
)
# Returns: {"choice": "yes", "probabilities": {"yes": 1.0}, "confidence": 1.0}
```

---

## ⚡ Performance Notes

| Setup | Latency | Notes |
|-------|---------|-------|
| **llama.cpp (GPU, 7B Q4)** | 200-800ms | **Recommended** — use `-ngl 99` for full GPU offload |
| **llama.cpp (CPU, 7B Q4)** | 3-10s | Too slow for real-time agents |
| **Ollama (GPU)** | 500ms-2s | Convenient but higher overhead |
| **vLLM (GPU, batched)** | 100-300ms | Best throughput for parallel agents |

**For JEV-like speed (70-500ms):**
- GPU with 8GB+ VRAM required
- 7B model @ Q4_K_M quantization
- llama.cpp server or vLLM with `--max-model-len 4096`
- Temperature 0.1, max_tokens 64-128

---

## 🔧 Configuration

### Environment Variables
```bash
export JEV_LOCAL_ENDPOINT=http://localhost:8080
export JEV_LOCAL_MODEL=qwen2.5-coder-7b-instruct-q4_k_m
```

### CLI Arguments
```bash
python3 jev_local.py --help
# --state: Current context/state (required)
# --questions: JSON string of questions dict (required)
# --endpoint: API endpoint (default: http://localhost:11434)
# --model: Model name (default: qwen2.5:7b)
# --temperature: Sampling temperature (default: 0.1)
# --max-tokens: Max output tokens (default: 128)
# --backend: auto | ollama | openai (default: auto)
```

---

## 🏗 Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Your Agent     │────▶│  JEVLocal        │────▶│  Local LLM      │
│  (browser, etc) │     │  (this lib)      │     │  (llama.cpp,    │
└─────────────────┘     └──────────────────┘     │   Ollama, vLLM) │
       ▲                      │                   └─────────────────┘
       │           ┌──────────┴──────────┐
       │           │  Structured JSON    │
       │           │  {choice, probs,    │
       │           │   confidence}       │
       │           └─────────────────────┘
       └──────────────────────────────────┘
              Action Execution
```

---

## 🎯 Use Cases

- **Browser Automation Agents** — Decide next action (click, type, scroll)
- **Game AI** — Choose move, evaluate position, risk assessment
- **Robotics** — Discrete action selection from sensor state
- **Trading Bots** — Buy/sell/hold with confidence scores
- **Any System-1 Task** — Fast, reflexive decisions without reasoning overhead

---

## 📄 License

MIT — Use freely, modify, distribute.

---

## 🙏 Credits

- **TypefAI** — Original JEV / System-1 architecture
- **llama.cpp / vLLM / Ollama** — Local inference backends
- **Nous Research** — Hermes agent ecosystem inspiration