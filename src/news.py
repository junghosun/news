"""Collect same-day political news per region from Google News RSS and
(optionally) summarise each region with Claude."""

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
    """Return a short prose summary, or None when no model is available
    (in which case the digest just lists the headlines)."""
    if client is None or not items:
        return None
    headlines = "\n".join(
        f"- {it['title']}" + (f" ({it['source']})" if it["source"] else "")
        for it in items
    )
    prompt = (
        f"Below are today's news headlines about {region_name}. Write a concise "
        f"summary (3-5 sentences) in {out_language} capturing the most important "
        f"political developments and themes today. Highlight trends and connections "
        f"rather than listing items one by one. Do not invent anything beyond the "
        f"headlines.\n\nHeadlines:\n{headlines}"
    )
    msg = client.messages.create(
        model=model,
        max_tokens=700,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in msg.content if b.type == "text").strip()
