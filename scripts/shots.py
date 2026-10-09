"""Capture product screenshots for the README, deck, and Devpost gallery with the locally installed Chrome.

Usage: python scripts/shots.py [base_url]   (server must be running; defaults to http://127.0.0.1:7860)
"""

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:7860"
OUT = Path(__file__).resolve().parent.parent / "docs" / "assets"


async def shot(page, name: str) -> None:
    await page.screenshot(path=OUT / f"{name}.jpg", type="jpeg", quality=86)


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.png"):
        old.unlink()
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=True)
        for theme in ("dark", "light"):
            ctx = await browser.new_context(viewport={"width": 1600, "height": 1000}, device_scale_factor=1.5, color_scheme=theme)
            await ctx.add_init_script(f"try{{localStorage.setItem('pg-theme','{theme}')}}catch(e){{}}")
            page = await ctx.new_page()
            await page.goto(BASE + "/", wait_until="networkidle")
            await page.wait_for_timeout(2600)
            await shot(page, f"hero-{theme}")
            for anchor, name, offset in (("cases", "cases", -20), ("how", "how", 700), ("models", "models", -20)):
                await page.evaluate(f"document.getElementById('{anchor}').scrollIntoView(); window.scrollBy(0, {offset})")
                await page.wait_for_timeout(2200)
                await shot(page, f"{name}-{theme}")
            await page.evaluate("window.scrollTo(0, 1500)")
            await page.wait_for_timeout(1800)
            await shot(page, f"frame-{theme}")
            for case in ("case-packaging-bump", "case-slugkit-refactor", "real-humanize-381"):
                await page.goto(f"{BASE}/run/{case}?speed=50", wait_until="networkidle")
                await page.wait_for_timeout(4500)
                await shot(page, f"run-{case}-{theme}")
                await page.evaluate("window.scrollTo(0, 1000)")
                await page.wait_for_timeout(1400)
                await shot(page, f"run-{case}-{theme}-detail")
            await ctx.close()
        await browser.close()
    print("saved to", OUT)


asyncio.run(main())
