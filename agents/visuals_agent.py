"""
Step 3: Visuals Agent
----------------------
Takes the most recent script JSON (from script_agent.py) and downloads a
few vertical (Shorts-shaped) stock video clips from Pexels that match the
story's topic — no manual footage hunting.

Run:
    python agents/visuals_agent.py
"""

import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("PEXELS_API_KEY")
OUTPUT_DIR = Path(__file__).parent / "output"
SEARCH_URL = "https://api.pexels.com/videos/search"

# How many clips to fetch for one 30s video. 3 clips of ~8-10s each is a
# reasonable starting point; Step 5 (video assembly) will trim to fit.
NUM_CLIPS = 3

# Generic tech/AI B-roll fallback terms, used if the script's own tags
# return nothing useful (Pexels doesn't have every niche term).
FALLBACK_TERMS = ["technology", "artificial intelligence", "computer", "data"]


def find_latest_script() -> Path:
    scripts = sorted(OUTPUT_DIR.glob("script_*.json"))
    if not scripts:
        raise SystemExit(
            "No script_*.json files found in agents/output/. "
            "Run script_agent.py first."
        )
    return scripts[-1]


def search_terms_from_script(data: dict) -> list[str]:
    """Tags are usually the best short search terms; title words as backup."""
    terms = list(data.get("tags", []))
    # Add a couple of words from the title too, in case tags are too niche.
    title_words = [w for w in data.get("title", "").split() if len(w) > 4]
    terms.extend(title_words[:3])
    terms.extend(FALLBACK_TERMS)
    # De-dupe while preserving order.
    seen = set()
    deduped = []
    for t in terms:
        key = t.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(t)
    return deduped


def search_pexels_videos(query: str, per_page: int = 5) -> list[dict]:
    headers = {"Authorization": API_KEY}
    params = {
        "query": query,
        "orientation": "portrait",  # vertical, matches Shorts
        "size": "medium",
        "per_page": per_page,
    }
    resp = requests.get(SEARCH_URL, headers=headers, params=params, timeout=20)
    if resp.status_code == 401:
        raise SystemExit("Pexels rejected the API key — check PEXELS_API_KEY in .env")
    resp.raise_for_status()
    return resp.json().get("videos", [])


def best_video_file(video: dict) -> dict | None:
    """Pick a reasonably sized portrait mp4 file from a Pexels video result."""
    candidates = [
        f for f in video.get("video_files", [])
        if f.get("file_type") == "video/mp4" and f.get("width", 0) < f.get("height", 1)
    ]
    if not candidates:
        return None
    # Prefer something around 720p width to keep downloads/processing light.
    candidates.sort(key=lambda f: abs((f.get("width") or 0) - 720))
    return candidates[0]


def download_file(url: str, dest: Path) -> None:
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 16):
                f.write(chunk)


def main():
    if not API_KEY:
        raise SystemExit(
            "PEXELS_API_KEY is not set. Add it to .env — get a free key at "
            "https://www.pexels.com/api/"
        )

    script_path = find_latest_script()
    data = json.loads(script_path.read_text())
    timestamp = script_path.stem.replace("script_", "")

    terms = search_terms_from_script(data)
    print(f"🔎 Searching Pexels for visuals matching: {data['title']}")

    used_video_ids = set()
    downloaded = []

    for term in terms:
        if len(downloaded) >= NUM_CLIPS:
            break
        try:
            results = search_pexels_videos(term)
        except requests.RequestException as e:
            print(f"⚠️  Search failed for '{term}': {e}")
            continue

        for video in results:
            if len(downloaded) >= NUM_CLIPS:
                break
            if video["id"] in used_video_ids:
                continue
            file_info = best_video_file(video)
            if not file_info:
                continue

            used_video_ids.add(video["id"])
            clip_path = OUTPUT_DIR / f"visual_{timestamp}_{len(downloaded)+1}.mp4"
            print(f"⬇️  Downloading clip for '{term}' (video id {video['id']})...")
            try:
                download_file(file_info["link"], clip_path)
            except requests.RequestException as e:
                print(f"⚠️  Download failed: {e}")
                used_video_ids.discard(video["id"])
                continue

            downloaded.append(
                {
                    "path": str(clip_path),
                    "search_term": term,
                    "pexels_id": video["id"],
                    "pexels_url": video.get("url"),
                    "duration_seconds": video.get("duration"),
                }
            )

    if not downloaded:
        raise SystemExit(
            "Could not find/download any matching clips. Try again later, "
            "or add more terms to FALLBACK_TERMS in this file."
        )

    manifest_path = OUTPUT_DIR / f"visuals_{timestamp}.json"
    manifest_path.write_text(json.dumps(downloaded, indent=2))

    print(f"\n✅ Downloaded {len(downloaded)} clip(s):")
    for clip in downloaded:
        print(f"   - {clip['path']}  ({clip['search_term']}, {clip['duration_seconds']}s)")
    print(f"\nManifest saved: {manifest_path}")

    if len(downloaded) < NUM_CLIPS:
        print(
            f"\n⚠️  Only found {len(downloaded)}/{NUM_CLIPS} clips. Video assembly "
            "will still work, just with fewer visual changes. Consider adding "
            "more search terms if this happens often."
        )


if __name__ == "__main__":
    main()
