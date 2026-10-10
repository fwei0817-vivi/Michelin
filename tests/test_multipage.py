"""A menu over several photos (or a PDF) is read as ONE menu (test-menus/cafe-mandarin-p*.jpg)."""

import base64
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from michelin import api
from michelin.parse import vision

PNG = b"\x89PNG\r\n\x1a\nfake"


class FakeHTTP:
    def __init__(self, body):
        self.body, self.calls = body, []

    def post(self, url, json, headers, timeout):
        self.calls.append({"json": json})
        reply = {"choices": [{"message": {"content": self.body}}], "usage": {"cost": 0}}
        return SimpleNamespace(status_code=200, json=lambda: reply)


JPG = b"\xff\xd8\xff\xe0fake"
PAGE1 = {
    "restaurant_name": "Cafe Mandarin",
    "legend": "V Vegetarian",
    "dishes": [
        {"name_en": "Cucumber Salad", "price": 10, "section": "Cold Appetizers"},
        {"name_en": "Hot & Sour Soup", "price": 5, "marks": ["vegetarian"], "spicy": 1},
    ],
}
PAGE2 = {
    "restaurant_name": "",
    "legend": "VP Vegetarian Possible",
    "dishes": [
        # Printed again on page 2 (a "specials" box): one dish, marks kept together.
        {"name_en": "Hot & Sour Soup", "price": 5, "marks": ["gluten_free"], "section": "Soup"},
        {
            "name_en": "Kung Pao",
            "price": 18,
            "marks": ["vegetarian_possible"],
            "choices": [{"name_en": "Chicken"}, {"name_en": "Tofu"}],
        },
    ],
}


def test_pages_fit_in_one_call_and_merge(monkeypatch):
    calls = []

    def fake(pages, client=None):
        calls.append(len(pages))
        merged = {**PAGE1, "dishes": PAGE1["dishes"] + PAGE2["dishes"]}
        return merged, "m"

    monkeypatch.setattr(vision, "_ask", fake)
    dishes, name, _used, _legend = vision.read_menu_pages([(PNG, "image/png"), (JPG, "image/jpeg")])
    assert calls == [2]
    names = [d.name_en for d in dishes]
    assert names == ["Cucumber Salad", "Hot & Sour Soup", "Kung Pao (Chicken)", "Kung Pao (Tofu)"]
    soup = dishes[1]
    assert {m.value for m in soup.menu_marks} == {"vegetarian", "gluten_free"}
    assert soup.menu_section == "Soup" and dishes[0].menu_section == "Cold Appetizers"
    assert name == "Cafe Mandarin"


def test_big_pages_go_one_call_each_then_merge(monkeypatch):
    replies = [(PAGE1, "m"), (PAGE2, "m")]
    calls = []

    def fake(pages, client=None):
        calls.append(len(pages))
        return replies.pop(0)

    monkeypatch.setattr(vision, "_ask", fake)
    monkeypatch.setattr(vision, "ONE_CALL_BYTES", 10)
    dishes, name, _, legend = vision.read_menu_pages([(PNG, "image/png"), (JPG, "image/jpeg")])
    assert calls == [1, 1]
    assert [d.name_en for d in dishes].count("Hot & Sour Soup") == 1
    assert legend == "V Vegetarian VP Vegetarian Possible" and name == "Cafe Mandarin"


def test_all_pages_go_in_one_request(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "o")
    http = FakeHTTP(json.dumps({"restaurant_name": "", "dishes": []}))
    vision.read_menu_pages([(PNG, "image/png"), (JPG, "image/jpeg"), (PNG, "image/png")], http)
    content = http.calls[0]["json"]["messages"][0]["content"]
    assert [c["type"] for c in content] == ["text", "image_url", "image_url", "image_url"]
    assert content[2]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert "3 photos are pages of ONE menu" in content[0]["text"]


def test_api_reads_several_pages_as_one_menu(monkeypatch):
    seen = []

    def fake(pages, client=None, key=None):
        seen.append([m for _, m in pages])
        return vision.rows_to_dishes(PAGE1["dishes"] + PAGE2["dishes"]), "Cafe", "m", ""

    monkeypatch.setattr(vision, "configured", lambda: True)
    monkeypatch.setattr(vision, "read_menu_pages", fake)
    enc = [base64.b64encode(x).decode() for x in (PNG, JPG)]
    r = TestClient(api.app).post("/api/menu/parse", json={"images_base64": enc})
    assert r.status_code == 200, r.text
    assert seen == [["image/png", "image/jpeg"]]
    assert "Read 2 pages as one menu." in r.json()["notice"]
    assert len(r.json()["dishes"]) == 4
    bad = base64.b64encode(b"GIF89a").decode()
    r = TestClient(api.app).post("/api/menu/parse", json={"images_base64": [bad]})
    assert r.status_code == 422 and "PDF" in r.json()["detail"]


@pytest.mark.skipif(not shutil.which("pdftoppm"), reason="needs poppler-utils")
def test_a_pdf_becomes_one_page_image_each():
    pdf = (Path(__file__).parents[1] / "test-menus/cafe-mandarin.pdf").read_bytes()
    pages = api._pdf_pages(pdf)
    assert len(pages) == 4 and all(m == "image/jpeg" and p[:3] == b"\xff\xd8\xff" for p, m in pages)
    assert all(len(p) < 1_500_000 for p, _ in pages)


