"""Assemble the HTML email body from regional news and literature picks.
News comes first (daily); literature follows (intermittent). News is grouped
into themes, each with its own summary and its own links."""

import html
from datetime import date

FONT_STACK = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"


def _esc(x):
    return html.escape(str(x or ""))


def _headline(it, base):
    title = _esc(it["title"])
    if it.get("link"):
        title = (
            f'<a href="{_esc(it["link"])}" '
            f'style="color:#1a4fa0;text-decoration:none;">{title}</a>'
        )
    src = (
        f' <span style="color:#888;">&mdash; {_esc(it["source"])}</span>'
        if it.get("source")
        else ""
    )
    return f'<div style="margin:4px 0;font-size:{base - 1}px;">{title}{src}</div>'


def build_html(lit_items, regions, base_font_size=15, today=None):
    """regions: list of {"name", "themes" (list|None), "items": [...]}.
    A theme is {"heading", "summary", "items": [{title, link, source}]}."""
    today = today or date.today().isoformat()
    base = base_font_size
    container = (
        f"font-family:{FONT_STACK};font-size:{base}px;line-height:1.5;"
        f"color:#1a1a1a;max-width:720px;margin:0 auto;"
    )
    parts = [f'<div style="{container}">']
    parts.append(
        f'<div style="font-size:{base + 6}px;font-weight:700;'
        f'border-bottom:2px solid #222;padding-bottom:6px;margin-bottom:4px;">'
        f'Daily Brief &middot; {today}</div>'
    )

    # ---- News first ----
    parts.append(
        f'<div style="font-size:{base + 3}px;font-weight:700;margin:22px 0 8px;">'
        f'Regional Politics News</div>'
    )
    for r in regions:
        parts.append(
            f'<div style="font-size:{base + 2}px;font-weight:700;margin:18px 0 6px;'
            f'border-bottom:1px solid #ddd;padding-bottom:3px;">{_esc(r["name"])}</div>'
        )
        themes = r.get("themes")
        if themes:
            for n, t in enumerate(themes, 1):
                if t.get("heading"):
                    parts.append(
                        f'<div style="font-weight:700;margin:12px 0 3px;">'
                        f'{n}. {_esc(t["heading"])}</div>'
                    )
                if t.get("summary"):
                    parts.append(f'<div style="margin-bottom:5px;">{_esc(t["summary"])}</div>')
                for it in t.get("items", []):
                    parts.append(_headline(it, base))
        else:
            items = r.get("items") or []
            if not items:
                parts.append('<div style="color:#777;">No news today.</div>')
            for it in items:
                parts.append(_headline(it, base))

    # ---- Literature after ----
    parts.append(
        f'<div style="font-size:{base + 3}px;font-weight:700;margin:28px 0 8px;">'
        f'New Publications</div>'
    )
    if not lit_items:
        parts.append('<div style="color:#777;">No new matching publications today.</div>')
    for w in lit_items:
        authors = ", ".join(w.get("authors", []))
        score = w.get("score")
        badge = (
            f' <span style="background:#eef;border-radius:4px;padding:1px 6px;'
            f'font-size:{base - 3}px;color:#334;">relevance {_esc(score)}/5</span>'
            if score
            else ""
        )
        parts.append(
            '<div style="margin:14px 0;padding-bottom:10px;border-bottom:1px solid #eee;">'
        )
        title = _esc(w["title"])
        if w.get("url"):
            title = (
                f'<a href="{_esc(w["url"])}" '
                f'style="color:#1a4fa0;text-decoration:none;">{title}</a>'
            )
        parts.append(f'<div style="font-weight:700;">{title}{badge}</div>')
        meta = _esc(w.get("journal")) + " &middot; " + _esc(w.get("date"))
        if authors:
            meta += " &middot; " + _esc(authors)
        parts.append(
            f'<div style="font-size:{base - 2}px;color:#777;margin:2px 0 5px;">{meta}</div>'
        )
        if w.get("distillation"):
            parts.append(f'<div>{_esc(w["distillation"])}</div>')
        elif w.get("abstract"):
            excerpt = w["abstract"][:500] + ("\u2026" if len(w["abstract"]) > 500 else "")
            parts.append(f'<div style="color:#444;">{_esc(excerpt)}</div>')
        if w.get("relevance"):
            parts.append(
                f'<div style="color:#555;margin-top:4px;">'
                f'<em>Why relevant:</em> {_esc(w["relevance"])}</div>'
            )
        parts.append("</div>")

    parts.append(
        f'<div style="font-size:{base - 3}px;color:#aaa;margin-top:28px;">'
        f'Literature via OpenAlex &middot; News via Google News &middot; Auto-generated.</div>'
    )
    parts.append("</div>")
    return "\n".join(parts)
