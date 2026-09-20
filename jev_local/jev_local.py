#!/usr/bin/env python3
"""
JEV-Local: System-1 style decision engine for local LLMs.
Mimics TypefAI JEV: structured choices only, no chatter, calibrated confidence.
Compatible with Ollama, vLLM, llama.cpp (OpenAI-compatible endpoints).

⚠️ PERFORMANCE NOTE:
- Target latency: 70-500ms (like cloud JEV)
- CPU inference: 2-10s (too slow for real-time)
- GPU required: 8GB+ VRAM for 7B @ Q4_K_M
- Best: llama.cpp server on GPU, or vLLM with batching
"""

import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field, model_validator

# ─── Config ──────────────────────────────────────────────────────────────
DEFAULT_ENDPOINT = os.getenv("JEV_LOCAL_ENDPOINT", "http://localhost:11434")  # Ollama default
DEFAULT_MODEL = os.getenv("JEV_LOCAL_MODEL", "qwen2.5:7b")
DEFAULT_TIMEOUT = 30.0

# ─── Schemas ─────────────────────────────────────────────────────────────
class QuestionSpec(BaseModel):
    type: Literal["choice", "score", "noul"] = "choice"
    instructions: str
    criteria: dict[str, str] | None = None  # for choice: label->description
    min_value: float | None = None  # for score
    max_value: float | None = None  # for score

class JEVAnswer(BaseModel):
    choice: str
    probabilities: dict[str, float]
    confidence: float = Field(ge=0.0, le=1.0)
    # Optional: for score type questions (model may output this instead)
    score: float | None = None
    range: list[float] | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_score(cls, data: Any) -> Any:
        if isinstance(data, dict) and "score" in data and "choice" not in data:
            score = data.get("score", 5.0)
            rng = data.get("range", [0, 10])
            # Convert score to choice format
            data = {
                "choice": str(score),
                "probabilities": {str(score): 1.0},
                "confidence": data.get("confidence", 0.8),
                "score": score,
                "range": rng,
            }
        return data

class JEVResponse(BaseModel):
    answers: dict[str, JEVAnswer]

# ─── Prompt Template (System-1: no reasoning tokens) ─────────────────────
SYSTEM_PROMPT = """Output ONLY valid JSON. No explanations. No thinking. No markdown.

Format:
{"answers": {"question_name": {"choice": "opt", "probabilities": {"opt": 1.0}, "confidence": 1.0}}}
"""

def build_user_prompt(state: str, questions: dict[str, QuestionSpec]) -> str:
    """Compact prompt: state + questions → JSON completion."""
    q_desc = {}
    for name, spec in questions.items():
        if spec.type == "choice":
            opts = list(spec.criteria.keys()) if spec.criteria else []
            q_desc[name] = {"type": "choice", "instruction": spec.instructions, "options": opts}
        elif spec.type == "score":
            q_desc[name] = {"type": "score", "instruction": spec.instructions, "range": [spec.min_value or 0, spec.max_value or 10]}
        else:
            q_desc[name] = {"type": "noul", "instruction": spec.instructions}
    return f"State: {state}\nQuestions: {json.dumps(q_desc, ensure_ascii=False)}\nOutput JSON:"


