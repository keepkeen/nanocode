from __future__ import annotations

from agent_memory_os import AgentMemoryOS, ProviderType, ProviderRequest

from nanocli.models import ModelProfile
from nanocli.provider_loop import ProviderToolLoop
from nanocli.storage import LocalStateStore


class FakeRegistry:
    def execute(self, name, arguments):
        assert name == "search_codebase"
        return {"matches": [arguments["query"]]}


def test_provider_tool_loop_chat_completions(tmp_path):
    store = LocalStateStore(tmp_path / "state.db", tmp_path / "artifacts")
    run = store.create_run(objective="loop", profile="deepseek", cwd=tmp_path)
    memory = AgentMemoryOS(namespace="test")
    profile = ModelProfile(
        name="deepseek",
        provider="deepseek",
        model="deepseek-chat",
        api_key_env="DEEPSEEK_API_KEY",
        base_url="https://api.deepseek.com",
        tool_mode="auto",
    )
    request = ProviderRequest(
        provider=ProviderType.DEEPSEEK,
        endpoint_style="chat.completions",
        path="/chat/completions",
        payload={
            "model": profile.model,
            "messages": [{"role": "user", "content": "find foo"}],
            "tools": [],
        },
    )
    calls = {"count": 0}

    def invoke_provider(provider_request, _profile, _api_key):
        calls["count"] += 1
        if calls["count"] == 1:
            return {
                "id": "resp-1",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "tool-1",
                                    "type": "function",
                                    "function": {
                                        "name": "search_codebase",
                                        "arguments": "{\"query\":\"foo\"}",
                                    },
                                }
                            ],
                        }
                    }
                ],
            }
        assert provider_request.payload["messages"][-1]["role"] == "tool"
        return {
            "id": "resp-2",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "done",
                    }
                }
            ],
        }

    loop = ProviderToolLoop(
        profile=profile,
        run_id=run.run_id,
        store=store,
        invoke_provider=invoke_provider,
        tool_registry=FakeRegistry(),
        memory=memory,
    )
    result = loop.run(request, api_key="fake")

    assert result.final_text == "done"
    assert result.rounds == 2
    assert calls["count"] == 2
    snapshot = memory.export_state()
    assert any(event["role"] == "tool" for event in snapshot["events"])
    assert any(trace.kind.value == "tool" for trace in store.list_traces(run.run_id))
