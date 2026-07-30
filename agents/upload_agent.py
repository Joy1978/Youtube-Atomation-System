"""
Step 6: Upload Agent
----------------------
Uploads the final video (from video_agent.py) to YouTube as a Short.

One-time setup required before this works — see README.md "Step 6 setup"
section. In short: you need client_secret.json (from Google Cloud
Console) in the project root, and the first run will open a browser for
you to log in and grant access. After that, a token.json is saved and
reused automatically (no more browser prompts) — until it needs one
manual re-publish step, also covered in the README.

Run:
    python agents/upload_agent.py
"""

import csv
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import gspread
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

load_dotenv()

PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = Path(__file__).parent / "output"
LOG_FILE = PROJECT_ROOT / "upload_log.csv"
SERVICE_ACCOUNT_FILE = PROJECT_ROOT / "service_account.json"
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")

CLIENT_SECRET_FILE = PROJECT_ROOT / "client_secret.json"
TOKEN_FILE = PROJECT_ROOT / "token.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

# 28 = "Science & Technology" — see https://developers.google.com/youtube/v3/docs/videoCategories/list
CATEGORY_ID = "28"

# public | unlisted | private — start with "unlisted" or "private" while
# you're still checking output quality, switch to "public" once confident.
PRIVACY_STATUS = "public"


def find_latest(pattern: str) -> Path:
    matches = sorted(OUTPUT_DIR.glob(pattern))
    if not matches:
        raise SystemExit(f"No files matching {pattern} in agents/output/. Run earlier steps first.")
    return matches[-1]


def get_credentials() -> Credentials:
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

    if not creds or not creds.valid:
        if not CLIENT_SECRET_FILE.exists():
            raise SystemExit(
                f"{CLIENT_SECRET_FILE.name} not found in project root. "
                "Download it from Google Cloud Console — see README.md Step 6 setup."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), SCOPES)
        creds = flow.run_local_server(port=0)

    TOKEN_FILE.write_text(creds.to_json())
    return creds


def ensure_shorts_hashtag(text: str) -> str:
    return text if "#Shorts" in text else f"{text}\n\n#Shorts"


def log_upload(video_id: str, title: str, source_link: str) -> None:
    now = datetime.now(ZoneInfo("Asia/Colombo"))
    row = [
        now.strftime("%Y-%m-%d"),
        now.strftime("%H:%M:%S"),
        title,
        video_id,
        f"https://youtube.com/shorts/{video_id}",
        source_link,
    ]

    # Always write the local CSV first — it's the safety net if the
    # Sheets call fails for any reason (network, permissions, etc).
    is_new_file = not LOG_FILE.exists()
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if is_new_file:
            writer.writerow(["date", "time_colombo", "title", "video_id", "video_url", "source_article"])
        writer.writerow(row)

    if not SERVICE_ACCOUNT_FILE.exists() or not GOOGLE_SHEET_ID:
        print("ℹ️  Google Sheet logging not configured — logged to upload_log.csv only.")
        return

    try:
        gc = gspread.service_account(filename=str(SERVICE_ACCOUNT_FILE))
        sheet = gc.open_by_key(GOOGLE_SHEET_ID).sheet1
        sheet.append_row(row)
        print("📋 Logged to Google Sheet.")
    except Exception as e:
        print(f"⚠️  Google Sheet logging failed ({e}) — entry is still saved in upload_log.csv.")


def set_custom_thumbnail(youtube, video_id: str, thumbnail_path: Path) -> None:
    if not thumbnail_path.exists():
        print("ℹ️  No thumbnail file found — skipping custom thumbnail (YouTube will auto-pick one).")
        return
    try:
        youtube.thumbnails().set(
            videoId=video_id, media_body=MediaFileUpload(str(thumbnail_path))
        ).execute()
        print("🖼️  Custom thumbnail set.")
    except Exception as e:
        # Custom thumbnails require a phone-verified YouTube channel —
        # this fails cleanly (not a pipeline-breaking error) if that's not done yet.
        print(
            f"⚠️  Could not set custom thumbnail ({e}). This usually means the "
            "channel isn't phone-verified yet — verify it in YouTube Studio "
            "under Settings > Channel > Feature eligibility, then this will work. "
            "The video still uploaded fine; YouTube just auto-picked a thumbnail instead."
        )


def main():
    script_path = find_latest("script_*.json")
    timestamp = script_path.stem.replace("script_", "")
    data = json.loads(script_path.read_text())

    video_path = OUTPUT_DIR / f"final_{timestamp}.mp4"
    if not video_path.exists():
        raise SystemExit(f"{video_path.name} not found — run video_agent.py first.")

    print("🔑 Authenticating with YouTube...")
    creds = get_credentials()
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": data["title"][:100],
            "description": ensure_shorts_hashtag(data["description"]),
            "tags": data.get("tags", []),
            "categoryId": CATEGORY_ID,
        },
        "status": {
            "privacyStatus": PRIVACY_STATUS,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True, mimetype="video/mp4")

    print(f"📤 Uploading: {data['title']}")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"   Upload progress: {int(status.progress() * 100)}%")

    video_id = response["id"]

    thumbnail_path = OUTPUT_DIR / f"thumbnail_{timestamp}.jpg"
    set_custom_thumbnail(youtube, video_id, thumbnail_path)

    log_upload(video_id, data["title"], data.get("source_link", ""))

    print(f"\n✅ Uploaded! https://youtube.com/shorts/{video_id}")


if __name__ == "__main__":
    main()