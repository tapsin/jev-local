#!/usr/bin/env python3
"""
JEV-Local Interactive Setup Wizard
- Asks provider (LM Studio / Ollama / llama.cpp / vLLM)
- Fetches models from API
- Lets user pick model
- Asks port
- Starts server and validates
"""

import json
import os
import subprocess
import sys
import time
from getpass import getpass
from pathlib import Path

import httpx


PROVIDERS = {
    "1": {"name": "LM Studio", "default_port": 1234, "api_base": "/v1/models", "type": "openai"},
    "2": {"name": "Ollama", "default_port": 11434, "api_base": "/api/tags", "type": "ollama"},
    "3": {"name": "llama.cpp / vLLM", "default_port": 8080, "api_base": "/v1/models", "type": "openai"},
    "4": {"name": "Custom OpenAI-compatible", "default_port": 8000, "api_base": "/v1/models", "type": "openai"},
}


def clear():
    os.system("clear" if os.name != "nt" else "cls")


def print_header(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def print_step(step: int, total: int, title: str):
    print(f"\n[{step}/{total}] {title}")
    print("-" * 40)


def auth_headers(api_key: str | None) -> dict[str, str]:
    """Return an Authorization header without exposing the key."""
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


def ask_api_key() -> str | None:
    """Ask whether the selected endpoint requires an API key."""
    while True:
        answer = input("Bu sağlayıcı için API key var mı/gerekli mi? [e/H]: ").strip().lower()
        if answer in ("", "h", "hayır", "hayir", "n", "no"):
            return None
        if answer in ("e", "evet", "y", "yes"):
            key = getpass("API key (ekranda görünmez): ").strip()
            if key:
                return key
            print("API key boş bırakılamaz.")
            continue
        print("Lütfen 'e' veya 'h' girin.")


def fetch_models(base_url: str, provider_type: str, api_key: str | None = None) -> list[dict]:
    """Fetch available models from provider API."""
    try:
        with httpx.Client(timeout=10.0, headers=auth_headers(api_key)) as client:
            if provider_type == "ollama":
                r = client.get(f"{base_url}/api/tags")
                r.raise_for_status()
                data = r.json()
                return [
                    {
                        "name": m["name"],
                        "size": m.get("size", 0),
                        "context_length": m.get("details", {}).get("context_length", 4096),
                    }
                    for m in data.get("models", [])
                ]
            else:
                r = client.get(f"{base_url}/v1/models")
                r.raise_for_status()
                data = r.json()
                models = []
                for m in data.get("data", []):
                    # LM Studio returns context_length in some cases
                    ctx = m.get("context_length", m.get("max_context_length", 4096))
                    models.append({"name": m["id"], "size": 0, "context_length": ctx})
                return models
    except Exception as e:
        print(f"❌ Model alınamadı: {e}")
        return []


def select_provider() -> dict:
    print_header("JEV-Local Kurulum Sihirbazı")
    print("Hangi sağlayıcıyı kullanmak istiyorsunuz?\n")
    for key, p in PROVIDERS.items():
        print(f"  {key}) {p['name']} (varsayılan port: {p['default_port']})")
    print()

    while True:
        choice = input("Seçim [1-4]: ").strip()
        if choice in PROVIDERS:
            return PROVIDERS[choice]
        print("Geçersiz seçim.")


def select_model(base_url: str, provider_type: str, api_key: str | None = None) -> tuple[str, int]:
    print_step(3, 6, "Model Seçimi")
    print(f"Bağlanılıyor: {base_url} ...\n")

    models = fetch_models(base_url, provider_type, api_key)

    if not models:
        print("⚠️  Model bulunamadı. Manuel girilecek.")
        model = input("Model adı (örn: qwen2.5-coder-7b-instruct): ").strip()
        return model, select_context_length(4096)

    print("Mevcut modeller:\n")
    for i, m in enumerate(models, 1):
        size_gb = m.get("size", 0) / (1024**3)
        size_str = f" ({size_gb:.1f} GB)" if size_gb > 0 else ""
        ctx = m.get("context_length", 4096)
        ctx_str = f" | Context: {ctx}" if ctx else ""
        print(f"  {i}) {m['name']}{size_str}{ctx_str}")

    print()
    while True:
        choice = input(f"Seçim [1-{len(models)}] veya 'm' (manuel): ").strip()
        if choice.lower() == "m":
            model = input("Model adı: ").strip()
            return model, select_context_length(4096)
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(models):
                model = models[idx]["name"]
                default_ctx = models[idx].get("context_length", 4096)
                return model, select_context_length(default_ctx)
        print("Geçersiz seçim.")


def select_context_length(default_ctx: int) -> int:
    """Ask user for context length."""
    print_step(3, 5, "Context Length (Bağlam Uzunluğu)")
    print(f"Modelin desteklediği context length: {default_ctx}")
    print("Daha yüksek = daha uzun konuşma/bağlam, daha fazla VRAM/RAM")
    print(f"Önerilen aralık: 2048 - 131072 (model limitine bağlı)\n")

    while True:
        ctx_input = input(f"Context length [{default_ctx}]: ").strip()
        if not ctx_input:
            return default_ctx
        try:
            ctx = int(ctx_input)
            if 512 <= ctx <= 2000000:
                return ctx
        except ValueError:
            pass
        print("Geçersiz değer. 512-2000000 arası girin.")


def select_port(default_port: int) -> int:
    print_step(3, 4, "Port Seçimi")
    port_input = input(f"Port [{default_port}]: ").strip()
    if not port_input:
        return default_port
    try:
        port = int(port_input)
        if 1 <= port <= 65535:
            return port
    except ValueError:
        pass
    print("Geçersiz port, varsayılan kullanılıyor.")
    return default_port


def load_lm_studio_model(
    base_url: str,
    model: str,
    context_length: int,
    api_key: str | None,
) -> bool:
    """Load the selected LM Studio model through its native REST API."""
    try:
        response = httpx.post(
            f"{base_url}/api/v1/models/load",
            headers=auth_headers(api_key),
            json={
                "model": model,
                "context_length": context_length,
                "echo_load_config": True,
            },
            timeout=300.0,
        )
        response.raise_for_status()
        print("✅ Model LM Studio belleğine yüklendi.")
        return True
    except Exception as exc:
        print(f"❌ LM Studio modeli yüklenemedi: {exc}")
        return False


def start_server(
    provider: dict,
    model: str,
    port: int,
    context_length: int,
    api_key: str | None = None,
) -> subprocess.Popen | None:
    """Start or prepare the inference server based on provider."""
    print_step(4, 5, "Sunucu Başlatılıyor")

    if provider["name"] == "LM Studio":
        base_url = f"http://localhost:{port}"
        print(f"LM Studio API: {base_url}")
        print(f"Model yükleniyor: {model}")
        print(f"Context length: {context_length}")
        if not load_lm_studio_model(base_url, model, context_length, api_key):
            raise RuntimeError(
                "LM Studio modeli aktif edilemedi. API sunucusunu, anahtarı ve belleği kontrol edin."
            )
        return None

    elif provider["name"] == "Ollama":
        print("Ollama zaten servis olarak çalışıyor olmalı.")
        print(f"   Kontrol: curl http://localhost:{port}/api/tags")
        input("   Devam etmek için Enter...")
        return None

    else:  # llama.cpp / vLLM / custom
        # Try to find model file
        model_paths = [
            Path.home() / ".cache" / "huggingface" / "hub" / f"*{model}*" / "*.gguf",
            Path("/home/tapsin/Masaüstü/SansursuzAI/app/llm-models") / f"*{model}*.gguf",
            Path("/home/tapsin") / f"*{model}*.gguf",
        ]

        model_file = None
        for pattern in model_paths:
            matches = list(Path(pattern.parent).glob(pattern.name)) if pattern.parent.exists() else []
            if matches:
                model_file = matches[0]
                break

        if not model_file:
            print(f"❌ Model dosyası bulunamadı: {model}")
            print("   llama.cpp için .gguf dosyası gerekiyor.")
            custom_path = input("   Model dosyası yolu (boş = iptal): ").strip()
            if not custom_path:
                return None
            model_file = Path(custom_path)

        print(f"Model dosyası: {model_file}")
        print(f"Port: {port}")
        print(f"Context length: {context_length}")
        print("Başlatılıyor (GPU offload: -ngl 99)...\n")

        # Start llama-server in background
        cmd = [
            "llama-server",
            "-m", str(model_file),
            "-c", str(context_length),
            "-ngl", "99",
            "--port", str(port),
            "--host", "0.0.0.0",
        ]

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Wait for server to be ready
        print("Sunucu hazırlanıyor...", end=" ", flush=True)
        for _ in range(30):
            time.sleep(1)
            try:
                with httpx.Client(timeout=2.0) as client:
                    r = client.get(f"http://localhost:{port}/health")
                    if r.status_code == 200:
                        print("✅ Hazır!")
                        return proc
            except Exception:
                print(".", end="", flush=True)

        print("\n❌ Sunucu zaman aşımına uğradı.")
        proc.terminate()
        return None


def validate_connection(
    base_url: str, provider_type: str, model: str, api_key: str | None = None
) -> bool:
    """Test the connection with a sample JEV request."""
    print("\nBağlantı test ediliyor...")

    test_payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Output only JSON: {\"answers\": {\"test\": {\"choice\": \"A\", \"probabilities\": {\"A\": 1.0}, \"confidence\": 1.0}}}"},
            {"role": "user", "content": "Test"},
        ],
        "temperature": 0.1,
        "max_tokens": 32,
        "response_format": {"type": "json_object"},
    }

    try:
        with httpx.Client(timeout=30.0, headers=auth_headers(api_key)) as client:
            if provider_type == "ollama":
                test_payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "Output only JSON: {\"answers\": {\"test\": {\"choice\": \"A\", \"probabilities\": {\"A\": 1.0}, \"confidence\": 1.0}}}"},
                        {"role": "user", "content": "Test"},
                    ],
                    "options": {"temperature": 0.1, "num_predict": 32},
                    "format": "json",
                    "stream": False,
                }
                r = client.post(f"{base_url}/api/chat", json=test_payload)
            else:
                r = client.post(f"{base_url}/v1/chat/completions", json=test_payload)

            r.raise_for_status()
            print("✅ Bağlantı başarılı! JEV-Local kullanıma hazır.")
            return True
    except Exception as e:
        print(f"❌ Test başarısız: {e}")
        return False


