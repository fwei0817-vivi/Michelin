"""Do a dish's English and Chinese names describe the same dish? (QA r20 WM-1)

A misread menu can pair one row's English with another row's Chinese ("Pan Fried Pork Bun"
next to 巧手潮州蒸粉果). Code compares what each name states: the main protein and the kind
of dish. One name merely leaving something out is normal ("Hunan Beef" / 小炒黄牛肉); a
clash is when each name states a DIFFERENT thing of the same kind (pork vs egg custard, bun
vs dumpling, soup vs cake). A clash makes the dish's allergen facts uncertain, so an
allergic diner is asked, never told it is fine."""

import re

PROTEIN = {
    "pork": (
        r"pork|\bham\b|bacon|char siu|spare ?ribs?|\bspam\b",
        ["豬", "猪", "叉燒", "叉烧", "排骨", "火腿", "腊肉", "臘肉", "腊味", "臘味"],
    ),
    "beef": (r"beef|oxtail|brisket", ["牛"]),
    "chicken": (r"chicken", ["雞", "鸡"]),
    "duck": (r"duck", ["鴨", "鸭"]),
    "lamb": (r"lamb|mutton", ["羊"]),
    "shrimp": (r"shrimp|prawn", ["蝦", "虾"]),
    "crab": (r"\bcrab", ["蟹"]),
    "fish": (r"\bfish\b|\bcod\b|\bbass\b|salmon|fluke|flounder|tilapia", ["魚", "鱼"]),
    "egg": (r"\beggs?\b|custard|omelet", ["蛋"]),
}
FORM = {
    "bun": (r"\bbuns?\b|\bbao\b", ["包"]),
    "dumpling": (
        r"dumpling|potsticker|wonton|siu mai|shumai|\bgow\b",
        ["餃", "饺", "粉果", "小籠", "小笼", "燒賣", "烧卖", "雲吞", "云吞", "餛飩", "馄饨"],
    ),
    "cake": (r"\bcake\b", ["糕"]),
    "soup": (r"\bsoup\b(?! dumpling)", ["湯", "汤", "羹"]),
    "noodle": (
        r"noodle|\bmein\b|chow fun|ho fun|mei fun",
        ["麵", "面", "河粉", "米粉", "炒河", "牛河"],
    ),
    "congee": (r"congee|porridge", ["粥"]),
    "tart": (r"\btarts?\b", ["撻", "挞"]),
    "roll": (
        r"rice roll|rice noodle roll|cheung fun|spring roll",
        ["腸粉", "肠粉", "春卷", "春捲"],
    ),
}
_ZH = re.compile(r"[\u4e00-\u9fff]")
# words that name a flavour, not an ingredient: 鱼香 (no fish), 鸡蛋 (egg, not chicken),
# 小笼包 / 灌汤包 are dumplings
_STRIP = ["魚香", "鱼香", "雞蛋", "鸡蛋", "籠包", "笼包", "湯包", "汤包"]
_EN_STRIP = re.compile(r"yu ?xiang|fish[- ]fragrant", re.IGNORECASE)


def _stated(en: str, zh: str, table: dict) -> tuple[set, set]:
    z = zh
    for w in _STRIP:
        z = z.replace(w, "笼" if "包" in w else "")
    e = _EN_STRIP.sub("", en)
    if any(w in zh for w in ("鸡蛋", "雞蛋")):
        z += "蛋"
    in_en = {k for k, (pat, _) in table.items() if re.search(pat, e, re.IGNORECASE)}
    in_zh = {k for k, (_, chars) in table.items() if any(c in z for c in chars)}
    if table is FORM and any(w in zh for w in ("籠包", "笼包", "湯包", "汤包")):
        in_zh.add("dumpling")
    return in_en, in_zh


def mismatch(name_en: str | None, name_zh: str | None) -> list[str]:
    """What the two names state differently, as 'english-thing/chinese-thing' pairs (empty:
    no clash). Only full Chinese names (3+ characters) are compared."""
    en, zh = name_en or "", name_zh or ""
    if not en.strip() or len(_ZH.findall(zh)) < 3:
        return []
    out = []
    for table in (PROTEIN, FORM):
        a, b = _stated(en, zh, table)
        only_en, only_zh = a - b, b - a
        if only_en and only_zh:
            out += [f"{x}/{y}" for x in sorted(only_en) for y in sorted(only_zh)]
    return out
