"""Collect the week's political news per region from Google News RSS, then have
Claude pick up to N distinct stories, dropping anything not politically
significant and favouring stories that bear on the research focus."""

import re
import urllib.parse

import feedparser

from .util import extract_json, model_text


def _norm_title(t):
    t = re.sub(r"\s+-\s+[^-]+$", "", t)  # drop trailing " - Source"
    return re.sub(r"\W+", "", t.lower())


def fetch_region_news(queries, hl, gl, ceid, window="7d", per_query=20, max_total=40):
    """Run the base query plus any research-themed extra queries, then merge
    and de-duplicate. `window` (e.g. 1d, 7d) is appended as a when: clause."""
    items, seen = [], set()
    for q in queries:
        if "when:" not in q:
            q = f"{q} when:{window}"
        url = (
            "https://news.google.com/rss/search?q="
            f"{urllib.parse.quote(q)}&hl={hl}&gl={gl}&ceid={ceid}"
        )
        try:
            feed = feedparser.parse(url)
        except Exception as e:
            print(f"  WARNING: news fetch failed for '{q}': {e}")
            continue
        for e in feed.entries[:per_query]:
            title = e.get("title", "")
            key = _norm_title(title)
            if not key or key in seen:
                continue
            seen.add(key)
            source = ""
            if e.get("source") and isinstance(e.source, dict):
                source = e.source.get("title", "")
            items.append(
                {
                    "title": title,
                    "link": e.get("link", ""),
                    "published": e.get("published", ""),
                    "source": source,
                }
            )
    return items[:max_total]


def flat_fallback(items, max_stories):
    """No-model mode: first few headlines, no description."""
    return [
        {"headline": it["title"], "description": "", "links": [it]}
        for it in items[:max_stories]
    ]


def curate_region(region_name, items, client, model, focus, max_stories=5,
                  window_desc="week", out_language="English"):
    """Return up to max_stories dicts of {headline, description, links}, or the
    flat fallback when no model is available."""
    if not items:
        return []
    if client is None:
        return flat_fallback(items, max_stories)

    catalog = "\n".join(
        f"[{i}] {it['title']}" for i, it in enumerate(items)
    )
    prompt = (
        "You are curating weekly political news for a researcher.\n\n"
        f"Reader's focus:\n{focus}\n\n"
        f"Below are news headlines from the past {window_desc} about {region_name}, each "
        "with an index. They may be in the local language.\n\n"
        f"Select up to {max_stories} distinct stories worth the reader's attention, "
        "ordered by importance and by relevance to the reader's focus. Merge headlines "
        "that cover the same event into one story. Skip anything that is not politically "
        "significant, as described in the focus. If nothing qualifies, return an empty "
        "list.\n\n"
        f"For each story write, in {out_language} (British spelling):\n"
        '- "headline": one complete, plain sentence of roughly 12 to 25 words saying '
        "exactly what happened. It must read as a statement of events, not a short label "
        "or title.\n"
        '- "description": two or three sentences giving the rough background and why it '
        "matters politically. Use only what the headlines support; do not invent "
        "details, names or numbers.\n"
        '- "articles": the indices of the headlines that cover this story (one to three).\n\n'
        "Do not use em dashes. Return ONLY valid JSON of the form "
        '{"stories": [{"headline": "...", "description": "...", "articles": [0, 4]}]}. '
        "No prose, no markdown.\n\n"
        f"Headlines:\n{catalog}"
    )
    try:
        msg = client.messages.create(
            model=model, max_tokens=2000, messages=[{"role": "user", "content": prompt}]
        )
        raw = extract_json(model_text(msg), "{", "}").get("stories", [])
    except Exception as e:
        print(f"  WARNING: curation failed for {region_name} ({e}); using headline list")
        return flat_fallback(items, max_stories)

    stories = []
    for s in raw[:max_stories]:
        links = []
        for idx in s.get("articles", []):
            if isinstance(idx, int) and 0 <= idx < len(items):
                links.append(items[idx])
        if s.get("headline") and links:
            stories.append(
                {
                    "headline": s["headline"].strip(),
                    "description": (s.get("description") or "").strip(),
                    "links": links[:3],
                }
            )
    return stories
