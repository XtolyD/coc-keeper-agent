# -*- coding: utf-8 -*-
from coc_keeper.agent.state import Session
from coc_keeper.agent.tools import make_dispatcher
from coc_keeper.character import Attributes
from coc_keeper.skill_data import SKILL_BASES, base_value, canonicalize
from coc_keeper.skills import get_skill_catalog


def test_skill_core_and_playbook_cover_all_canonical_skills():
    catalog = get_skill_catalog()
    cards = catalog.cards()
    assert len(cards) == 110
    canonical = {card.canonical_name for card in cards}
    assert len(canonical) == 55
    assert set(SKILL_BASES) == canonical
    assert all(catalog.get(card.canonical_name) is not None for card in cards)
    assert all(catalog.get(card.canonical_name).playbook for card in cards)


def test_canonicalize_aliases_and_specializations():
    assert canonicalize("取悦") == "魅惑"
    assert canonicalize("电子学 Ω") == "电子学"
    assert canonicalize("动物驯养") == "驯兽"
    assert canonicalize("表演") == "艺术/手艺"
    assert canonicalize("手枪") == "射击（手枪）"
    assert canonicalize("斗殴") == "格斗（斗殴）"
    assert canonicalize("数学") == "科学"
    assert canonicalize("生存：") == "生存"


def test_generated_base_values_match_skill_catalog():
    attrs = Attributes(DEX=60, EDU=70)
    assert base_value("闪避", attrs) == 30
    assert base_value("母语", attrs) == 70
    assert base_value("会计", attrs) == 5
    assert base_value("格斗（斗殴）", attrs) == 25
    assert base_value("手枪", attrs) == 20


def test_catalog_get_and_search_alias():
    catalog = get_skill_catalog()
    assert catalog.get("表演").canonical_name == "艺术/手艺"
    assert catalog.get("手枪").canonical_name == "射击（手枪）"
    hits = catalog.search("取悦")
    assert hits and hits[0][0].canonical_name == "魅惑"
    hits = catalog.search("会计")
    assert hits and hits[0][0].canonical_name == "会计"


def test_resolve_action_returns_kp_advisory_candidates():
    catalog = get_skill_catalog()
    skills = {"侦查": 65, "聆听": 40, "会计": 50, "说服": 60, "锁匠": 45, "艺术/手艺": 55}
    cases = {
        "我仔细搜查房间": "侦查",
        "我偷听门后": "聆听",
        "我开锁": "锁匠",
        "我试图说服守卫": "说服",
        "我检查账本": "会计",
        "我表演戏剧": "艺术/手艺",
    }
    for action, expected in cases.items():
        candidates = catalog.resolve_action(action, skills)
        assert candidates, action
        assert candidates[0]["skill"] == expected, (action, candidates)
        assert candidates[0]["confidence"] >= 0.9
    assert catalog.resolve_action("我打开门", skills) == []


def test_dispatcher_resolve_and_get_skill_tools():
    session = Session()
    dispatch = make_dispatcher(session)
    resolved = dispatch("resolve_skill", {"action": "我仔细搜查房间"})
    assert resolved["candidates"][0]["skill"] == "侦查"
    skill = dispatch("get_skill", {"name": "取悦"})
    assert skill["canonical_name"] == "魅惑"
    assert skill["sections"]["description"]
    search = dispatch("search_skills", {"query": "社交", "limit": 3})
    assert search["skills"]
    assert all("summary" in item for item in search["skills"])


def test_roll_skill_check_canonicalizes_specialization():
    session = Session()
    session.investigator.skills["艺术/手艺"] = 60
    dispatch = make_dispatcher(session, rng=__import__("random").Random(1))
    result = dispatch("roll_skill_check", {"skill": "表演"})
    assert result["检定项"] == "艺术/手艺"
    assert result["数值"] == 60


def test_roll_skill_check_returns_candidates_for_unknown_skill():
    session = Session()
    dispatch = make_dispatcher(session)
    result = dispatch("roll_skill_check", {"skill": "不存在的技能"})
    assert "error" in result
    assert result["candidates"] == []
