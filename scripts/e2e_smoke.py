"""Drive the built app like a user (headless Chromium) and check the flows end to end.

    uv run uvicorn michelin.api:app --port 8000      # serves web/dist
    pip install playwright && playwright install chromium
    python scripts/e2e_smoke.py [--url http://127.0.0.1:8000/] [--shots /tmp/shots]

Exits non-zero when a check fails or the browser logs an error. Covers regressions:
per-diner notes before anyone is at the table, imports replacing or renaming the current
restaurant, dish counts that disagree, and the example group always hitting "No order fits".
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
import uuid
from pathlib import Path

from playwright.async_api import Page, async_playwright

FAILS: list[str] = []


def check(ok: bool, what: str) -> None:
    print(("PASS " if ok else "FAIL ") + what, flush=True)
    if not ok:
        FAILS.append(what)


async def settle(pg: Page, ms: int = 300) -> None:
    await pg.wait_for_load_state("networkidle")
    try:
        await pg.wait_for_function("!document.querySelector('.spin')", timeout=30000)
    except Exception:  # noqa: BLE001, S110 - a spinner that never clears is caught by the checks
        pass
    await pg.wait_for_timeout(ms)


async def heading(pg: Page) -> str:
    return (await pg.locator("main h1, main h2").first.inner_text()).strip()


def dialog(pg: Page):
    return pg.locator("[role=dialog]").last


async def close_dialog(pg: Page) -> None:
    await dialog(pg).get_by_role("button", name="Close").first.click()
    await settle(pg)


async def selected(pg: Page) -> str:
    return await dialog(pg).locator("select").first.evaluate("e => e.options[e.selectedIndex].text")


async def plan_counts(pg: Page) -> tuple[int, int, int]:
    h1 = await pg.locator("main h1").first.inner_text()
    bill = await pg.locator(".bill h2").inner_text()
    cards = await pg.locator(".dish-card").count()
    return int(re.search(r"\d+", h1)[0]), int(re.search(r"\d+", bill)[0]), cards


async def step(name, coro):
    try:
        await coro
    except Exception as e:  # noqa: BLE001 - keep going so one broken flow does not hide the others
        check(False, f"{name}: {type(e).__name__}: {str(e).splitlines()[0]}")


async def run(url: str, shots: Path) -> None:
    shots.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        pg = await browser.new_page(viewport={"width": 1280, "height": 900})
        pg.set_default_timeout(15000)
        errors: list[str] = []
        pg.on(
            "console",
            lambda m: (
                errors.append(f"console: {m.text}")
                if m.type == "error" and "503" not in m.text
                else None
            ),
        )
        pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        pg.on(
            "response",
            lambda r: (
                errors.append(f"HTTP {r.status} {r.request.method} {r.url}")
                if r.status >= 500 and not (r.status == 503 and "/api/menu/parse" in r.url)
                else None
            ),
        )
        await pg.goto(url)
        await pg.wait_for_selector("main h1")
        await settle(pg)
        check(await heading(pg) == "Choose a menu", "starts on the menu step")
        await pg.screenshot(path=str(shots / "01_choose_menu.png"), full_page=True)

        async def menu_browser():
            await pg.get_by_role("button", name="View menu").click()
            await settle(pg)
            names = await dialog(pg).locator("select").first.locator("option").all_inner_texts()
            check(len(names) >= 4, f"restaurant list: {names}")
            check(
                await dialog(pg).locator(".not-for").count() == 0,
                "no 'not for' notes without diners (bug 1)",
            )
            for slug in ["chili", "sample_sichuan", "atlas_kitchen", "cafe_china"]:
                await dialog(pg).locator("select").first.select_option(slug)
                await settle(pg)
                rows = await dialog(pg).locator(".menu-row").count()
                check(rows > 0, f"switch to {slug}: {await selected(pg)}, {rows} dishes")
            await dialog(pg).get_by_label("Search dishes or ingredients").fill("tofu")
            await settle(pg)
            check(await dialog(pg).locator(".menu-row").count() > 0, "search filters the menu")
            await dialog(pg).get_by_label("Search dishes or ingredients").fill("")

        async def imports():
            before = await dialog(pg).locator("select").first.locator("option").all_inner_texts()
            await dialog(pg).get_by_role("button", name="Import menu").click()
            await dialog(pg).get_by_label("Use imported dishes").select_option("replace")
            await dialog(pg).get_by_label("New restaurant name").fill("test")
            await (
                dialog(pg)
                .get_by_label("Menu text")
                .fill("Garlic greens $12.95\nMapo Tofu $14.95\nSteamed rice $2.00")
            )
            await dialog(pg).get_by_role("button", name="Extract dishes").click()
            await settle(pg)
            check(
                "3 dishes found" in await dialog(pg).inner_text(), "text import extracts 3 dishes"
            )
            await dialog(pg).get_by_role("button", name="Add restaurant for review").click()
            await settle(pg)
            after = await dialog(pg).locator("select").first.locator("option").all_inner_texts()
            check(
                len(after) == len(before) + 1 and "Café China" in after,
                f"import adds a restaurant (bug 2): {after}",
            )
            check(
                await selected(pg) == "Café China",
                f"current restaurant unchanged after import (bug 3): {await selected(pg)}",
            )
            await pg.screenshot(path=str(shots / "02_import_new_restaurant.png"), full_page=True)
            await dialog(pg).get_by_role("button", name=re.compile("^Switch to test")).click()
            await settle(pg)
            check(
                (await selected(pg)).startswith("test"),
                f"explicit switch selects test: {await selected(pg)}",
            )
            check(await dialog(pg).locator(".menu-row").count() == 3, "test menu has its 3 dishes")
            await dialog(pg).locator("select").first.select_option("cafe_china")
            await settle(pg)
            check(
                await dialog(pg).locator(".menu-row").count() == 40,
                "Café China keeps its 40 dishes",
            )
            await dialog(pg).get_by_role("button", name="Import menu").click()
            await dialog(pg).locator("summary", has_text="assistant-prepared").click()
            prepared = dialog(pg).get_by_label("Prepared menu")
            opts = await prepared.locator("option").evaluate_all(
                "o => o.map(x => x.value).filter(Boolean)"
            )
            check(bool(opts), f"prepared inputs listed: {opts}")
            await prepared.select_option(opts[-1])
            await dialog(pg).get_by_role("button", name="Replay prepared response").click()
            await settle(pg)
            found = await dialog(pg).locator(".import-review h3").all_inner_texts()
            check(any("dishes found" in t for t in found), f"replay returns dishes: {found}")
            await dialog(pg).get_by_role("button", name="Add restaurant for review").click()
            await settle(pg)
            check(
                await selected(pg) == "Café China",
                f"replay keeps current restaurant: {await selected(pg)}",
            )

        await step("menu browser", menu_browser())
        await step("imports", imports())
        if await pg.locator("[role=dialog]").count():
            await close_dialog(pg)
        check(
            await pg.locator(".menu-choice h2").first.inner_text() == "Café China",
            "menu step still shows Café China",
        )

        async def table_and_plan():
            await pg.get_by_role("button", name="Continue with this menu").click()
            await settle(pg)
            check(await pg.locator(".not-for").count() == 0, "table step has no per-diner notes")
            await pg.get_by_label("Load a group").select_option("saved")
            await settle(pg)
            people = await pg.locator(".people-list li").count()
            total = (await pg.locator(".footer-total").inner_text()).splitlines()[0]
            check(people == 6, f"example group loads 6 people, budget {total}")
            await pg.get_by_role("button", name="Find dishes").click()
            await settle(pg, 800)
            check(
                await heading(pg) != "No order fits yet",
                f"example group gets a plan (bug 5): {await heading(pg)}",
            )
            h1, bill, cards = await plan_counts(pg)
            check(h1 == bill == cards, f"counts agree: heading {h1}, bill {bill}, cards {cards}")
            steps = await pg.locator(".steps li").all_inner_texts()
            current = await pg.locator(".steps li[aria-current=step]").inner_text()
            check(
                len(steps) == 3 and current.strip().endswith("Dishes"),
                f"stepper on the plan: {steps}",
            )
            await pg.get_by_role("button", name="Your table").click()
            target = int(await dialog(pg).locator("input").nth(1).input_value())
            await close_dialog(pg)
            check(h1 == target, f"dish count matches 'Dishes to order' ({h1} vs {target}) (bug 4)")
            await pg.screenshot(path=str(shots / "03_plan_example_group.png"), full_page=True)

        async def dish_edits():
            name = await pg.locator(".dish-card").first.locator("h2").inner_text()
            await pg.get_by_role("button", name=f"Keep {name}").click()
            check(
                await pg.get_by_role("button", name=f"Keep {name}").get_attribute("aria-pressed")
                == "true",
                f"keep {name}",
            )
            second = await pg.locator(".dish-card").nth(1).locator("h2").inner_text()
            await pg.get_by_role("button", name=f"Swap {second}").click()
            await settle(pg)
            await dialog(pg).locator("button:enabled", has_text="Swap in").first.click()
            await settle(pg, 800)
            titles = await pg.locator(".dish-card h2").all_inner_texts()
            check(
                second not in titles and name in titles,
                "swap replaces the dish and keeps the kept one",
            )
            third = await pg.locator(".dish-card").nth(2).locator("h2").inner_text()
            await pg.get_by_role("button", name=f"Remove {third}").click()
            await settle(pg, 800)
            check(
                third not in await pg.locator(".dish-card h2").all_inner_texts(), f"remove {third}"
            )
            await pg.locator(".change-notice").get_by_role("button", name="Undo").click()
            await settle(pg, 800)
            check(
                third in await pg.locator(".dish-card h2").all_inner_texts(), "undo brings it back"
            )
            await pg.get_by_role("button", name=re.compile("Something else in mind")).click()
            await settle(pg)
            await dialog(pg).locator("button:enabled", has_text="Add to order").first.click()
            await settle(pg, 800)
            check(await heading(pg) != "No order fits yet", "add a dish keeps a plan")
            h1, bill, cards = await plan_counts(pg)
            check(h1 == bill == cards, f"counts agree after edits: {h1}/{bill}/{cards}")
            await pg.get_by_role("button", name="View order ticket").click()
            await settle(pg)
            text = await dialog(pg).inner_text()
            check(f"{h1} dishes to share" in text, "order ticket shows the same dish count")
            await pg.screenshot(path=str(shots / "04_order_ticket.png"), full_page=True)
            await close_dialog(pg)

        async def diners_and_budget():
            await pg.get_by_role("button", name="Your table").click()
            await dialog(pg).get_by_role("button", name="Edit Kevin").click()
            await dialog(pg).get_by_role("button", name="Not eating tonight").click()
            await settle(pg, 800)
            await dialog(pg).get_by_role("button", name="Add a person").click()
            await dialog(pg).get_by_label("Name").fill("Zoe")
            await dialog(pg).get_by_role("button", name="peanuts").click()
            await dialog(pg).get_by_role("button", name="Use for this meal").click()
            await settle(pg, 800)
            await dialog(pg).get_by_role("button", name="Edit Tom").click()
            await dialog(pg).get_by_role("button", name="dairy").click()
            await dialog(pg).get_by_role("button", name="Use for this meal").click()
            await settle(pg, 800)
            people = await dialog(pg).locator(".people-list li").all_inner_texts()
            check(
                any("Zoe" in p for p in people) and not any("Kevin" in p for p in people),
                "add Zoe, remove Kevin",
            )
            check(any("Tom" in p and "dairy" in p for p in people), "edit Tom adds dairy")
            budget = dialog(pg).locator("input").first
            await budget.fill("40")
            await budget.press("Tab")
            await dialog(pg).get_by_role("button", name="Update dishes").click()
            await settle(pg, 1000)
            check(
                await heading(pg) != "No order fits yet",
                f"plan after people and budget edits: {await heading(pg)}",
            )
            notes = " ".join(await pg.locator(".not-for").all_inner_texts())
            check("Kevin" not in notes, "removed diner never appears in notes")
            check(
                "$40.00" in await pg.locator(".bill-budget").inner_text(), "per-person budget shown"
            )

        async def remember():
            await pg.locator("summary", has_text="Remember people").click()
            box = pg.locator("details", has_text="Remember people")
            await box.get_by_label("Profile scope").fill(f"e2e-{uuid.uuid4().hex[:6]}")
            await box.get_by_role("button", name="View history").click()
            await settle(pg)
            check(
                await box.get_by_role("alert").count() == 0
                and not any("pageerror" in e for e in errors),
                "history of an unsaved person is not an error",
            )
            await box.get_by_role("button", name="Save for future meals").click()
            await settle(pg)
            check("revision 1" in await box.inner_text(), "save person")
            await box.get_by_role("button", name="Save for future meals").click()
            await settle(pg)
            check("revision 2" in await box.inner_text(), "save again bumps revision")
            await box.get_by_role("button", name="View history").click()
            await settle(pg)
            check("History: 2 revisions" in await box.inner_text(), "history lists revisions")
            await box.get_by_role("button", name="Load saved preferences").click()
            await settle(pg, 800)
            check("Applied saved preferences" in await box.inner_text(), "load saved preferences")
            await pg.locator("summary", has_text="Remember people").click()

        async def no_fit():
            await pg.get_by_role("button", name="Your table").click()
            budget = dialog(pg).locator("input").first
            await budget.fill("10")
            await budget.press("Tab")
            await dialog(pg).get_by_role("button", name="Update dishes").click()
            await settle(pg, 1000)
            check(await heading(pg) == "No order fits yet", "tiny budget shows the no-fit screen")
            await pg.screenshot(path=str(shots / "05_no_fit.png"), full_page=True)
            apply = pg.get_by_role("button", name=re.compile("Apply"))
            check(await apply.count() > 0, "no-fit offers a change")
            await apply.first.click()
            await settle(pg, 1000)
            check(await heading(pg) != "No order fits yet", "applying the suggestion gives a plan")

        async def switch_and_empty():
            await pg.locator(".topbar").get_by_role("button", name="Menu", exact=True).click()
            await dialog(pg).locator("select").first.select_option("chili")
            await settle(pg)
            await close_dialog(pg)
            check(
                await pg.locator(".menu-choice h2").first.inner_text() == "CHILI",
                "explicit switch to CHILI",
            )
            await pg.get_by_role("button", name="Continue with this menu").click()
            await pg.get_by_label("Load a group").select_option("new")
            await settle(pg)
            check(
                await pg.locator(".not-for, .dish-card").count() == 0,
                "empty table shows no dishes or notes",
            )
            await pg.screenshot(path=str(shots / "06_empty_table.png"), full_page=True)

        for name, fn in [
            ("table and plan", table_and_plan),
            ("dish edits", dish_edits),
            ("diners and budget", diners_and_budget),
            ("remember people", remember),
            ("no fit", no_fit),
            ("switch and empty", switch_and_empty),
        ]:
            await step(name, fn())
            while await pg.locator("[role=dialog]").count():
                await close_dialog(pg)

        await step("demo flow", demo(browser, url, shots, errors))
        for e in errors:
            check(False, e)
        await browser.close()


SKY = """Eggplant with Garlic Sauce $15.50
Mapo Tofu $14.95
Kung Pao Chicken $16.95
Dry Fried String Beans $14.50
Sauteed Pea Shoots with Garlic $15.95
Di San Xian $13.95
Hot and Sour Soup $6.50
Dan Dan Noodles $11.95
Fish Fillet in Hot Chili Oil $24.95
Twice Cooked Pork $17.95
Cumin Lamb $19.95
Smashed Cucumber Salad $7.95
Scallion Pancake $6.95
Vegetable Lo Mein $12.95
Steamed Rice $2.00"""

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360f8cf00000301010018dd8db00000000049454e44ae426082"
)


async def demo(browser, url: str, shots: Path, errors: list[str]) -> None:
    """The reference demo, step by step: photo-first menu, table of six, dishes, no-fit, ticket."""
    pg = await browser.new_page(viewport={"width": 1280, "height": 900})
    pg.set_default_timeout(15000)
    pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    await pg.goto(url)
    await pg.wait_for_selector("main h1")
    await settle(pg)
    text = await pg.locator("main").inner_text()
    check(
        "Have the menu in front of you?" in text and "Or use a saved menu" in text,
        "photo-first menu step",
    )
    check(await pg.get_by_role("button", name="Take a photo").count() == 1, "Take a photo button")
    await pg.screenshot(path=str(shots / "step1_choose_menu.png"), full_page=True)

    # A photo with no reader configured: a clear message, not a crash.
    await pg.get_by_label("Upload a menu photo").set_input_files(
        {"name": "menu.png", "mimeType": "image/png", "buffer": PNG}
    )
    await settle(pg)
    alert = await dialog(pg).get_by_role("alert").all_inner_texts()
    check(bool(alert), f"photo without a reader explains itself: {alert}")
    await close_dialog(pg)

    await pg.get_by_role("button", name="Or paste the menu text").click()
    await dialog(pg).get_by_label("New restaurant name").fill("Sky Pavilion")
    await dialog(pg).get_by_label("Menu text").fill(SKY)
    await dialog(pg).get_by_role("button", name="Extract dishes").click()
    await settle(pg)
    await pg.screenshot(path=str(shots / "step1b_import_review.png"), full_page=True)
    await dialog(pg).get_by_role("button", name="Import and open Sky Pavilion").click()
    await settle(pg)
    check((await selected(pg)).startswith("Sky Pavilion"), "import from step 1 opens Sky Pavilion")
    eggplant = dialog(pg).locator(".menu-row", has_text="Eggplant with Garlic Sauce")
    flag = await eggplant.locator(".hidden-flag").all_inner_texts()
    check(any("minced pork" in f for f in flag), f"eggplant flagged for hidden minced pork: {flag}")
    await pg.screenshot(path=str(shots / "step1c_browse_hidden_flags.png"), full_page=True)
    await dialog(pg).get_by_label("I have reviewed this menu against the source.").check()
    await dialog(pg).get_by_role("button", name="Mark reviewed").click()
    await dialog(pg).get_by_role("button", name="Use this menu").click()
    await settle(pg)
    check(
        await pg.locator(".menu-choice h2").first.inner_text() == "Sky Pavilion",
        "Sky Pavilion is the menu",
    )

    await pg.get_by_role("button", name="Continue with this menu").click()
    people = [
        ("Ana", ["vegetarian"], []),
        ("Ben", [], ["shellfish"]),
        ("Chen", ["no pork"], []),
        ("Kevin", [], []),
        ("Dana", [], []),
        ("Eli", [], []),
    ]
    for name, diets, allergies in people:
        await pg.get_by_role("button", name="Add a person").click()
        await dialog(pg).get_by_label("Name").fill(name)
        for d in diets:
            await dialog(pg).get_by_role("button", name=d, exact=True).click()
        for a in allergies:
            await dialog(pg).get_by_role("button", name=a, exact=True).click()
        if name == "Kevin":
            await dialog(pg).get_by_role("button", name="no heat", exact=True).click()
        await dialog(pg).get_by_role("button", name="Use for this meal").click()
        await settle(pg)
    budget = pg.locator(".setup-table input").first
    await budget.fill("25")
    await budget.press("Tab")
    await pg.screenshot(path=str(shots / "step2_table.png"), full_page=True)
    await pg.get_by_role("button", name="Find dishes").click()
    await settle(pg, 1000)
    check(
        await heading(pg) != "No order fits yet",
        f"Sky Pavilion plan for six at $25: {await heading(pg)}",
    )
    per = await pg.locator(".bill-total").inner_text()
    check("per person" in per, f"bill: {per.splitlines()[0]}")
    await pg.screenshot(path=str(shots / "step3_dishes.png"), full_page=True)
    await pg.get_by_role("button", name="View order ticket").click()
    await settle(pg)
    ticket = await dialog(pg).inner_text()
    check(
        "Order ticket" in ticket
        and "Table of 6" in ticket
        and "Show this to your server" in ticket,
        "order ticket",
    )
    await pg.screenshot(path=str(shots / "step3b_order_ticket.png"))
    await close_dialog(pg)
    await pg.get_by_role("button", name="Your table").click()
    budget = dialog(pg).locator("input").first
    await budget.fill("15")
    await budget.press("Tab")
    await dialog(pg).get_by_role("button", name="Update dishes").click()
    await settle(pg, 1000)
    text = await pg.locator("main").inner_text()
    check(
        "No order fits yet" in text and "$15.00 each with tax and tip" in text,
        "no-fit names the per-person budget",
    )
    check(
        "Raise the budget to" in text and "per person" in text, "no-fit offers a per-person raise"
    )
    await pg.screenshot(path=str(shots / "step3c_no_fit.png"), full_page=True)
    await pg.get_by_role("button", name=re.compile("Apply")).first.click()
    await settle(pg, 1000)
    check(await heading(pg) != "No order fits yet", "Apply gives a plan")
    await pg.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000/")
    ap.add_argument("--shots", type=Path, default=Path("/tmp/michelin-shots"))
    args = ap.parse_args()
    asyncio.run(run(args.url, args.shots))
    print(f"\n{len(FAILS)} failed" if FAILS else "\nall checks passed")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
