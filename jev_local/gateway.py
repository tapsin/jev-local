#!/usr/bin/env python3
"""OpenAI-compatible local gateway for JEV-Local."""

import argparse
import json
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx

JEV_SYSTEM_PROMPT = """You are a fast decision engine. Do not chat or explain reasoning.
Return only a concise decision. When choices are provided, output valid JSON with:
{"choice":"selected_option","probabilities":{"option":1.0},"confidence":1.0}
Use only the provided options. Probabilities must sum to 1.0."""


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    config_path = Path(path or Path.home() / ".config" / "jev-local" / "config.json")
    return json.loads(config_path.read_text(encoding="utf-8"))


def models_response() -> dict[str, Any]:
    return {
        "object": "list",
        "data": [
            {
                "id": "jev-local",
                "object": "model",
                "created": 0,
                "owned_by": "tapsin",
            }
        ],
    }


def build_upstream_payload(payload: dict[str, Any], upstream_model: str) -> dict[str, Any]:
    result = dict(payload)
    messages = list(result.get("messages") or [])
    if not messages or messages[0].get("role") != "system":
        messages.insert(0, {"role": "system", "content": JEV_SYSTEM_PROMPT})
    else:
        messages[0] = {
            **messages[0],
            "content": f"{JEV_SYSTEM_PROMPT}\n\nTask instructions:\n{messages[0].get('content', '')}",
        }
    result["messages"] = messages
    result["model"] = upstream_model
    result["stream"] = bool(result.get("stream", False))
    result.setdefault("temperature", 0.1)
    result.setdefault("max_tokens", 256)
    return result


def _error(message: str, status: int = 400) -> tuple[int, dict[str, Any]]:
    return status, {
        "error": {
            "message": message,
            "type": "invalid_request_error",
            "param": None,
            "code": "jev_local_error",
        }
    }


class JEVGatewayHandler(BaseHTTPRequestHandler):
    server_version = "JEVLocal/0.2"

    @property
    def config(self) -> dict[str, Any]:
        return self.server.config  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {format % args}")

    def _json(self, status: int, data: dict[str, Any]) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.rstrip("/") == "/health":
            self._json(200, {"status": "ok", "service": "jev-local"})
            return
        if self.path.rstrip("/") == "/v1/models":
            self._json(200, models_response())
            return
        status, data = _error("Endpoint not found", 404)
        self._json(status, data)

    def do_POST(self) -> None:
        if self.path.rstrip("/") != "/v1/chat/completions":
            status, data = _error("Endpoint not found", 404)
            self._json(status, data)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            status, data = _error("Request body must be valid JSON")
            self._json(status, data)
            return

        upstream_model = self.config.get("upstream_model") or self.config.get("model")
        if not upstream_model:
            status, data = _error("No upstream model configured", 500)
            self._json(status, data)
            return
        upstream = build_upstream_payload(payload, str(upstream_model))
        base_url = self.config["base_url"].rstrip("/")
        provider_type = self.config.get("provider_type", "openai")
        api_key = self.config.get("api_key")
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

        if provider_type == "ollama":
            self._proxy_ollama(base_url, upstream, headers)
        else:
            self._proxy_openai(base_url, upstream, headers)

    def _proxy_openai(self, base_url: str, payload: dict[str, Any], headers: dict[str, str]) -> None:
        try:
            with httpx.Client(timeout=300.0) as client:
                if payload.get("stream"):
                    with client.stream(
                        "POST", f"{base_url}/v1/chat/completions", json=payload, headers=headers
                    ) as response:
                        self.send_response(response.status_code)
                        self.send_header("Content-Type", "text/event-stream")
                        self.send_header("Cache-Control", "no-cache")
                        self.end_headers()
                        for chunk in response.iter_bytes():
                            self.wfile.write(chunk)
                            self.wfile.flush()
                    return
                response = client.post(
                    f"{base_url}/v1/chat/completions", json=payload, headers=headers
                )
            self.send_response(response.status_code)
            self.send_header("Content-Type", response.headers.get("content-type", "application/json"))
            self.send_header("Content-Length", str(len(response.content)))
            self.end_headers()
            self.wfile.write(response.content)
        except Exception as exc:
            status, data = _error(f"Upstream connection failed: {exc}", 502)
            self._json(status, data)

    def _proxy_ollama(self, base_url: str, payload: dict[str, Any], headers: dict[str, str]) -> None:
        ollama_payload = {
            "model": payload["model"],
            "messages": payload["messages"],
            "stream": False,
            "format": "json",
            "options": {
                "temperature": payload.get("temperature", 0.1),
                "num_predict": payload.get("max_tokens", 256),
            },
        }
        try:
            response = httpx.post(
                f"{base_url}/api/chat", json=ollama_payload, headers=headers, timeout=300.0
            )
            response.raise_for_status()
            content = response.json().get("message", {}).get("content", "")
            now = int(time.time())
            data = {
                "id": f"chatcmpl-{uuid.uuid4().hex}",
                "object": "chat.completion",
                "created": now,
                "model": "jev-local",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            }
            self._json(200, data)
        except Exception as exc:
            status, data = _error(f"Ollama connection failed: {exc}", 502)
            self._json(status, data)


def serve(host: str, port: int, config_path: str | None = None) -> None:
    config = load_config(config_path)
    server = ThreadingHTTPServer((host, port), JEVGatewayHandler)
    server.config = config  # type: ignore[attr-defined]
    print(f"JEV-Local OpenAI API: http://{host}:{port}/v1")
    print("Model: jev-local")
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="JEV-Local OpenAI-compatible REST gateway")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3030)
    parser.add_argument("--config", default=None)
    args = parser.parse_args()
    serve(args.host, args.port, args.config)


if __name__ == "__main__":
    main()
