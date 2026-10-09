"""Render the motion-graphics opener frame by frame from scripts/motion/index.html.

The page exposes render(t); each frame is a screenshot piped into ffmpeg, so motion is exact at 30 fps.
Output: docs/video/polygraph-motion.mp4
"""

import asyncio
import subprocess
from pathlib import Path

import imageio_ffmpeg
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "scripts" / "motion" / "index.html"
OUT = ROOT / "docs" / "video" / "polygraph-motion.mp4"
FPS = 30
SPEED = 1.18  # plays the 40 s timeline in about 34 s


async def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    ff = subprocess.Popen(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-f", "image2pipe", "-framerate", str(FPS), "-c:v", "mjpeg", "-i", "-",
         "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(OUT)],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        await page.goto(PAGE.as_uri(), wait_until="networkidle")
        await page.evaluate("document.fonts.ready")
        duration = await page.evaluate("window.DURATION")
        for i in range(int(duration / SPEED * FPS)):
            await page.evaluate(f"render({i * SPEED / FPS})")
            ff.stdin.write(await page.screenshot(type="jpeg", quality=94))
        await browser.close()
    ff.stdin.close()
    ff.wait()
    print("saved", OUT)


asyncio.run(main())