def save_config(
    provider: dict,
    model: str,
    port: int,
    base_url: str,
    context_length: int,
    api_key: str | None,
    config_dir: Path | None = None,
) -> Path:
    """Save config with user-only permissions."""
    config_dir = config_dir or (Path.home() / ".config" / "jev-local")
    config_dir.mkdir(parents=True, exist_ok=True)

    config = {
        "provider": provider["name"],
        "provider_type": provider["type"],
        "model": model,
        "port": port,
        "context_length": context_length,
        "base_url": base_url,
        "endpoint": f"{base_url}/v1" if provider["type"] == "openai" else base_url,
        "api_key": api_key,
    }

    config_file = config_dir / "config.json"
    config_file.write_text(json.dumps(config, indent=2))
    config_file.chmod(0o600)
    print(f"\n💾 Yapılandırma kaydedildi: {config_file}")
    return config_file


def print_usage(base_url: str, provider_type: str, model: str, context_length: int):
    print_header("Kullanım")
    print("CLI:")
    print(f"  python3 -m jev_local.jev_local \\")
    print(f'    --state "Login page" \\')
    print(f'    --questions \'{{"action": {{"type": "choice", "instructions": "Next?", "criteria": {{"fill": "Type", "click": "Click"}}}}}}\' \\')
    print(f"    --model {model} \\")
    print(f"    --endpoint {base_url} \\")
    print(f"    --backend auto\n")
    print("Python:")
    print(f"  from jev_local import decide_action")
    print(f"  result = decide_action(")
    print(f'      state="...",')
    print(f'      actions=["fill", "click"],')
    print(f'      endpoint="{base_url}",')
    print(f'      model="{model}"')
    print(f"  )")
    print(f"\n⚙️  Context length: {context_length}")
    print(f"\n📖 Docs: https://github.com/tapsin/jev-local")


