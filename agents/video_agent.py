"""
Step 5: Video Assembly Agent
------------------------------
Combines the outputs of the previous steps into the final vertical
(1080x1920) .mp4:
  - voice_<ts>.mp3        (Step 2)
  - visual_<ts>_*.mp4     (Step 3, via visuals_<ts>.json manifest)
  - captions_<ts>.srt     (Step 4, burned in as subtitles)

Uses ffmpeg directly via subprocess — no extra Python video library needed
beyond what Step 4 already required you to install.

Run:
    python agents/video_agent.py
"""

import json
import random
import subprocess
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "output"
MUSIC_DIR = Path(__file__).parent.parent / "assets" / "music"

TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920
TARGET_FPS = 30

# Background music volume relative to narration (1.0 = same as voice).
# Keep this low so the narration stays clearly audible.
MUSIC_VOLUME = 0.12

# Style for burned-in captions (ffmpeg subtitles filter "force_style").
# Big, bold, centered — standard short-form caption look.
SUBTITLE_STYLE = (
    "FontName=Arial,FontSize=16,Bold=1,PrimaryColour=&H00FFFFFF,"
    "OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=0,"
    "Alignment=2,MarginV=120"
)


def find_latest(pattern: str) -> Path:
    matches = sorted(OUTPUT_DIR.glob(pattern))
    if not matches:
        raise SystemExit(f"No files matching {pattern} in agents/output/. Run earlier steps first.")
    return matches[-1]


def run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr[-3000:])  # ffmpeg errors can be long; show the tail
        raise SystemExit(f"Command failed: {' '.join(cmd)}")


def get_audio_duration(audio_path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "json", str(audio_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"ffprobe failed on {audio_path}: {result.stderr}")
    return float(json.loads(result.stdout)["format"]["duration"])


def escape_for_ffmpeg_filter(path: Path) -> str:
    """ffmpeg filter args treat ':' and '\\' specially — this matters a lot on Windows paths."""
    p = str(path.resolve()).replace("\\", "/")
    p = p.replace(":", "\\:")
    return p


def pick_random_music() -> Path | None:
    if not MUSIC_DIR.exists():
        return None
    tracks = list(MUSIC_DIR.glob("*.mp3")) + list(MUSIC_DIR.glob("*.wav"))
    if not tracks:
        return None
    return random.choice(tracks)


def build_visuals_segment(clip_paths: list[Path], total_duration: float, out_path: Path) -> None:
    """Trim each clip to an even share of total_duration, scale/crop to
    portrait 1080x1920, and concat them into one silent video segment."""
    n = len(clip_paths)
    per_clip = total_duration / n

    inputs = []
    filter_parts = []
    for i, clip in enumerate(clip_paths):
        inputs += ["-i", str(clip)]
        filter_parts.append(
            f"[{i}:v]trim=0:{per_clip:.3f},setpts=PTS-STARTPTS,"
            f"scale={TARGET_WIDTH}:{TARGET_HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={TARGET_WIDTH}:{TARGET_HEIGHT},fps={TARGET_FPS}[v{i}]"
        )

    concat_inputs = "".join(f"[v{i}]" for i in range(n))
    filter_complex = ";".join(filter_parts) + f";{concat_inputs}concat=n={n}:v=1:a=0[outv]"

    cmd = (
        ["ffmpeg", "-y"] + inputs
        + ["-filter_complex", filter_complex, "-map", "[outv]"]
        + ["-an", str(out_path)]
    )
    run(cmd)


def main():
    script_path = find_latest("script_*.json")
    timestamp = script_path.stem.replace("script_", "")

    voice_path = OUTPUT_DIR / f"voice_{timestamp}.mp3"
    visuals_manifest_path = OUTPUT_DIR / f"visuals_{timestamp}.json"
    captions_path = OUTPUT_DIR / f"captions_{timestamp}.srt"
    final_path = OUTPUT_DIR / f"final_{timestamp}.mp4"

    for p in (voice_path, visuals_manifest_path, captions_path):
        if not p.exists():
            raise SystemExit(
                f"Missing {p.name} — make sure Steps 2, 3 and 4 all ran for "
                f"this same timestamp ({timestamp})."
            )

    print("🎬 Assembling final video...")

    audio_duration = get_audio_duration(voice_path)
    print(f"   Narration length: {audio_duration:.1f}s")

    clips = json.loads(visuals_manifest_path.read_text())
    clip_paths = [Path(c["path"]) for c in clips]

    silent_video_path = OUTPUT_DIR / f"_silent_{timestamp}.mp4"
    print(f"   Assembling {len(clip_paths)} visual clip(s)...")
    build_visuals_segment(clip_paths, audio_duration, silent_video_path)

    print("   Adding narration + burning in captions...")
    subs_arg = escape_for_ffmpeg_filter(captions_path)

    music_path = pick_random_music()
    if music_path:
        print(f"   Mixing in background music: {music_path.name}")
        cmd = [
            "ffmpeg", "-y",
            "-i", str(silent_video_path),
            "-i", str(voice_path),
            "-stream_loop", "-1", "-i", str(music_path),
            "-filter_complex",
            f"[0:v]subtitles='{subs_arg}':force_style='{SUBTITLE_STYLE}'[outv];"
            f"[2:a]atrim=0:{audio_duration:.3f},volume={MUSIC_VOLUME}[music];"
            f"[1:a][music]amix=inputs=2:duration=first:dropout_transition=2[outa]",
            "-map", "[outv]", "-map", "[outa]",
            "-c:v", "libx264", "-c:a", "aac",
            "-shortest",
            str(final_path),
        ]
    else:
        print("   No background music found in assets/music/ — skipping (voice-only).")
        cmd = [
            "ffmpeg", "-y",
            "-i", str(silent_video_path),
            "-i", str(voice_path),
            "-filter_complex",
            f"[0:v]subtitles='{subs_arg}':force_style='{SUBTITLE_STYLE}'[outv]",
            "-map", "[outv]", "-map", "1:a",
            "-c:v", "libx264", "-c:a", "aac",
            "-shortest",
            str(final_path),
        ]
    run(cmd)

    silent_video_path.unlink(missing_ok=True)

    print(f"\n✅ Final video ready: {final_path}")


if __name__ == "__main__":
    main()