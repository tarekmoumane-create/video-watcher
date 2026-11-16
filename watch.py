#!/usr/bin/env python3
"""Watch a TikTok/Instagram/YouTube video with Gemini and produce a full breakdown.

Usage: python3 watch.py <video_url>

Output goes to ~/Downloads/watched/<video-slug>/
  - report.md      exact transcript, on-screen text, visual breakdown, materials
  - video.mp4      the downloaded video
  - frames/        screenshots taken through the video
"""

import os
import re
import subprocess
import sys
import time
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
ENV_FILE = PROJECT_DIR / ".env"

MODEL = "gemini-3.7-flash"
FALLBACK_MODEL = "gemini-3.5-flash"

PROMPT = """You are analyzing a short-form social video (TikTok/Instagram Reel style).
Watch and listen to the ENTIRE video carefully, then produce a markdown report with these sections:

## Exact Transcript
A word-for-word verbatim transcript of everything spoken, with timestamps every few seconds
in [MM:SS] format. Include filler words (um, like) exactly as said. If there is no speech,
say so and describe the audio (music, sounds) instead.

## On-Screen Text
Every piece of text that appears on screen (captions, text overlays, signs, product labels),
each with its timestamp and exact wording.

## Visual Breakdown
A shot-by-shot description: what is shown, camera style, cuts, transitions, and timestamps.

## Topic & Materials
What the video is about, and a list of every material/product/tool/location/person referenced
or shown that someone would need if they wanted to recreate or act on this video. Be specific
(brand names, product names, quantities if visible or stated).

## Hook & Structure Notes
The opening hook (first 3 seconds), the video's structure, and why it holds attention.

Be exhaustive and literal. Do not summarize the transcript; it must be verbatim."""


def load_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key and ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if line.startswith("GEMINI_API_KEY"):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key:
        sys.exit("No GEMINI_API_KEY found in environment or .env")
    return key


def slugify(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:60] or "video"


def download(url: str, out_dir: Path) -> tuple[Path, str]:
    """Download the video with yt-dlp. Returns (video_path, title)."""
    title = subprocess.run(
        ["yt-dlp", "--get-title", "--no-warnings", url],
        capture_output=True, text=True,
    ).stdout.strip() or "video"

    out_dir.mkdir(parents=True, exist_ok=True)
    video_path = out_dir / "video.mp4"
    result = subprocess.run(
        [
            "yt-dlp", "--no-warnings",
            "-f", "mp4/bestvideo*+bestaudio/best",
            "--merge-output-format", "mp4",
            "-o", str(video_path),
            url,
        ],
        capture_output=True, text=True,
    )
    if not video_path.exists():
        sys.exit(f"Download failed:\n{result.stderr[-2000:]}")
    return video_path, title


def extract_frames(video_path: Path, out_dir: Path) -> int:
    """Grab a screenshot every 2 seconds (max ~30 frames)."""
    frames_dir = out_dir / "frames"
    frames_dir.mkdir(exist_ok=True)

    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(video_path)],
        capture_output=True, text=True,
    )
    duration = float(probe.stdout.strip() or 30)
    interval = max(2.0, duration / 30)

    subprocess.run(
        ["ffmpeg", "-y", "-v", "quiet", "-i", str(video_path),
         "-vf", f"fps=1/{interval}", "-q:v", "2",
         str(frames_dir / "frame_%03d.jpg")],
        capture_output=True,
    )
    return len(list(frames_dir.glob("*.jpg")))


def analyze(video_path: Path, key: str) -> str:
    from google import genai

    client = genai.Client(api_key=key)

    uploaded = client.files.upload(file=str(video_path))
    while uploaded.state and uploaded.state.name == "PROCESSING":
        time.sleep(3)
        uploaded = client.files.get(name=uploaded.name)
    if uploaded.state and uploaded.state.name == "FAILED":
        sys.exit("Gemini could not process the video file.")

    for model in (MODEL, FALLBACK_MODEL):
        try:
            response = client.models.generate_content(
                model=model, contents=[uploaded, PROMPT]
            )
            if response.text:
                return response.text
        except Exception as e:
            print(f"  {model} failed ({e}); trying fallback...", file=sys.stderr)
    sys.exit("Gemini analysis failed on all models.")


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("Usage: python3 watch.py <tiktok/instagram/youtube url>")
    url = sys.argv[1]
    key = load_key()

    print("Downloading video...")
    tmp_dir = Path.home() / "Downloads" / "watched" / f"tmp-{int(time.time())}"
    video_path, title = download(url, tmp_dir)

    out_dir = Path.home() / "Downloads" / "watched" / slugify(title)
    if out_dir.exists():
        out_dir = Path(str(out_dir) + f"-{int(time.time())}")
    tmp_dir.rename(out_dir)
    video_path = out_dir / "video.mp4"

    print("Taking screenshots...")
    n_frames = extract_frames(video_path, out_dir)

    print("Watching with Gemini (this takes ~30-60 seconds)...")
    report = analyze(video_path, key)

    report_path = out_dir / "report.md"
    report_path.write_text(f"# {title}\n\nSource: {url}\n\n{report}\n")

    print(f"\nDone. Everything is in: {out_dir}")
    print(f"  report.md ({len(report)} chars), video.mp4, {n_frames} screenshots")


if __name__ == "__main__":
    main()