def main():
    clear()
    print_header("JEV-Local Interactive Setup")

    # Step 1: Provider
    provider = select_provider()

    # Step 2: Port
    port = select_port(provider["default_port"])
    base_url = f"http://localhost:{port}"

    # Step 3: Optional API key (local providers usually do not need one)
    api_key = ask_api_key()

    # Step 4: Model (need base_url and optional auth for fetching)
    model, context_length = select_model(base_url, provider["type"], api_key)

    # Step 5: Start server or load selected model (if needed)
    try:
        server_proc = start_server(provider, model, port, context_length, api_key)
    except RuntimeError as exc:
        print(f"\n❌ {exc}")
        sys.exit(1)

    # Step 6: Validate
    if not validate_connection(base_url, provider["type"], model, api_key):
        print("\n❌ Kurulum başarısız. Manuel kontrol edin.")
        if server_proc:
            server_proc.terminate()
        sys.exit(1)

    # Step 7: Save config
    save_config(provider, model, port, base_url, context_length, api_key)

    # Step 8: Show usage
    print_usage(base_url, provider["type"], model, context_length)

    # Keep server alive if we started it
    if server_proc:
        print("\n⚠️  Sunucu arka planda çalışıyor. Çıkmak için Ctrl+C.")
        try:
            server_proc.wait()
        except KeyboardInterrupt:
            print("\nKapatılıyor...")
            server_proc.terminate()


if __name__ == "__main__":
    main()