"""
Step 1: Script Agent
---------------------
Pulls a fresh, real AI/tech news story from free RSS feeds (no grounding
tool, no search-related billing surprises) and turns it into a ~30 second
YouTube Shorts script + title + description + tags via Gemini.

Output: writes agents/output/script_<timestamp>.json which the next
agent (voice_agent.py, Step 2) will consume.

Setup:
    pip install -r requirements.txt
    cp .env.example .env   # then paste your free Gemini API key in

Run:
    python agents/script_agent.py
"""

import os
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import feedparser
from dotenv import load_dotenv
from google import genai

load_dotenv()

API_KEY = os.environ.get("GEMINI_API_KEY")
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
OUTPUT_DIR = Path(__file__).parent / "output"
HISTORY_FILE = OUTPUT_DIR / "recent_topics.json"

# Free, no-key-needed RSS feeds. Add/remove sources here freely.
RSS_FEEDS = [
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://venturebeat.com/category/ai/feed/",
    "https://www.artificialintelligence-news.com/feed/",
]


def load_recent_topics(limit: int = 100) -> list[str]:
    if not HISTORY_FILE.exists():
        return []
    try:
        return json.loads(HISTORY_FILE.read_text())[-limit:]
    except (json.JSONDecodeError, OSError):
        return []


def save_recent_topic(identifier: str) -> None:
    history = load_recent_topics(limit=200)
    history.append(identifier)
    HISTORY_FILE.write_text(json.dumps(history[-200:], indent=2))


def fetch_candidate_articles(max_per_feed: int = 8) -> list[dict]:
    """Pull recent entries from each feed. Returns list of {title, summary, link, source}."""
    articles = []
    for feed_url in RSS_FEEDS:
        try:
            parsed = feedparser.parse(feed_url)
        except Exception as e:
            print(f"⚠️  Could not read feed {feed_url}: {e}")
            continue

        for entry in parsed.entries[:max_per_feed]:
            summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
            # Strip any HTML tags from the summary
            summary = re.sub(r"<[^>]+>", "", summary).strip()
            articles.append(
                {
                    "title": getattr(entry, "title", "").strip(),
                    "summary": summary[:500],
                    "link": getattr(entry, "link", ""),
                    "source": parsed.feed.get("title", feed_url),
                }
            )
    return articles


def pick_unused_article(articles: list[dict], used_links: list[str]) -> dict | None:
    for article in articles:
        if article["link"] and article["link"] not in used_links:
            return article
    return None


def build_prompt(article: dict) -> str:
    return f"""You are the script writer for a fast-growing, faceless YouTube
Shorts channel about AI and technology news, for a global English-speaking
audience.

Here is a real, current news story to base the video on:

Title: {article['title']}
Source: {article['source']}
Summary: {article['summary']}

Write a 30-second Shorts script based ONLY on the facts in the title and
summary above. Do not invent numbers, dates, or details not present there.

Hard requirements:
- Spoken script: 70-85 words total (this is read aloud by text-to-speech,
  so it must sound natural spoken, not written).
- Hook in the first sentence (must stop someone scrolling in under 2 seconds).
- Plain, punchy, conversational sentences. Briefly explain any jargon.
- End on a punchy line, a question, or a "why this matters" beat.

Return ONLY valid JSON, no markdown fences, no commentary, in exactly this
shape:

{{
  "title": "YouTube title, under 60 characters, curiosity-driven, no clickbait lies",
  "script": "the 70-85 word spoken script",
  "description": "2-3 sentence YouTube description, include the core fact and one relevant hashtag",
  "tags": ["5", "to", "8", "relevant", "tags"]
}}
"""


def extract_json(text: str) -> dict:
    """Gemini sometimes wraps JSON in ```json fences despite instructions - strip them."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    return json.loads(cleaned)


def generate_script() -> dict:
    if not API_KEY:
        raise SystemExit(
            "GEMINI_API_KEY is not set. Copy .env.example to .env and add your "
            "free key from https://aistudio.google.com/apikey"
        )

    print("📡 Fetching latest AI/tech news from RSS feeds...")
    articles = fetch_candidate_articles()
    if not articles:
        raise SystemExit("No articles found from any feed. Check your internet connection / feed URLs.")

    used_links = load_recent_topics()
    article = pick_unused_article(articles, used_links)
    if article is None:
        raise SystemExit(
            "All fetched articles were already used recently. Try again later "
            "once feeds have new stories, or add more RSS sources."
        )

    print(f"📰 Using: {article['title']}  ({article['source']})")

    client = genai.Client(api_key=API_KEY)
    response = client.models.generate_content(
        model=MODEL,
        contents=build_prompt(article),
    )

    data = extract_json(response.text)

    required_keys = {"title", "script", "description", "tags"}
    missing = required_keys - data.keys()
    if missing:
        raise ValueError(f"Model output missing keys: {missing}\nRaw: {response.text}")

    data["source_title"] = article["title"]
    data["source_link"] = article["link"]
    data["word_count"] = len(data["script"].split())
    data["generated_at"] = datetime.now(timezone.utc).isoformat()

    if not (60 <= data["word_count"] <= 100):
        print(
            f"⚠️  Warning: script is {data['word_count']} words (target 70-85). "
            "Still saved, but review before using."
        )

    save_recent_topic(article["link"])
    return data


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    data = generate_script()

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = OUTPUT_DIR / f"script_{timestamp}.json"
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    print(f"\n✅ Script generated: {out_path}")
    print(f"\nTitle: {data['title']}")
    print(f"Words: {data['word_count']}")
    print(f"\nScript:\n{data['script']}")


if __name__ == "__main__":
    main()
