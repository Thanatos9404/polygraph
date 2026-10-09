"""Join the motion-graphics opener and the product demo into the submission video.

Output: docs/video/polygraph-final.mp4 (1920x1080, 30 fps, H.264, under three minutes)
"""

import subprocess
from pathlib import Path

import imageio_ffmpeg

VID = Path(__file__).resolve().parent.parent / "docs" / "video"
FF = imageio_ffmpeg.get_ffmpeg_exe()


def duration(path: Path) -> float:
    err = subprocess.run([FF, "-i", str(path)], capture_output=True, text=True).stderr
    line = next(l for l in err.splitlines() if "Duration" in l)
    h, m, s = line.split("Duration:")[1].split(",")[0].strip().split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def main() -> None:
    a, b = VID / "polygraph-motion.mp4", VID / "polygraph-demo.mp4"
    da = duration(a)
    graph = (
        f"[0:v]fps=30,format=yuv420p,fade=t=out:st={da - 0.5:.2f}:d=0.5[v0];"
        "[1:v]fps=30,format=yuv420p,fade=t=in:st=0:d=0.5[v1];"
        "[v0][v1]concat=n=2:v=1:a=0[out]"
    )
    out = VID / "polygraph-final.mp4"
    subprocess.run(
        [FF, "-y", "-i", str(a), "-i", str(b), "-filter_complex", graph, "-map", "[out]", "-c:v", "libx264",
         "-preset", "slow", "-crf", "19", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)],
        check=True, capture_output=True,
    )
    total = duration(out)
    print(f"saved {out} ({total:.1f}s, opener {da:.1f}s)")
    if total >= 180:
        print("WARNING: over three minutes")


if __name__ == "__main__":
    main()
