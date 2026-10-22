# -*- coding: utf-8 -*-
from coc_keeper.agent.llm import LLMResponse
from coc_keeper.agent.memory import Memory


def test_memory_trims_complete_rounds_only():
    memory = Memory("system", limit=4)
    memory.add_user("第一回合")
    memory.add_assistant(LLMResponse(tool_calls=[{"id": "one", "name": "luck_check", "arguments": "{}"}]))
    memory.add_tool_result("one", {"成功": True})
    memory.add_assistant(LLMResponse(content="第一回合结束"))
    memory.add_user("第二回合")
    messages = memory.messages()
    assert messages == [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "第二回合"},
    ]


def test_memory_preserves_reasoning_content_for_tool_roundtrip():
    memory = Memory("system")
    memory.add_assistant(LLMResponse(
        reasoning_content="需要先检查角色卡。",
        tool_calls=[{"id": "one", "name": "get_character", "arguments": "{}"}],
    ))
    message = memory.messages()[1]
    assert message["reasoning_content"] == "需要先检查角色卡。"
    assert message["tool_calls"][0]["function"]["name"] == "get_character"


def test_memory_drops_legacy_tool_rounds_without_reasoning_content():
    memory = Memory("system")
    memory.restore([
        {"role": "user", "content": "检查房间"},
        {"role": "assistant", "content": "", "tool_calls": [{
            "id": "legacy", "type": "function",
            "function": {"name": "roll_skill_check", "arguments": "{}"},
        }]},
        {"role": "tool", "tool_call_id": "legacy", "content": "{\"成功\": true}"},
        {"role": "assistant", "content": "你找到了钥匙。"},
    ], require_reasoning_content=True)
    assert memory.snapshot() == [
        {"role": "user", "content": "检查房间"},
        {"role": "assistant", "content": "你找到了钥匙。"},
    ]
