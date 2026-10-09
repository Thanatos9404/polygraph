"""Record the demo video by driving the real app in the locally installed Chrome.

Captions and title cards are injected into the page, so every frame is the real product. One live run on
Nemotron happens during recording (a few cents). Output: docs/video/polygraph-demo.mp4

Usage: python scripts/video.py [base_url]
"""

import asyncio
import shutil
import time
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg
from playwright.async_api import Page, async_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:7860"
OUT = Path(__file__).resolve().parent.parent / "docs" / "video"
W, H = 1920, 1080

OVERLAY = """
(() => {
  if (window.__pg) return;
  const css = document.createElement('style');
  css.textContent = `
    #pg-cursor{position:fixed;z-index:99999;width:22px;height:22px;margin:-11px 0 0 -11px;border-radius:50%;
      background:rgba(229,72,42,.9);box-shadow:0 0 0 6px rgba(229,72,42,.18);pointer-events:none;transition:transform .15s}
    #pg-cap{position:fixed;z-index:99998;left:50%;bottom:56px;transform:translateX(-50%) translateY(20px);opacity:0;
      max-width:1280px;padding:18px 30px;border-radius:999px;background:rgba(16,15,14,.86);color:#f3f1ec;
      font:500 27px/1.35 Geist,system-ui,sans-serif;text-align:center;backdrop-filter:blur(12px);
      box-shadow:0 20px 60px -20px rgba(0,0,0,.6);transition:all .5s cubic-bezier(.2,.8,.2,1)}
    #pg-cap.on{opacity:1;transform:translateX(-50%) translateY(0)}
    #pg-cap b{color:#ff8a5c;font-weight:600}
    #pg-card{position:fixed;inset:0;z-index:99997;display:flex;flex-direction:column;align-items:center;justify-content:center;
      gap:28px;background:#121110;color:#f3f1ec;opacity:0;pointer-events:none;transition:opacity .6s}
    #pg-card.on{opacity:1}
    #pg-card h1{font:400 150px/0.95 'Instrument Serif',Georgia,serif;letter-spacing:-3px;margin:0;text-align:center}
    #pg-card p{font:400 52px/1.15 'Instrument Serif',Georgia,serif;margin:0;max-width:1400px;text-align:center}
    #pg-card i{color:#ff8a5c}
    #pg-card small{font:500 22px/1 'Geist Mono',monospace;letter-spacing:4px;text-transform:uppercase;color:#e5482a}`;
  document.head.appendChild(css);
  const cur = document.createElement('div'); cur.id = 'pg-cursor'; document.body.appendChild(cur);
  addEventListener('mousemove', e => { cur.style.left = e.clientX + 'px'; cur.style.top = e.clientY + 'px'; }, true);
  addEventListener('mousedown', () => cur.style.transform = 'scale(.7)', true);
  addEventListener('mouseup', () => cur.style.transform = 'scale(1)', true);
  const cap = document.createElement('div'); cap.id = 'pg-cap'; document.body.appendChild(cap);
  const card = document.createElement('div'); card.id = 'pg-card'; document.body.appendChild(card);
  window.__pg = {
    cap(t){ cap.classList.remove('on'); setTimeout(() => { cap.innerHTML = t; if (t) cap.classList.add('on'); }, t && cap.innerHTML ? 260 : 0); },
    card(h){ card.innerHTML = h; card.classList.add('on'); },
    uncard(){ card.classList.remove('on'); },
  };
})();
"""


async def prep(page: Page) -> None:
    await page.evaluate(OVERLAY)


async def cap(page: Page, text: str, hold: float = 0) -> None:
    await page.evaluate("t => window.__pg.cap(t)", text)
    if hold:
        await page.wait_for_timeout(int(hold * 1000))


async def card(page: Page, html: str, hold: float) -> None:
    await page.evaluate("h => window.__pg.card(h)", html)
    await page.wait_for_timeout(int(hold * 1000))
    await page.evaluate("window.__pg.uncard()")
    await page.wait_for_timeout(500)


