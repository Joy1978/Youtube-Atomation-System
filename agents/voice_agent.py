"""
Step 2: Voice Agent
--------------------
Takes the most recent script JSON (from script_agent.py) and turns the
"script" text into a narration .mp3 using Edge-TTS (Microsoft, free,
no API key needed).

Run:
    python agents/voice_agent.py
"""

import asyncio
import json
import sys
from pathlib import Path

import edge_tts

OUTPUT_DIR = Path(__file__).parent / "output"

# Change this to try a different voice/style.
# Full list: run `edge-tts --list-voices` in your terminal.
VOICE = "en-US-GuyNeural"

# Speech rate. "+0%" = normal. Use "+10%" / "-10%" etc. to nudge pacing
# so a ~80-word script lands close to 30 seconds.
RATE = "+0%"


def find_latest_script() -> Path:
    scripts = sorted(OUTPUT_DIR.glob("script_*.json"))
    if not scripts:
        raise SystemExit(
            "No script_*.json files found in agents/output/. "
            "Run script_agent.py first."
        )
    return scripts[-1]


async def generate_voice(text: str, out_path: Path) -> None:
    communicate = edge_tts.Communicate(text, voice=VOICE, rate=RATE)
    await communicate.save(str(out_path))


def main():
    script_path = find_latest_script()
    data = json.loads(script_path.read_text())
    script_text = data["script"]

    # Match the audio filename to the script's timestamp so Step 3/4/5
    # can pair them up easily.
    timestamp = script_path.stem.replace("script_", "")
    out_path = OUTPUT_DIR / f"voice_{timestamp}.mp3"

    print(f"🗣️  Generating voice for: {data['title']}")
    print(f"   Voice: {VOICE}  |  Rate: {RATE}")

    asyncio.run(generate_voice(script_text, out_path))

    print(f"✅ Voice saved: {out_path}")
    print(
        "\nListen to it and check:\n"
        "  - Does it land close to 30 seconds? If it's noticeably longer, "
        "increase RATE (e.g. '+10%') and rerun.\n"
        "  - Does the voice/pacing fit the channel? Change VOICE at the "
        "top of this file to try another (see `edge-tts --list-voices`)."
    )


if __name__ == "__main__":
    if sys.version_info < (3, 8):
        raise SystemExit("Python 3.8+ required.")
    main()
