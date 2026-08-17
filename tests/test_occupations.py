# -*- coding: utf-8 -*-
import random

import pytest

from coc_keeper.character import (
    allocate_occupation_points, base_skill_values,
    generate_character_candidates,
)
from coc_keeper.occupations import (
    get_occupation, interest_point_budget, list_occupations,
    occupation_point_budget, validate_occupation_skills,
)


def make_sheet():
    return generate_character_candidates(rng=random.Random(1920), count=1)[0]


def selected_skills(occupation):
    selected = list(occupation.fixed_skills)
    for group in occupation.choice_groups:
        selected.extend([skill for skill in group.skills if skill not in selected][:group.count])
    available = [name for name in base_skill_values(make_sheet().attributes) if name not in selected and name != "克苏鲁神话"]
    selected.extend(available[:occupation.free_choice_count])
    return selected


def test_catalog_and_occupation_formulas():
    assert len(list_occupations()) == 229
    sheet = make_sheet()
    accountant = get_occupation(2)
    detective = get_occupation(6)
    assert occupation_point_budget(sheet.attributes, accountant) == sheet.attributes.EDU * 4
    assert occupation_point_budget(sheet.attributes, detective) == sheet.attributes.EDU * 2 + max(sheet.attributes.STR, sheet.attributes.DEX) * 2
    assert interest_point_budget(sheet.attributes) == sheet.attributes.INT * 2


def test_occupation_selection_and_dual_point_pools():
    sheet = make_sheet()
    occupation = get_occupation(2)
    selected = selected_skills(occupation)
    validate_occupation_skills(occupation, selected)
    allocate_occupation_points(
        sheet, occupation.id, selected,
        {"信用评级": occupation.credit_min, "会计": 10},
        {"急救": 10},
    )
    assert sheet.occupation_name == occupation.name
    assert sheet.skills["信用评级"] == occupation.credit_min
    assert sheet.skills["会计"] == base_skill_values(sheet.attributes)["会计"] + 10
    assert sheet.skills["急救"] == base_skill_values(sheet.attributes)["急救"] + 10


def test_occupation_rules_reject_invalid_allocations():
    occupation = get_occupation(2)
    selected = selected_skills(occupation)
    sheet = make_sheet()
    non_main = next(name for name in base_skill_values(sheet.attributes) if name not in selected and name != "克苏鲁神话")
    with pytest.raises(ValueError, match="只能分配给本职技能"):
        allocate_occupation_points(sheet, occupation.id, selected, {"信用评级": occupation.credit_min, non_main: 1}, {})
    with pytest.raises(ValueError, match="达到"):
        allocate_occupation_points(sheet, occupation.id, selected, {"信用评级": occupation.credit_min - 1}, {})


def test_main_and_non_main_caps_are_distinct():
    occupation = get_occupation(2)
    selected = selected_skills(occupation)
    sheet = make_sheet()
    bases = base_skill_values(sheet.attributes)
    main = next(name for name in selected if name != "信用评级" and bases[name] < 70)
    non_main = next(name for name in bases if name not in selected and name != "克苏鲁神话" and bases[name] < 60)
    with pytest.raises(ValueError, match="本职技能上限 70"):
        allocate_occupation_points(
            sheet, occupation.id, selected,
            {"信用评级": occupation.credit_min, main: 70 - bases[main]},
            {main: 1},
        )
    with pytest.raises(ValueError, match="非本职技能上限 60"):
        allocate_occupation_points(
            sheet, occupation.id, selected,
            {"信用评级": occupation.credit_min},
            {non_main: 61 - bases[non_main]},
        )
