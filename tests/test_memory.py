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
