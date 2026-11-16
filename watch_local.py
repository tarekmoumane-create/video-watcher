#!/usr/bin/env python3
"""Like watch.py, but for an already-downloaded video file.

Usage: python3 watch_local.py <video.mp4> <slug> <source_url>

Fallback for when yt-dlp's TikTok extractor is broken and the file was
fetched some other way. Reuses watch.py's frame extraction and Gemini call.
"""

import sys
from pathlib import Path

from watch import analyze, extract_frames, load_key


def main() -> None:
    if len(sys.argv) < 4:
        sys.exit("Usage: python3 watch_local.py <video.mp4> <slug> <source_url>")
    video_src, slug, url = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    if not video_src.exists():
        sys.exit(f"No such file: {video_src}")
    key = load_key()

    out_dir = Path.home() / "Downloads" / "watched" / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    video_path = out_dir / "video.mp4"
    if video_src.resolve() != video_path.resolve():
        video_path.write_bytes(video_src.read_bytes())

    print("Taking screenshots...")
    n_frames = extract_frames(video_path, out_dir)

    print("Watching with Gemini (this takes ~30-60 seconds)...")
    report = analyze(video_path, key)

    report_path = out_dir / "report.md"
    report_path.write_text(f"# {slug}\n\nSource: {url}\n\n{report}\n")

    print(f"\nDone. Everything is in: {out_dir}")
    print(f"  report.md ({len(report)} chars), video.mp4, {n_frames} screenshots")


if __name__ == "__main__":
    main()
