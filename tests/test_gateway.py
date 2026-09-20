from jev_local.gateway import build_upstream_payload, models_response


def test_models_response_exposes_jev_local():
    assert models_response()["data"][0]["id"] == "jev-local"


def test_gateway_rewrites_model_and_adds_decision_system_prompt():
    payload = build_upstream_payload(
        {
            "model": "jev-local",
            "messages": [{"role": "user", "content": "A mı B mi?"}],
            "temperature": 0.8,
        },
        "ornith-instance",
    )

    assert payload["model"] == "ornith-instance"
    assert payload["messages"][0]["role"] == "system"
    assert "decision engine" in payload["messages"][0]["content"]
    assert payload["messages"][1]["content"] == "A mı B mi?"
    assert payload["stream"] is False
