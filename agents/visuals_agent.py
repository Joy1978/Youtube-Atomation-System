"""
Step 3: Visuals Agent
----------------------
Builds the set of visual assets for one video:
  1. A screenshot of the actual source article (via Playwright) — adds
     specificity/accuracy that generic stock footage can't.
  2. Stock video clips from Pexels matching the story's tags/title.
  3. Stock photos from Pexels as a fallback/supplement when video clips
     run out (photos have a much bigger library for niche terms) — these
     get a Ken Burns zoom effect applied in Step 5 so they're not static.

Tracks which Pexels IDs have been used before (agents/state/used_visuals.json,
committed to git) so repeated runs don't keep reusing the same handful of
clips for generic terms like "technology" or "AI".

Run:
    python agents/visuals_agent.py
"""

import json
import os
import random
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("PEXELS_API_KEY")
OUTPUT_DIR = Path(__file__).parent / "output"
STATE_DIR = Path(__file__).parent / "state"
USED_VISUALS_FILE = STATE_DIR / "used_visuals.json"

VIDEO_SEARCH_URL = "https://api.pexels.com/videos/search"
PHOTO_SEARCH_URL = "https://api.pexels.com/v1/search"

NUM_CLIPS = 3  # total visual segments per video, screenshot included
INCLUDE_SCREENSHOT = True

FALLBACK_TERMS = ["technology", "artificial intelligence", "computer", "data", "network", "digital"]

# How many random "pages" of Pexels results to shuffle through per term —
# spreads results out instead of always hitting the same top matches.
PAGE_POOL = [1, 2, 3, 4]


# ---------- state (cross-run dedup) ----------

def load_used_ids(limit: int = 500) -> set:
    if not USED_VISUALS_FILE.exists():
        return set()
    try:
        data = json.loads(USED_VISUALS_FILE.read_text())
        return set(data[-limit:])
    except (json.JSONDecodeError, OSError):
        return set()


def save_used_ids(new_ids: list, limit: int = 500) -> None:
    existing = load_used_ids(limit=10_000)
    combined = list(existing) + [i for i in new_ids if i not in existing]
    STATE_DIR.mkdir(exist_ok=True)
    USED_VISUALS_FILE.write_text(json.dumps(combined[-limit:], indent=2))


# ---------- helpers ----------

def find_latest_script() -> Path:
    scripts = sorted(OUTPUT_DIR.glob("script_*.json"))
    if not scripts:
        raise SystemExit("No script_*.json files found. Run script_agent.py first.")
    return scripts[-1]


def search_terms_from_script(data: dict) -> list[str]:
    terms = list(data.get("tags", []))
    title_words = [w for w in data.get("title", "").split() if len(w) > 4]
    terms.extend(title_words[:3])
    terms.extend(FALLBACK_TERMS)
    seen, deduped = set(), []
    for t in terms:
        key = t.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(t)
    random.shuffle(deduped[: len(deduped) - len(FALLBACK_TERMS)])  # keep fallback order stable at the end
    return deduped


def download_file(url: str, dest: Path) -> None:
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 16):
                f.write(chunk)


# ---------- source screenshot ----------

def capture_source_screenshot(url: str, out_path: Path) -> bool:
    if not url:
        return False
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("⚠️  Playwright not installed — skipping source screenshot.")
        return False

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1080, "height": 1920})
            page.goto(url, timeout=25000, wait_until="domcontentloaded")
            # Try to dismiss common cookie banners so they don't dominate the shot.
            for selector in ["text=Accept", "text=I Agree", "text=Accept All"]:
                try:
                    page.click(selector, timeout=1500)
                    break
                except Exception:
                    pass
            page.wait_for_timeout(1200)
            page.screenshot(path=str(out_path))
            browser.close()
        return True
    except Exception as e:
        print(f"⚠️  Screenshot capture failed ({e}) — continuing without it.")
        return False


# ---------- Pexels video search ----------

def search_pexels_videos(query: str, page: int, per_page: int = 6) -> list[dict]:
    headers = {"Authorization": API_KEY}
    params = {"query": query, "orientation": "portrait", "size": "medium", "per_page": per_page, "page": page}
    resp = requests.get(VIDEO_SEARCH_URL, headers=headers, params=params, timeout=20)
    if resp.status_code == 401:
        raise SystemExit("Pexels rejected the API key — check PEXELS_API_KEY in .env")
    resp.raise_for_status()
    return resp.json().get("videos", [])


def best_video_file(video: dict) -> dict | None:
    candidates = [
        f for f in video.get("video_files", [])
        if f.get("file_type") == "video/mp4" and f.get("width", 0) < f.get("height", 1)
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda f: abs((f.get("width") or 0) - 720))
    return candidates[0]