# ─── Core Client ─────────────────────────────────────────────────────────
class JEVLocal:
    def __init__(
        self,
        endpoint: str = DEFAULT_ENDPOINT,
        model: str = DEFAULT_MODEL,
        timeout: float = DEFAULT_TIMEOUT,
        temperature: float = 0.1,
        max_tokens: int = 128,
        backend: Literal["auto", "ollama", "openai"] = "auto",
    ):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.backend = backend
        self._client = httpx.Client(timeout=timeout, http2=False)

    def _detect_backend(self) -> str:
        """Auto-detect backend from endpoint."""
        if self.backend != "auto":
            return self.backend
        # Ollama default port
        if ":11434" in self.endpoint:
            return "ollama"
        # vLLM/llama.cpp/LM Studio default ports
        if any(port in self.endpoint for port in (":8080", ":8000", ":1234")):
            return "openai"
        try:
            r = self._client.get(f"{self.endpoint}/v1/models", timeout=2.0)
            if r.status_code == 200:
                return "openai"
        except Exception:
            pass
        try:
            r = self._client.get(f"{self.endpoint}/api/tags", timeout=2.0)
            if r.status_code == 200:
                return "ollama"
        except Exception:
            pass
        return "openai"  # default

    def _call_llm(self, prompt: str) -> str:
        """Call local LLM with backend-specific format."""
        backend = self._detect_backend()

        if backend == "openai":
            return self._call_openai_compat(prompt)
        else:
            return self._call_ollama(prompt)

    def _call_openai_compat(self, prompt: str) -> str:
        """vLLM, llama.cpp server, OpenAI-compatible /v1/chat/completions"""
        url = f"{self.endpoint}/v1/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "response_format": {"type": "json_object"},
        }
        r = self._client.post(url, json=payload)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    def _call_ollama(self, prompt: str) -> str:
        """Ollama native /api/chat"""
        url = f"{self.endpoint}/api/chat"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "options": {"temperature": self.temperature, "num_predict": self.max_tokens},
            "format": "json",
            "stream": False,
        }
        r = self._client.post(url, json=payload)
        r.raise_for_status()
        return r.json()["message"]["content"]

    @staticmethod
    def _extract_json(text: str) -> dict:
        """Robust JSON extraction from model output."""
        # Direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Fenced code block
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        # First {...} block
        m = re.search(r"(\{.*\})", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        raise ValueError(f"Cannot extract valid JSON from model output: {text[:200]}")

    def decide(self, state: str, questions: dict[str, QuestionSpec]) -> JEVResponse:
        """Single call: state + multiple questions → structured decisions."""
        prompt = build_user_prompt(state, questions)
        raw = self._call_llm(prompt)
        data = self._extract_json(raw)
        return JEVResponse.model_validate(data)

    def decide_one(self, state: str, name: str, spec: QuestionSpec) -> JEVAnswer:
        """Convenience: single question."""
        return self.decide(state, {name: spec}).answers[name]


# ─── High-Level Helpers ──────────────────────────────────────────────────
def decide_action(state: str, actions: list[str], endpoint: str = None, model: str = None) -> JEVAnswer:
    """Quick helper: pick one action from list."""
    jev = JEVLocal(endpoint=endpoint or DEFAULT_ENDPOINT, model=model or DEFAULT_MODEL)
    return jev.decide_one(
        state,
        "action",
        QuestionSpec(type="choice", instructions="Select next action", criteria={a: a for a in actions}),
    )

def decide_score(state: str, question: str, min_v: float = 0, max_v: float = 10, endpoint: str = None, model: str = None) -> JEVAnswer:
    """Quick helper: numeric score."""
    jev = JEVLocal(endpoint=endpoint or DEFAULT_ENDPOINT, model=model or DEFAULT_MODEL)
    return jev.decide_one(
        state,
        "score",
        QuestionSpec(type="score", instructions=question, min_value=min_v, max_value=max_v),
    )

def decide_binary(state: str, question: str, endpoint: str = None, model: str = None) -> JEVAnswer:
    """Quick helper: yes/no gate (noul)."""
    jev = JEVLocal(endpoint=endpoint or DEFAULT_ENDPOINT, model=model or DEFAULT_MODEL)
    return jev.decide_one(
        state,
        "gate",
        QuestionSpec(type="noul", instructions=question),
    )


# ─── CLI / Tool Entry Point ──────────────────────────────────────────────
def main():
    import argparse

    parser = argparse.ArgumentParser(description="JEV-Local: structured decisions from local LLM")
    parser.add_argument("--state", required=True, help="Current state / context")
    parser.add_argument("--questions", required=True, help="JSON string of questions dict")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--max-tokens", type=int, default=128)
    parser.add_argument("--backend", choices=["auto", "ollama", "openai"], default="auto")
    args = parser.parse_args()

    questions_data = json.loads(args.questions)
    questions = {k: QuestionSpec(**v) for k, v in questions_data.items()}

    jev = JEVLocal(
        endpoint=args.endpoint,
        model=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        backend=args.backend,
    )
    result = jev.decide(args.state, questions)
    print(result.model_dump_json(ensure_ascii=False))


if __name__ == "__main__":
    main()