async def glide(page: Page, x: float, y: float, steps: int = 30) -> None:
    await page.mouse.move(x, y, steps=steps)


async def scroll_to(page: Page, y: float, ms: int = 1600) -> None:
    await page.evaluate(
        """([y, ms]) => new Promise(res => {
            const s = scrollY, d = y - s, t0 = performance.now();
            const ease = t => t < .5 ? 4*t*t*t : 1 - Math.pow(-2*t + 2, 3) / 2;
            const step = now => { const t = Math.min(1, (now - t0) / ms); scrollTo(0, s + d * ease(t)); t < 1 ? requestAnimationFrame(step) : res(); };
            requestAnimationFrame(step);
        })""",
        [y, ms],
    )


async def scroll_el(page: Page, selector: str, offset: int = 0, ms: int = 1600) -> None:
    y = await page.evaluate("([s, o]) => document.querySelector(s).getBoundingClientRect().top + scrollY + o", [selector, offset])
    await scroll_to(page, y, ms)


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    raw = OUT / "raw"
    shutil.rmtree(raw, ignore_errors=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=True, args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        ctx = await browser.new_context(
            viewport={"width": W, "height": H},
            record_video_dir=str(raw),
            record_video_size={"width": W, "height": H},
            color_scheme="dark",
        )
        await ctx.add_init_script("try{localStorage.setItem('pg-theme','dark')}catch(e){}")
        page = await ctx.new_page()
        t0 = time.monotonic()
        marks: dict[str, float] = {}

        # 1. Title card and hero
        await page.goto(BASE + "/", wait_until="networkidle")
        await prep(page)
        await glide(page, 600, 760, 40)
        await cap(page, "Code review today means <b>reading a diff</b>. A diff never runs.", 2.8)
        await glide(page, 1350, 700, 50)
        await cap(page, "Polygraph runs the code <b>before and after</b> a change in two isolated universes.", 3.6)

        # 2. Product frame flattening, manifesto
        await scroll_to(page, 1000, 2600)
        await cap(page, "It turns every claim in the PR into an experiment, and flags behavior <b>nobody declared</b>.", 3.2)
        await scroll_el(page, "#cases", -1150, 3200)
        await cap(page, "", 0.2)

        # 3. Read vs run switch (real output for the dependency bump)
        sw = page.locator("button[role=switch]").first
        await sw.scroll_into_view_if_needed()
        await scroll_to(page, await page.evaluate("document.querySelector('button[role=switch]').getBoundingClientRect().top + scrollY - 380"), 1200)
        box = await sw.bounding_box()
        await glide(page, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, 30)
        await sw.click()
        await cap(page, "Same PR, a one-line dependency bump. <b>Nemotron 3 Ultra reading the diff approves it.</b>", 3.6)
        await sw.click()
        await cap(page, "Running both versions finds <b>five undeclared breaking changes</b>.", 3.4)

        # 4. Case files, then a live run
        await scroll_el(page, "#cases", -20, 1800)
        await cap(page, "Let's run one live, on <b>NVIDIA Nemotron via Nebius Token Factory</b>.", 1.0)
        first_card = page.locator("#cases article").first
        fb = await first_card.bounding_box()
        await glide(page, fb["x"] + fb["width"] * 0.3, fb["y"] + fb["height"] * 0.35, 30)
        await glide(page, fb["x"] + fb["width"] * 0.7, fb["y"] + fb["height"] * 0.6, 40)
        await page.wait_for_timeout(1200)
        live_btn = first_card.get_by_role("button", name="Run live")
        lb = await live_btn.bounding_box()
        await glide(page, lb["x"] + lb["width"] / 2, lb["y"] + lb["height"] / 2, 25)
        await live_btn.click()
        await page.wait_for_url("**/run/**", timeout=30000)
        await page.wait_for_timeout(600)
        await prep(page)
        await cap(page, "An AI agent's refactor: <b>“No behavior change. All tests pass.”</b> Nemotron 3 Ultra writes the claim ledger.", 5.5)
        await cap(page, "Ultra plans experiments. <b>Nemotron 3.5 Lightning</b> writes executable probes in parallel.", 5.5)
        await cap(page, "Each probe runs in universe <b>A</b>, in A again to discard noise, and in <b>B</b>. The project's own tests run in both.", 5.5)
        await cap(page, "<b>Nemotron 3 Super</b> splits divergences by root cause. Ultra rules on every claim. <b>Fast-forward 4x.</b>", 1.2)
        marks["ff_start"] = time.monotonic() - t0
        await page.get_by_text("examination complete").wait_for(timeout=240000)
        marks["ff_end"] = time.monotonic() - t0 + 0.6
        await page.wait_for_timeout(1800)
        await cap(page, "Verdict: <b>inconsistent</b>. Tests stayed green, the 2x speedup is real, the behavior changed anyway.", 4.0)

        # 5. Ledger and a witness
        await scroll_to(page, 1050, 1800)
        await cap(page, "Every claim is confirmed, contradicted, or left unverified, with the evidence attached.", 3.6)
        await page.get_by_role("tab", name="Divergences").click()
        await page.wait_for_timeout(500)
        await scroll_to(page, 1050, 900)
        await cap(page, "Every finding has a witness: <b>the same input, before and after</b>.", 4.0)
        await page.get_by_role("tab", name="Report").click()
        await page.wait_for_timeout(500)
        await cap(page, "Ships as a PR comment and a pytest file that <b>fails until the change is declared</b>.", 3.4)

        # 6. Dependency bump replay with the control arm and Tavily
        await page.goto(BASE + "/run/case-packaging-bump?speed=14", wait_until="networkidle")
        await prep(page)
        await cap(page, "Recorded run: the dependency bump. <b>Tavily</b> pulls the official changelog between the two versions.", 3.5)
        await page.get_by_text("examination complete").wait_for(timeout=60000)
        ctrl = await page.get_by_text("Control arm: reading the diff").bounding_box()
        await scroll_to(page, ctrl["y"] + await page.evaluate("scrollY") - 140, 2200)
        await cap(page, "Control arm: the reader approved with nothing to say. Polygraph ran two library versions side by side.", 4.4)

        # 7. Real merged PR
        await page.goto(BASE + "/run/real-humanize-381?speed=14", wait_until="networkidle")
        await prep(page)
        await cap(page, "A real merged PR in <b>python-humanize</b>, installed and tested in both universes.", 2.6)
        await page.get_by_text("examination complete").wait_for(timeout=60000)
        await page.get_by_role("tab", name="Divergences").click()
        await scroll_to(page, 900, 1600)
        await cap(page, "<b>natural_list(None)</b> returned <b>''</b>. Now it raises <b>TypeError</b>. The PR never mentions it.", 5.0)

        # 8. Close
        await cap(page, "", 0.2)
        await card(page, "<h1>Merge what you <i>can prove.</i></h1><p>CLI · GitHub Action · web app · API · Apache 2.0</p><small>github.com/Thanatos9404/polygraph</small>", 4.0)

        await ctx.close()
        await browser.close()

    webm = next(raw.glob("*.webm"))
    mp4 = OUT / "polygraph-demo.mp4"
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    a, b = marks["ff_start"], marks["ff_end"]
    graph = (
        f"[0:v]trim=0.8:{a},setpts=PTS-STARTPTS[v0];"
        f"[0:v]trim={a}:{b},setpts=(PTS-STARTPTS)/4[v1];"
        f"[0:v]trim={b},setpts=PTS-STARTPTS[v2];"
        "[v0][v1][v2]concat=n=3:v=1:a=0,fps=30[out]"
    )
    subprocess.run(
        [ff, "-y", "-i", str(webm), "-filter_complex", graph, "-map", "[out]", "-c:v", "libx264", "-preset", "slow",
         "-crf", "19", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(mp4)],
        check=True, capture_output=True,
    )
    print("marks", marks)
    probe = subprocess.run([ff, "-i", str(mp4)], capture_output=True, text=True)
    dur = [l for l in probe.stderr.splitlines() if "Duration" in l]
    print("saved", mp4, dur[0].strip() if dur else "")


asyncio.run(main())
