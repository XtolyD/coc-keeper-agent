# -*- coding: utf-8 -*-
import random

import pytest

from coc_keeper.character import (
    allocate_skill_points, base_skill_values, generate_character_candidates,
    skill_point_budget, skill_points_spent,
)
from coc_keeper.character_store import CharacterStore


def test_generate_five_character_candidates():
    candidates = generate_character_candidates("艾琳", 28, rng=random.Random(1920))
    assert len(candidates) == 5
    assert all(candidate.name == "艾琳" for candidate in candidates)
    assert len({candidate.attributes.STR for candidate in candidates}) > 1


def test_allocate_skill_points_and_budget():
    sheet = generate_character_candidates(rng=random.Random(7), count=1)[0]
    bases = base_skill_values(sheet.attributes)
    allocate_skill_points(sheet, {"侦查": bases["侦查"] + 20, "聆听": bases["聆听"] + 10})
    assert skill_points_spent(sheet) == 30
    assert skill_point_budget(sheet.attributes) == sheet.attributes.EDU * 4 + sheet.attributes.INT * 2


def test_allocate_skill_points_rejects_overspend():
    sheet = generate_character_candidates(rng=random.Random(3), count=1)[0]
    with pytest.raises(ValueError, match="超出预算"):
        allocate_skill_points(sheet, {name: 100 for name in base_skill_values(sheet.attributes)})


def test_character_store_is_permanent(tmp_path):
    store = CharacterStore(tmp_path / "characters")
    sheet = generate_character_candidates("永久角色", rng=random.Random(8), count=1)[0]
    record = store.create(sheet)
    restored = CharacterStore(tmp_path / "characters").get(record.id)
    assert restored.sheet.name == "永久角色"
    assert restored.to_dict()["permanent"] is True
    restored.sheet.hp -= 2
    store.save(restored.id, restored.sheet)
    assert store.get(restored.id).sheet.hp == restored.sheet.hp
