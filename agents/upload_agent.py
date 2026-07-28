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

import json
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = Path(__file__).parent / "output"

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
    print(f"\n✅ Uploaded! https://youtube.com/shorts/{video_id}")


if __name__ == "__main__":
    main()
