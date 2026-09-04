"""
Step 5: Video Assembly Agent
------------------------------
Combines the outputs of the previous steps into the final vertical
(1080x1920) .mp4:
  - voice_<ts>.mp3          (Step 2)
  - visual_<ts>_*.(mp4/jpg) (Step 3, via visuals_<ts>.json manifest —
                              video clips play normally, images get a
                              Ken Burns zoom effect so nothing sits static)
  - captions_<ts>.srt       (Step 4, burned in as subtitles)

Uses ffmpeg directly via subprocess.

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

MUSIC_VOLUME = 0.12

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
        print(result.stderr[-3000:])
        raise SystemExit(f"Command failed: {' '.join(cmd)}")

def get_audio_duration(audio_path: Path) -> float:
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(audio_path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"ffprobe failed on {audio_path}: {result.stderr}")
    return float(json.loads(result.stdout)["format"]["duration"])

def escape_for_ffmpeg_filter(path: Path) -> str:
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

def build_visuals_segment(clips: list[dict], total_duration: float, out_path: Path) -> None:
    """Builds one silent video segment from a mix of video clips (trimmed to
    an even share of total_duration) and images (Ken Burns zoom effect)."""
    n = len(clips)
    per_clip = total_duration / n
    frames = max(1, round(per_clip * TARGET_FPS))

    inputs = []
    filter_parts = []
    for i, clip in enumerate(clips):
        path = clip["path"]
        if clip["type"] == "video":
            inputs += ["-i", path]
            filter_parts.append(
                f"[{i}:v]trim=0:{per_clip:.3f},setpts=PTS-STARTPTS,"
                f"scale={TARGET_WIDTH}:{TARGET_HEIGHT}:force_original_aspect_ratio=increase,"
                f"crop={TARGET_WIDTH}:{TARGET_HEIGHT},setsar=1,fps={TARGET_FPS}[v{i}]"
            )
        else:  # image — loop it and apply a slow Ken Burns zoom
            inputs += ["-loop", "1", "-i", path]
            filter_parts.append(
                f"[{i}:v]scale={TARGET_WIDTH}:{TARGET_HEIGHT}:force_original_aspect_ratio=increase,"
                f"crop={TARGET_WIDTH}:{TARGET_HEIGHT},scale={TARGET_WIDTH*2}:{TARGET_HEIGHT*2},"
                f"zoompan=z='min(zoom+0.0015,1.2)':d={frames}:"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={TARGET_WIDTH}x{TARGET_HEIGHT}:fps={TARGET_FPS},"
                f"setsar=1,trim=0:{per_clip:.3f},setpts=PTS-STARTPTS[v{i}]"
            )

    concat_inputs = "".join(f"[v{i}]" for i in range(n))
    filter_complex = ";".join(filter_parts) + f";{concat_inputs}concat=n={n}:v=1:a=0[outv]"

    cmd = (
        ["ffmpeg", "-y"] + inputs
        + ["-filter_complex", filter_complex, "-map", "[outv]"]
        + ["-an", str(out_path)]
    )
    run(cmd)

def extract_thumbnail(clips: list[dict], out_path: Path) -> bool:
    """Grab a frame from the first *video* clip (not the screenshot/photos)
    to use as the YouTube thumbnail — more reliable than YouTube's
    auto-picker, which can land on the wrong asset."""
    first_video = next((c for c in clips if c["type"] == "video"), None)
    if not first_video:
        return False
    cmd = [
        "ffmpeg", "-y", "-i", first_video["path"],
        "-ss", "0.5", "-frames:v", "1",
        "-vf", f"scale={TARGET_WIDTH}:{TARGET_HEIGHT}:force_original_aspect_ratio=increase,crop={TARGET_WIDTH}:{TARGET_HEIGHT}",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0 and out_path.exists()

def main():
    script_path = find_latest("script_*.json")
    timestamp = script_path.stem.replace("script_", "")

    voice_path = OUTPUT_DIR / f"voice_{timestamp}.mp3"
    visuals_manifest_path = OUTPUT_DIR / f"visuals_{timestamp}.json"
    captions_path = OUTPUT_DIR / f"captions_{timestamp}.srt"
    final_path = OUTPUT_DIR / f"final_{timestamp}.mp4"

    for p in (voice_path, visuals_manifest_path, captions_path):
        if not p.exists():
            raise SystemExit(f"Missing {p.name} — make sure Steps 2, 3 and 4 all ran for timestamp {timestamp}.")

    print("🎬 Assembling final video...")

    audio_duration = get_audio_duration(voice_path)
    print(f"   Narration length: {audio_duration:.1f}s")

    clips = json.loads(visuals_manifest_path.read_text())
    print(f"   Assembling {len(clips)} visual asset(s) ({sum(1 for c in clips if c['type']=='video')} video, "
          f"{sum(1 for c in clips if c['type']=='image')} image)...")

    silent_video_path = OUTPUT_DIR / f"_silent_{timestamp}.mp4"
    build_visuals_segment(clips, audio_duration, silent_video_path)

    thumbnail_path = OUTPUT_DIR / f"thumbnail_{timestamp}.jpg"
    if extract_thumbnail(clips, thumbnail_path):
        print(f"   Thumbnail extracted: {thumbnail_path.name}")
    else:
        print("   ⚠️  Could not extract a thumbnail frame (no video clip in this batch?).")

    print("   Adding narration + burning in captions...")
    subs_arg = escape_for_ffmpeg_filter(captions_path)

    # Write the filter graph to a script file instead of passing it inline as
    # a single -filter_complex argv string. Some ffmpeg builds (seen on
    # ffmpeg 8/9) choke on the mix of single-quoted subtitles path +
    # force_style value in one inline string ("No option name near ..."),
    # even though the string is well-formed. -filter_complex_script reads
    # the exact same graph syntax straight out of a file and sidesteps that
    # argv-parsing edge case entirely.
    filter_script_path = OUTPUT_DIR / f"_filter_{timestamp}.txt"

    music_path = pick_random_music()
    if music_path:
        print(f"   Mixing in background music: {music_path.name}")
        filter_complex = (
            f"[0:v]subtitles='{subs_arg}':force_style='{SUBTITLE_STYLE}'[outv];"
            f"[2:a]atrim=0:{audio_duration:.3f},volume={MUSIC_VOLUME}[music];"
            f"[1:a][music]amix=inputs=2:duration=first:dropout_transition=2[outa]"
        )
        filter_script_path.write_text(filter_complex)
        cmd = [
            "ffmpeg", "-y",
            "-i", str(silent_video_path),
            "-i", str(voice_path),
            "-stream_loop", "-1", "-i", str(music_path),
            "-filter_complex_script", str(filter_script_path),
            "-map", "[outv]", "-map", "[outa]",
            "-c:v", "libx264", "-c:a", "aac",
            "-shortest",
            str(final_path),
        ]
    else:
        print("   No background music found in assets/music/ — skipping (voice-only).")
        filter_complex = f"[0:v]subtitles='{subs_arg}':force_style='{SUBTITLE_STYLE}'[outv]"
        filter_script_path.write_text(filter_complex)
        cmd = [
            "ffmpeg", "-y",
            "-i", str(silent_video_path),
            "-i", str(voice_path),
            "-filter_complex_script", str(filter_script_path),
            "-map", "[outv]", "-map", "1:a",
            "-c:v", "libx264", "-c:a", "aac",
            "-shortest",
            str(final_path),
        ]
    run(cmd)

    silent_video_path.unlink(missing_ok=True)
    filter_script_path.unlink(missing_ok=True)
    print(f"\n✅ Final video ready: {final_path}")

if __name__ == "__main__":
    main()
