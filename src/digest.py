"""Assemble the HTML email: Academic Publications first, then regional news.
Each news story is a one-sentence headline, a short description and links."""

import html
from datetime import date

FONT_STACK = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"


def _esc(x):
    return html.escape(str(x or ""))


def _trim(text, limit=900):
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut + "\u2026"


def _link(label, url, color="#1a4fa0"):
    if not url:
        return _esc(label)
    return f'<a href="{_esc(url)}" style="color:{color};text-decoration:none;">{_esc(label)}</a>'


def build_html(lit_items, regions, base_font_size=15, today=None):
    """regions: list of {"name", "stories": [{headline, description, links}]}."""
    today = today or date.today().isoformat()
    b = base_font_size
    parts = [
        f'<div style="font-family:{FONT_STACK};font-size:{b}px;line-height:1.5;'
        f'color:#1a1a1a;max-width:720px;margin:0 auto;">',
        f'<div style="font-size:{b + 6}px;font-weight:700;border-bottom:2px solid #222;'
        f'padding-bottom:6px;margin-bottom:4px;">Weekly Brief &middot; {_esc(today)}</div>',
    ]

    # ---- Academic Publications (top of the email) ----
    parts.append(
        f'<div style="font-size:{b + 3}px;font-weight:700;margin:22px 0 8px;">'
        "Academic Publications</div>"
    )
    if not lit_items:
        parts.append('<div style="color:#777;">No new relevant publications this week.</div>')
    for n, w in enumerate(lit_items, 1):
        parts.append(
            '<div style="margin:14px 0;padding-bottom:12px;border-bottom:1px solid #eee;">'
        )
        parts.append(
            f'<div style="font-weight:700;">{n}. {_link(w["title"], w.get("url"))}</div>'
        )
        authors = ", ".join(w.get("authors", []))
        meta = " &middot; ".join(
            x for x in [_esc(authors), _esc(w.get("journal")), _esc(w.get("date"))] if x
        )
        parts.append(f'<div style="color:#777;margin:2px 0 6px;">{meta}</div>')
        abstract = _trim(w.get("abstract"))
        parts.append(
            f'<div style="color:#333;">{_esc(abstract) if abstract else "<em>Abstract not available.</em>"}</div>'
        )
        if w.get("why_relevant"):
            parts.append(
                f'<div style="margin-top:6px;"><strong>Why relevant:</strong> '
                f'{_esc(w["why_relevant"])}</div>'
            )
        parts.append("</div>")

    # ---- Regional news ----
    parts.append(
        f'<div style="font-size:{b + 3}px;font-weight:700;margin:28px 0 8px;">'
        "Regional Politics News</div>"
    )
    for r in regions:
        parts.append(
            f'<div style="font-size:{b + 2}px;font-weight:700;margin:20px 0 6px;'
            f'border-bottom:1px solid #ddd;padding-bottom:3px;">{_esc(r["name"])}</div>'
        )
        stories = r.get("stories") or []
        if not stories:
            parts.append('<div style="color:#777;">No politically significant news this week.</div>')
        for n, s in enumerate(stories, 1):
            parts.append('<div style="margin:12px 0 14px;">')
            parts.append(f'<div style="font-weight:700;">{n}. {_esc(s["headline"])}</div>')
            if s.get("description"):
                parts.append(f'<div style="margin:3px 0;">{_esc(s["description"])}</div>')
            links = " &middot; ".join(
                _link(l.get("source") or "Read more", l.get("link")) for l in s.get("links", [])
            )
            if links:
                parts.append(f'<div style="color:#777;">Read: {links}</div>')
            parts.append("</div>")

    parts.append(
        f'<div style="font-size:{b - 3}px;color:#aaa;margin-top:28px;">'
        "Literature via OpenAlex &middot; News via Google News &middot; Auto-generated.</div>"
    )
    parts.append("</div>")
    return "\n".join(parts)
