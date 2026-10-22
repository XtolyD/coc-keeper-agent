# -*- coding: utf-8 -*-
from coc_keeper.agent.state import Session
from coc_keeper.agent.tool_registry import ToolRegistry
from coc_keeper.agent.tool_schemas import TOOLS_SCHEMA
from coc_keeper.agent.tools import TOOLS_SCHEMA as TOOLS_SCHEMA_COMPAT


def test_tool_registry_exposes_schema_and_dispatches():
    registry = ToolRegistry(Session())
    names = [item["function"]["name"] for item in registry.schema]
    assert registry.schema is TOOLS_SCHEMA
    assert TOOLS_SCHEMA_COMPAT is TOOLS_SCHEMA
    assert {"get_character", "resolve_skill", "search_skills", "get_skill"} <= set(names)
    assert registry.dispatch("get_character", {})["name"]
