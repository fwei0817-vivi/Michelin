"""LLM matcher with a fake client: no network, no credentials."""

import json
from types import SimpleNamespace

from michelin.parse.knowledge import label_dish
from michelin.parse.matcher import cache_key, load_cache, match_names
from michelin.schemas import Allergen, Dish, EvidenceTier


class FakeClaude:
    def __init__(self, answers, stop_reason="end_turn"):
        self.answers, self.stop_reason, self.calls = answers, stop_reason, []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        body = json.dumps(
            {"matches": [{"dish": i, "kb_id": a} for i, a in enumerate(self.answers)]}
        )
        return SimpleNamespace(
            stop_reason=self.stop_reason, content=[SimpleNamespace(type="text", text=body)]
        )


def dish(dish_id, name_en, description=None):
    return Dish(id=dish_id, name_en=name_en, price=10.0, description_raw=description)


def test_only_unrecognized_names_are_sent_and_answers_are_stored(tmp_path):
    cache = tmp_path / "matches.json"
    menu = [dish("a", "Kung Pao Chicken"), dish("b", "Spicy Tofu w/ Ground Pork")]
    fake = FakeClaude(["mapo_tofu"])
    assert match_names(menu, call_api=True, client=fake, cache_path=cache) == {"b": "mapo_tofu"}
    sent = fake.calls[0]["messages"][0]["content"]
    assert "Spicy Tofu" in sent and "Kung Pao" not in sent
    stored = load_cache(cache)["matches"][cache_key(menu[1])]
    assert stored["kb_id"] == "mapo_tofu" and stored["reviewed"] is False


def test_stored_answer_is_reused_without_calling_again(tmp_path):
    cache = tmp_path / "matches.json"
    menu = [dish("b", "Spicy Tofu w/ Ground Pork")]
    match_names(menu, call_api=True, client=FakeClaude(["mapo_tofu"]), cache_path=cache)
    again = FakeClaude(["vegetable_lo_mein"])
    assert match_names(menu, call_api=True, client=again, cache_path=cache) == {"b": "mapo_tofu"}
    assert again.calls == []


def test_no_api_call_unless_enabled(tmp_path, monkeypatch):
    monkeypatch.delenv("MICHELIN_LLM_MATCH", raising=False)
    fake = FakeClaude(["mapo_tofu"])
    menu = [dish("b", "Spicy Tofu w/ Ground Pork")]
    assert match_names(menu, client=fake, cache_path=tmp_path / "m.json") == {}
    assert fake.calls == []


def test_none_and_refusal_match_nothing(tmp_path):
    menu = [dish("b", "Chef's Special Clay Pot")]
    assert match_names(menu, call_api=True, client=FakeClaude(["none"]),
                       cache_path=tmp_path / "1.json") == {}  # fmt: skip
    refused = FakeClaude(["mapo_tofu"], stop_reason="refusal")
    assert match_names(menu, call_api=True, client=refused, cache_path=tmp_path / "2.json") == {}


def test_request_constrains_answers_to_catalog_ids(tmp_path):
    fake = FakeClaude(["none"])
    match_names([dish("b", "Mystery")], call_api=True, client=fake, cache_path=tmp_path / "m.json")
    call = fake.calls[0]
    schema = call["output_config"]["format"]["schema"]
    allowed = schema["properties"]["matches"]["items"]["properties"]["kb_id"]["enum"]
    assert "mapo_tofu" in allowed and "none" in allowed
    assert call["model"] == "claude-opus-5-5"
    assert call["fallbacks"] == "default"


def test_suggested_match_labels_dish_and_asks_staff_to_confirm():
    d = dish("b", "Spicy Tofu w/ Ground Pork", "soft tofu, chili")
    out = label_dish(d, suggested="mapo_tofu")
    assert out.match == "mapo_tofu"
    assert out.dish.is_vegetarian is False
    assert any("confirm it is the same dish" in q for q in out.dish.confirm_with_staff)


def test_printed_evidence_still_applies_after_a_wrong_suggestion():
    # Even if the model picked a meatless entry, printed shrimp keeps blocking shellfish.
    d = dish("b", "Shrimp Lo Mein", "egg noodles, shrimp")
    out = label_dish(d, suggested="vegetable_lo_mein")
    shellfish = {f.tier for f in out.dish.allergens if f.allergen == Allergen.SHELLFISH}
    assert EvidenceTier.MENU in shellfish
    assert out.dish.is_vegetarian is False
