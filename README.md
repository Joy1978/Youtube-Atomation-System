# AI/Tech News Shorts — Automation Pipeline

Fully-automated Tech/AI News YouTube Shorts channel. Goal: 3 uploads/day,
~30s each, zero manual work once running, global audience.

## Progress

- [x] **Step 1 — Script Agent**: fetches a real, recent AI/tech news story
      (via free RSS feeds) and writes a 30s spoken script + title
      + description + tags.
- [x] **Step 2 — Voice Agent**: converts the script into narration audio
      using Edge-TTS (free, no API key).
- [x] **Step 3 — Visuals Agent**: downloads matching vertical stock video
      clips from Pexels based on the script's tags/title.
- [x] **Step 4 — Captions Agent**: transcribes the narration with Whisper
      and generates short-form burn-in captions (.srt + word timings).
- [x] **Step 5 — Video Assembly**: combines voice + visuals + burned-in
      captions into the final vertical 1080x1920 .mp4 via ffmpeg.
- [x] **Step 6 — Upload Agent**: auto-publishes to YouTube via the Data
      API, logs each upload to Google Sheets (+ local CSV backup).
- [x] **Step 7 — GitHub Actions**: runs the full pipeline automatically
      3x/day (7:00 AM, 5:00 PM, 9:30 PM Colombo time) — see
      "Step 7 setup" below to activate it.

## Step 7 setup — required GitHub Secrets

Go to your repo → **Settings → Secrets and variables → Actions → New
repository secret**, and add each of these:

| Secret name | Value |
|---|---|
| `GEMINI_API_KEY` | same as your local `.env` |
| `PEXELS_API_KEY` | same as your local `.env` |
| `GOOGLE_SHEET_ID` | same as your local `.env` |
| `CLIENT_SECRET_JSON` | paste the **entire contents** of your local `client_secret.json` |
| `TOKEN_JSON` | paste the **entire contents** of your local `token.json` |
| `SERVICE_ACCOUNT_JSON` | paste the **entire contents** of your local `service_account.json` |

**Before adding `TOKEN_JSON`**: make sure you already published your OAuth
consent screen to Production (Testing-mode tokens expire in 7 days and
will silently break the automation).

Once the secrets are set, the workflow at
`.github/workflows/publish.yml` runs automatically on schedule. You can
also trigger it manually anytime from the repo's **Actions** tab →
"Publish AI News Short" → "Run workflow" — useful for testing before
you trust the schedule.

The workflow commits `agents/state/recent_topics.json` and
`upload_log.csv` back to the repo after each run, so duplicate-topic
avoidance and the upload history both persist across runs.

## Setup (Step 1)

1. Get a **free** Gemini API key: https://aistudio.google.com/apikey
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy the env template and paste your key in:
   ```bash
   cp .env.example .env
   ```
4. Run it:
   ```bash
   python agents/script_agent.py
   ```

This prints the generated title + script to the terminal and saves the
full JSON to `agents/output/script_<timestamp>.json`. It also keeps a
`recent_topics.json` file so the same story isn't repeated across runs —
important once this is running 3x/day automatically.

## Notes

- News comes from free RSS feeds (TechCrunch AI, VentureBeat AI, AI News),
  not Gemini's search grounding tool — grounding often needs a
  billing-enabled project even for light use, which breaks the "zero cost"
  requirement. RSS is free and unlimited. Add more feeds in
  `RSS_FEEDS` inside `script_agent.py` if you want more variety.
- The model name in `.env` (`GEMINI_MODEL`) may need updating over time —
  check https://ai.google.dev/gemini-api/docs/models for the current
  recommended flash model before your first run, and again if you start
  seeing errors (model names get deprecated/replaced fast — Google shipped
  a whole new lineup on July 21, 2026 alone).
- The script only uses facts present in the RSS title/summary — reduces
  (but doesn't eliminate) hallucination risk. Still worth spot-checking
  output during the first week.