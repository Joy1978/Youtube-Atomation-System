# AI/Tech News Shorts — Automation Pipeline

Fully-automated Tech/AI News YouTube Shorts channel. Goal: 3 uploads/day,
~30s each, zero manual work once running, global audience.

## Progress

- [x] **Step 1 — Script Agent**: fetches a real, recent AI/tech news story
      (via free RSS feeds) and writes a 30s spoken script + title
      + description + tags.
- [x] **Step 2 — Voice Agent**: converts the script into narration audio
      using Edge-TTS (free, no API key).
- [ ] Step 3 — Visuals Agent (Pexels/Pixabay: fetch matching stock clips)
- [ ] Step 4 — Captions Agent (Whisper: burn in subtitles)
- [ ] Step 5 — Video Assembly (FFmpeg: combine everything into the final .mp4)
- [ ] Step 6 — Upload Agent (YouTube Data API: auto-publish)
- [ ] Step 7 — GitHub Actions workflow tying it all together on a 3x/day cron

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
