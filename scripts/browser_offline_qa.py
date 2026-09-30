"""Local-only Chromium QA. Requires built web/dist and optional playwright + Chromium.

Run with a Python having playwright installed. The API subprocess uses the repo .venv.
No service is published; server binds loopback and all external browser requests are blocked.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
URL = "http://127.0.0.1:8765"


def main():
    checks, errors, external = [], [], []
    with tempfile.TemporaryDirectory(prefix="michelin-browser-") as directory:
        env = {
            **os.environ,
            "MICHELIN_PROFILE_DB": str(Path(directory) / "history.sqlite3"),
            "MICHELIN_EXTRACTION_PROVIDER": "replay",
            "MICHELIN_MOCK": "0",
        }
        server = None

        def start():
            nonlocal server
            server = subprocess.Popen(
                [
                    str(ROOT / ".venv/bin/python"),
                    "-m",
                    "uvicorn",
                    "michelin.api:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8765",
                ],
                cwd=ROOT,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            for _ in range(100):
                if server.poll() is not None:
                    raise RuntimeError("Local server failed to start; check port 8765")
                try:
                    urllib.request.urlopen(URL + "/api/health", timeout=1)
                    return
                except OSError:
                    time.sleep(0.1)
            raise RuntimeError("Local server did not become ready")

        def stop():
            if server:
                server.terminate()
                server.wait(timeout=10)

        start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    executable_path=shutil.which("chromium"), headless=True, args=["--no-sandbox"]
                )
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.set_default_timeout(10000)

                def route(request):
                    if request.request.url.startswith(URL):
                        request.continue_()
                    else:
                        external.append(request.request.url)
                        request.abort()

                page.route("**/*", route)
                page.goto(URL)
                expect(page.get_by_role("heading", name="Choose a menu")).to_be_visible()
                page.get_by_role("button", name="Bring your own menu").click()
                page.screenshot(path="/tmp/michelin-import-debug.png", full_page=True)
                page.get_by_label("Prepared menu", exact=True).select_option("cafe_china_regular")
                page.get_by_role("button", name="Replay prepared response", exact=True).click()
                expect(page.get_by_text("6 dishes found", exact=True)).to_be_visible()
                page.get_by_role("button", name="Add to menu for review").click()
                page.get_by_label("I have reviewed this menu against the source.").check()
                page.get_by_role("button", name="Mark reviewed", exact=True).click()
                page.get_by_role("button", name="Use this menu", exact=True).click()
                expect(
                    page.get_by_text(re.compile("Assistant-prepared menu response replay"))
                ).to_be_visible()
                checks.append("prepared response import, explicit review, provenance banner")
                page.get_by_role("button", name="Continue with this menu").click()
                page.get_by_label("Load a group").select_option("synthetic-three")
                page.get_by_role("button", name="Back to menu").click()
                page.get_by_role("button", name="Continue with this menu").click()
                page.get_by_role("button", name="Edit Synthetic 1", exact=True).click()
                page.get_by_label("Likes", exact=True).fill("should not save")
                page.get_by_role("button", name="Cancel", exact=True).click()
                page.get_by_role("button", name="Edit Synthetic 1", exact=True).click()
                expect(page.get_by_label("Likes", exact=True)).to_have_value("")
                page.get_by_label("Likes", exact=True).fill("tofu")
                page.get_by_role("button", name="Save", exact=True).click()
                checks.append("back navigation and cancelled profile edit preserve state")
                page.get_by_text("Local synthetic profile history", exact=True).click()
                page.get_by_role("button", name="Save current person", exact=True).click()
                expect(
                    page.get_by_text("Saved Synthetic 1, revision 1.", exact=True)
                ).to_be_visible()
                page.get_by_role("button", name="Edit Synthetic 1", exact=True).click()
                page.get_by_label("Likes", exact=True).fill("mushrooms")
                page.get_by_role("button", name="Save", exact=True).click()
                page.get_by_role("button", name="Save current person", exact=True).click()
                expect(
                    page.get_by_text("Saved Synthetic 1, revision 2.", exact=True)
                ).to_be_visible()
                expect(page.get_by_role("list", name="Profile revisions")).to_contain_text("tofu")
                checks.append("explicit preference saves and historical revisions")
                # TableSetup uses "Find dishes for the table" in the initial flow.
                buttons = page.get_by_role("button").all_text_contents()
                plan_button = next(x for x in buttons if "Find" in x or "Plan the table" in x)
                page.get_by_role("button", name=plan_button, exact=True).click()
                expect(page.get_by_role("heading", name="Who can eat what")).to_be_visible()
                expect(page.get_by_role("button", name="View order ticket")).to_be_enabled()
                checks.append("real-menu plan and per-person coverage")
                for _ in range(2):
                    swap = page.get_by_role("button", name=re.compile("^Swap ")).first
                    swap.click()
                    page.get_by_role("button", name="Swap in", exact=True).first.click()
                    expect(page.get_by_role("button", name="View order ticket")).to_be_enabled()
                checks.append("two repeated swaps complete with whole-order validation")
                page.get_by_role("button", name=re.compile("^Swap ")).first.click()
                page.get_by_role("dialog").get_by_role("button", name="Close", exact=True).click()
                expect(page.get_by_role("button", name="View order ticket")).to_be_enabled()
                checks.append("swap cancellation preserves valid order")
                # Save evidence before intentional restriction failure.
                page.screenshot(path="/tmp/michelin-offline-plan.png", full_page=True)
                page.get_by_role("button", name="Edit people and budget", exact=True).click()
                page.get_by_role("button", name="Edit Synthetic 1", exact=True).click()
                page.get_by_role("button", name="shellfish", exact=True).click()
                page.get_by_role("button", name="Save", exact=True).click()
                page.get_by_role("dialog", name="Your table", exact=True).get_by_role(
                    "button", name="Close", exact=True
                ).click()
                expect(page.get_by_role("heading", name="No order fits yet")).to_be_visible()
                page.get_by_role("button", name="Browse menu", exact=True).click()
                expect(
                    page.get_by_text(re.compile("Synthetic 1: Requires confirmation")).first
                ).to_be_visible()
                expect(
                    page.get_by_text(re.compile("Synthetic 1: Recorded conflict")).first
                ).to_be_visible()
                page.get_by_role("button", name="Use this menu", exact=True).click()
                page.get_by_role("button", name="Edit people and budget", exact=True).click()
                page.get_by_role("button", name="Edit Synthetic 1", exact=True).click()
                page.get_by_role("button", name="shellfish", exact=True).click()
                page.get_by_role("button", name="Save", exact=True).click()
                page.get_by_label("Budget per person").fill("20")
                page.get_by_role("dialog", name="Your table", exact=True).get_by_role(
                    "button", name="Update dishes", exact=True
                ).click()
                expect(page.get_by_role("button", name="View order ticket")).to_be_enabled()
                checks.append(
                    "changed allergy blocks planning; per-person conflicts and uncertainty shown; clearing restores plan"
                )
                page.get_by_role("button", name=re.compile("^Swap ")).first.click()
                page.get_by_role("listitem").filter(
                    has_text="Braised Whole Fish with Pickled Chilis"
                ).get_by_role("button", name="Swap in", exact=True).click()
                expect(page.get_by_role("heading", name="No order fits yet")).to_be_visible()
                page.get_by_role("button", name="Undo", exact=True).click()
                expect(page.get_by_role("button", name="View order ticket")).to_be_enabled()
                checks.append(
                    "over-budget swap fails and Undo restores the prior valid constraints"
                )
                page.get_by_role("button", name="Edit people and budget", exact=True).click()
                page.get_by_label("Budget per person").fill("1")
                page.get_by_role("dialog", name="Your table", exact=True).get_by_role(
                    "button", name="Update dishes", exact=True
                ).click()
                expect(page.get_by_role("heading", name="No order fits yet")).to_be_visible()
                checks.append("changed budget produces explicit no-solution view")
                # Restart the actual server process on the same database.
                stop()
                start()
                page.reload()
                expect(page.get_by_role("heading", name="Choose a menu")).to_be_visible()
                page.get_by_text("Local synthetic profile history", exact=True).click()
                page.get_by_role("button", name="Load saved group", exact=True).click()
                expect(
                    page.get_by_text("Loaded 1 saved synthetic profiles.", exact=True)
                ).to_be_visible()
                page.get_by_role("button", name="View history", exact=True).click()
                expect(page.get_by_role("list", name="Profile revisions")).to_contain_text(
                    "mushrooms"
                )
                expect(page.get_by_role("list", name="Profile revisions")).to_contain_text("tofu")
                checks.append("actual local server restart retains both SQLite revisions")
                browser.close()
        finally:
            stop()
    report = {
        "checks": checks,
        "page_errors": errors,
        "external_requests": external,
        "live_model": "NOT RUN",
        "image_ocr": "NOT RUN",
    }
    Path("/tmp/michelin-browser-qa.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    assert not errors and not external


if __name__ == "__main__":
    main()
