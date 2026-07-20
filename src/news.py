"""Collect same-day political news per region from Google News RSS and
(optionally) group + summarise each region into themes with Claude."""

import json
import urllib.parse

import feedparser


def fetch_region_news(query, hl, gl, ceid, max_items=15):
    """query: search terms (a `when:1d` clause keeps it to the last day).
    hl/gl/ceid: Google News locale params, e.g. hl=ko, gl=KR, ceid=KR:ko."""
    q = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={ceid}"
    feed = feedparser.parse(url)
    items = []
    for e in feed.entries[:max_items]:
        source = ""
        if e.get("source") and isinstance(e.source, dict):
            source = e.source.get("title", "")
        items.append(
            {
                "title": e.get("title", ""),
                "link": e.get("link", ""),
                "published": e.get("published", ""),
                "source": source,
            }
        )
    return items


def summarize_region(region_name, items, client, model, out_language="English"):
    """Group the day's headlines into themes and summarise each one.
    Returns a list of {"heading", "summary", "items": [...]} ordered by
    importance, or None when no model is available (digest then lists
    headlines flat)."""
    if client is None or not items:
        return None
    catalog = "\n".join(
        f"[{i}] {it['title']}" + (f" ({it['source']})" if it["source"] else "")
        for i, it in enumerate(items)
    )
    prompt = (
        f"Below are today's news headlines about {region_name}, each with an index.\n\n"
        f"Group them into 2-5 themes (the day's main stories), ordered by importance. "
        f"Assign EVERY article to exactly one theme. For each theme write, in "
        f"{out_language}: a short heading (3-6 words) and a 2-4 sentence summary that "
        f"explains what happened, why it matters, and any key figures or statements. "
        f"Do not invent anything beyond the headlines.\n\n"
        f'Return ONLY valid JSON of the form '
        f'{{"themes": [{{"heading": "...", "summary": "...", "articles": [0, 2]}}]}}. '
        f"No prose, no markdown.\n\nHeadlines:\n{catalog}"
    )
    msg = client.messages.create(
        model=model,
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{") :] if "{" in text else text
    try:
        raw_themes = json.loads(text).get("themes", [])
    except Exception:
        return None  # fall back to a flat headline list

    themes, used = [], set()
    for t in raw_themes:
        theme_items = []
        for idx in t.get("articles", []):
            if isinstance(idx, int) and 0 <= idx < len(items) and idx not in used:
                theme_items.append(items[idx])
                used.add(idx)
        themes.append(
            {
                "heading": t.get("heading", ""),
                "summary": t.get("summary", ""),
                "items": theme_items,
            }
        )
    leftovers = [items[i] for i in range(len(items)) if i not in used]
    if leftovers:
        themes.append({"heading": "More", "summary": "", "items": leftovers})
    return themes
