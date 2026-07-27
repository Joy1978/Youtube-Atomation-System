"""
Step 4: Captions Agent
------------------------
Transcribes the narration audio (from voice_agent.py) using Whisper
(OpenAI, free, runs locally — no API key, no per-use cost) and writes
short-form burn-in captions (2-4 words per line, timed to the words) as
both a .srt file and a raw word-timing .json for Step 5.

Requires ffmpeg installed on your system (Whisper uses it internally):
    Windows: choco install ffmpeg   (or download from ffmpeg.org and add to PATH)
    Mac:     brew install ffmpeg
    Linux:   sudo apt install ffmpeg

Run:
    python agents/captions_agent.py
"""

import json
import shutil
from pathlib import Path

import whisper

OUTPUT_DIR = Path(__file__).parent / "output"

# "tiny" and "base" are fast enough to run on CPU in a few seconds for a
# 30s clip. Bump to "small" if accuracy on tricky tech terms is an issue.
MODEL_SIZE = "base"

# How many words per caption line — short-form captions read best at 2-4.
WORDS_PER_CAPTION = 3


def find_latest_voice() -> Path:
    files = sorted(OUTPUT_DIR.glob("voice_*.mp3"))
    if not files:
        raise SystemExit(
            "No voice_*.mp3 files found in agents/output/. Run voice_agent.py first."
        )
    return files[-1]


def check_ffmpeg():
    if shutil.which("ffmpeg") is None:
        raise SystemExit(
            "ffmpeg not found on your system PATH. Whisper needs it.\n"
            "Windows: choco install ffmpeg  (or download from ffmpeg.org and add to PATH)\n"
            "Mac:     brew install ffmpeg\n"
            "Linux:   sudo apt install ffmpeg"
        )


def format_srt_timestamp(seconds: float) -> str:
    ms_total = round(seconds * 1000)
    hours, ms_total = divmod(ms_total, 3_600_000)
    minutes, ms_total = divmod(ms_total, 60_000)
    secs, ms = divmod(ms_total, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{ms:03}"


def group_words_into_lines(words: list[dict], per_line: int) -> list[dict]:
    lines = []
    for i in range(0, len(words), per_line):
        chunk = words[i : i + per_line]
        lines.append(
            {
                "text": "".join(w["word"] for w in chunk).strip(),
                "start": chunk[0]["start"],
                "end": chunk[-1]["end"],
            }
        )
    return lines


def write_srt(lines: list[dict], out_path: Path) -> None:
    blocks = []
    for idx, line in enumerate(lines, start=1):
        blocks.append(
            f"{idx}\n"
            f"{format_srt_timestamp(line['start'])} --> {format_srt_timestamp(line['end'])}\n"
            f"{line['text']}\n"
        )
    out_path.write_text("\n".join(blocks), encoding="utf-8")


def main():
    check_ffmpeg()

    voice_path = find_latest_voice()
    timestamp = voice_path.stem.replace("voice_", "")

    print(f"🎧 Transcribing: {voice_path.name}  (model: {MODEL_SIZE})")
    model = whisper.load_model(MODEL_SIZE)
    result = model.transcribe(str(voice_path), word_timestamps=True, language="en")

    # Flatten word-level timestamps across all segments.
    words = []
    for segment in result["segments"]:
        for w in segment.get("words", []):
            words.append({"word": w["word"], "start": w["start"], "end": w["end"]})

    if not words:
        raise SystemExit("Whisper returned no word-level timestamps — try a different model size.")

    lines = group_words_into_lines(words, WORDS_PER_CAPTION)

    srt_path = OUTPUT_DIR / f"captions_{timestamp}.srt"
    write_srt(lines, srt_path)

    words_json_path = OUTPUT_DIR / f"words_{timestamp}.json"
    words_json_path.write_text(json.dumps(words, indent=2, ensure_ascii=False))

    full_text_check = " ".join(w["word"].strip() for w in words)
    print(f"\n✅ Captions saved: {srt_path}")
    print(f"✅ Word timings saved: {words_json_path}")
    print(f"\nTranscribed text (sanity check against the script):\n{full_text_check}")


if __name__ == "__main__":
    main()