# ---------- Pexels photo search (fallback/supplement) ----------

def search_pexels_photos(query: str, page: int, per_page: int = 6) -> list[dict]:
    headers = {"Authorization": API_KEY}
    params = {"query": query, "orientation": "portrait", "size": "large", "per_page": per_page, "page": page}
    resp = requests.get(PHOTO_SEARCH_URL, headers=headers, params=params, timeout=20)
    if resp.status_code == 401:
        raise SystemExit("Pexels rejected the API key — check PEXELS_API_KEY in .env")
    resp.raise_for_status()
    return resp.json().get("photos", [])


# ---------- main ----------

def main():
    if not API_KEY:
        raise SystemExit("PEXELS_API_KEY is not set. Add it to .env — https://www.pexels.com/api/")

    script_path = find_latest_script()
    data = json.loads(script_path.read_text())
    timestamp = script_path.stem.replace("script_", "")

    used_ids = load_used_ids()
    newly_used_ids = []
    downloaded = []

    # 1) Source article screenshot, if we can get one.
    if INCLUDE_SCREENSHOT:
        shot_path = OUTPUT_DIR / f"visual_{timestamp}_0_screenshot.jpg"
        print(f"📸 Capturing source screenshot: {data.get('source_link', '(no link)')}")
        if capture_source_screenshot(data.get("source_link", ""), shot_path):
            downloaded.append(
                {"path": str(shot_path), "type": "image", "search_term": "source_screenshot",
                 "pexels_id": None, "duration_seconds": None}
            )

    # 2) Stock video clips.
    terms = search_terms_from_script(data)
    print(f"🔎 Searching Pexels videos for: {data['title']}")
    for term in terms:
        if len(downloaded) >= NUM_CLIPS:
            break
        page = random.choice(PAGE_POOL)
        try:
            results = search_pexels_videos(term, page=page)
        except requests.RequestException as e:
            print(f"⚠️  Video search failed for '{term}': {e}")
            continue

        for video in results:
            if len(downloaded) >= NUM_CLIPS:
                break
            vid = video["id"]
            if vid in used_ids or vid in newly_used_ids:
                continue
            file_info = best_video_file(video)
            if not file_info:
                continue

            clip_path = OUTPUT_DIR / f"visual_{timestamp}_{len(downloaded)+1}.mp4"
            print(f"⬇️  Video clip for '{term}' (id {vid})...")
            try:
                download_file(file_info["link"], clip_path)
            except requests.RequestException as e:
                print(f"⚠️  Download failed: {e}")
                continue

            newly_used_ids.append(vid)
            downloaded.append(
                {"path": str(clip_path), "type": "video", "search_term": term,
                 "pexels_id": vid, "duration_seconds": video.get("duration")}
            )

    # 3) Fill any remaining slots with stock photos (Ken Burns'd in Step 5).
    if len(downloaded) < NUM_CLIPS:
        print(f"🔎 Filling {NUM_CLIPS - len(downloaded)} remaining slot(s) with photos...")
        for term in terms:
            if len(downloaded) >= NUM_CLIPS:
                break
            page = random.choice(PAGE_POOL)
            try:
                results = search_pexels_photos(term, page=page)
            except requests.RequestException as e:
                print(f"⚠️  Photo search failed for '{term}': {e}")
                continue

            for photo in results:
                if len(downloaded) >= NUM_CLIPS:
                    break
                pid = photo["id"]
                photo_key = f"photo_{pid}"
                if photo_key in used_ids or photo_key in newly_used_ids:
                    continue
                img_url = photo.get("src", {}).get("large2x") or photo.get("src", {}).get("large")
                if not img_url:
                    continue

                img_path = OUTPUT_DIR / f"visual_{timestamp}_{len(downloaded)+1}.jpg"
                print(f"⬇️  Photo for '{term}' (id {pid})...")
                try:
                    download_file(img_url, img_path)
                except requests.RequestException as e:
                    print(f"⚠️  Download failed: {e}")
                    continue

                newly_used_ids.append(photo_key)
                downloaded.append(
                    {"path": str(img_path), "type": "image", "search_term": term,
                     "pexels_id": photo_key, "duration_seconds": None}
                )

    if not downloaded:
        raise SystemExit("Could not gather any visuals (screenshot, video, or photo). Try again later.")

    save_used_ids(newly_used_ids)

    manifest_path = OUTPUT_DIR / f"visuals_{timestamp}.json"
    manifest_path.write_text(json.dumps(downloaded, indent=2))

    print(f"\n✅ Gathered {len(downloaded)} visual asset(s):")
    for clip in downloaded:
        print(f"   - [{clip['type']}] {clip['path']}  ({clip['search_term']})")
    print(f"\nManifest saved: {manifest_path}")


if __name__ == "__main__":
    main()