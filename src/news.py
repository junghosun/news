"""Collect same-day political news per region from Google News RSS and
summarise each region with Claude."""

import urllib.parse

import feedparser


def fetch_region_news(query, hl, gl, ceid, max_items=15):
    """query: search terms (a `when:1d` clause keeps it to the last day).
    hl/gl/ceid: Google News locale params, e.g. hl=ko, gl=KR, ceid=KR:ko."""
    q = urllib.parse.quote(query)
    url = (
        f"https://news.google.com/rss/search?q={q}"
        f"&hl={hl}&gl={gl}&ceid={ceid}"
    )
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


def summarize_region(region_name, items, client, model, out_language="中文"):
    """Return a short prose summary of the region's day. Falls back to a
    headline list when no model client is available."""
    if not items:
        return "（今日无相关新闻）"
    headlines = "\n".join(
        f"- {it['title']}" + (f" ({it['source']})" if it["source"] else "")
        for it in items
    )
    if client is None:
        return headlines
    prompt = (
        f"以下是关于{region_name}的今日新闻标题。请用{out_language}写一段简洁的综述"
        "（3-5 句），提炼今天该地区政治领域最重要的动态与主题，突出趋势和关联，"
        "不要逐条罗列，不要编造标题之外的内容。\n\n"
        f"标题：\n{headlines}"
    )
    msg = client.messages.create(
        model=model,
        max_tokens=700,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in msg.content if b.type == "text").strip()