def test_the_printed_name_keeps_its_versions_and_price():
    from michelin.parse.vision import rows_to_dishes

    rows = [
        {"name_en": "Sesame Chicken or Tofu", "price": 18},
        {
            "name_en": "Yu Xiang Pork",
            "price": 18,
            "choices": [
                {"name_en": "Chicken", "price": 18},
                {"name_en": "Beef", "price": 20},
                {"name_en": "Tofu", "price": 18},
            ],
        },
        {
            "name_en": "Mongolian Beef",
            "price": 18,
            "choices": [
                {"name_en": "Chicken", "price": 18},
                {"name_en": "Beef", "price": 20},
                {"name_en": "Shrimp", "price": 22},
            ],
        },
    ]
    got = {d.name_en: d.price for d in rows_to_dishes(rows)}
    assert got["Sesame (Chicken)"] == 18 and got["Sesame (Tofu)"] == 18
    assert got["Yu Xiang (Pork)"] == 18 and got["Yu Xiang (Beef)"] == 20
    assert got["Mongolian (Beef)"] == 18 and got["Mongolian (Shrimp)"] == 22


# --- choice prices: base + each option's own printed surcharge ---------------------------

import copy

READ = json.loads((Path(__file__).parent / "fixtures" / "cafe_mandarin_4p_read.json").read_text())

MAIN_CLASSICS = {
    "Yu Xiang (Pork)": 18,
    "Yu Xiang (Chicken)": 18,
    "Yu Xiang (Beef)": 20,
    "Yu Xiang (Shrimp)": 22,
    "Yu Xiang (Tofu)": 18,
    "Kung Pao (Chicken)": 18,
    "Kung Pao (Beef)": 20,
    "Kung Pao (Shrimp)": 22,
    "Kung Pao (Tofu)": 18,
    "Broccoli (Chicken)": 18,
    "Broccoli (Beef)": 20,
    "Broccoli (Shrimp)": 22,
    "Broccoli (Tofu)": 18,
    "Cumin (Lamb)": 18,
    "Cumin (Chicken)": 18,
    "Cumin (Beef)": 18,
    "Cumin (Shrimp)": 22,
    "Cumin (Tofu)": 18,
    "Mongolian (Chicken)": 18,
    "Mongolian (Beef)": 18,
    "Mongolian (Shrimp)": 22,
    "Mongolian (Tofu)": 18,
    "Sesame (Chicken)": 18,
    "Sesame (Tofu)": 18,
}


def _prices(rows):
    from michelin.parse.vision import rows_to_dishes

    return {d.name_en: d.price for d in rows_to_dishes(rows)}


def _row(name):
    return next(r for r in copy.deepcopy(READ["dishes"]) if r["name_en"] == name)


def test_saved_four_page_read_prices_every_main_classic_as_printed():
    got = _prices(READ["dishes"])
    assert {k: got.get(k) for k in MAIN_CLASSICS} == MAIN_CLASSICS
    assert got["Sichuan Boiled in Chili Oil (Beef)"] == 24
    assert got["Sichuan Boiled in Chili Oil (Fish)"] == 28
    assert got["Lo Mein (Beef)"] == 18 and got["Lo Mein (Combo)"] == 20
    assert not any("(Fish)" in n for n in got if n.startswith("Fluke"))  # styles, not proteins


def test_surcharges_shifted_onto_the_wrong_options_are_repaired():
    """Yukino's import: 'Pork 18, Chicken 20, Beef 22, Shrimp 18' for 'Beef +$2 | Shrimp +$4'."""
    row = _row("Yu Xiang Pork")
    for c, (wrong, up) in zip(
        row["choices"], [(18, ""), (20, "+$2"), (22, "+$4"), (18, ""), (18, "")]
    ):
        c["price"], c["upcharge"] = wrong, up
    got = _prices([row])
    assert [got[f"Yu Xiang ({o})"] for o in ("Pork", "Chicken", "Beef", "Shrimp", "Tofu")] == [
        18,
        18,
        20,
        22,
        18,
    ]


def test_choice_line_in_the_description_also_wins():
    row = _row("Kung Pao Chicken")
    row.pop("choice_text")
    row["description"] = "Scallion | Peanut\nChoice of Chicken | Beef +$2 | Shrimp +$4 | Tofu"
    for c, wrong in zip(row["choices"], [20, 22, 18, 18]):
        c["price"], c["upcharge"] = wrong, ""
    got = _prices([row])
    assert [got[f"Kung Pao ({o})"] for o in ("Chicken", "Beef", "Shrimp", "Tofu")] == [
        18,
        20,
        22,
        18,
    ]


def test_each_options_own_upcharge_token_without_a_choice_line():
    row = _row("Cumin Lamb")
    row.pop("choice_text")
    for c in row["choices"]:
        c["price"] = 99
    got = _prices([row])
    assert got["Cumin (Beef)"] == 18 and got["Cumin (Shrimp)"] == 22 and got["Cumin (Lamb)"] == 18


def test_paired_prices_split_by_the_chinese_name():
    row = {
        "name_en": "Sichuan Boiled Beef in Chili Oil",
        "name_zh": "水煮牛 / 鱼",
        "price": 24,
        "price_text": "$24 / $28",
    }
    got = _prices([row])
    assert got == {
        "Sichuan Boiled in Chili Oil (Beef)": 24,
        "Sichuan Boiled in Chili Oil (Fish)": 28,
    }
