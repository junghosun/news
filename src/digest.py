"""Assemble the HTML email body from literature picks and regional news."""

import html
from datetime import date


def _esc(x):
    return html.escape(str(x or ""))


def build_html(lit_items, region_summaries, today=None):
    today = today or date.today().isoformat()
    parts = [
        "<div style=\"font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;"
        "max-width:720px;margin:0 auto;color:#1a1a1a;line-height:1.55;\">",
        f"<h1 style=\"font-size:20px;border-bottom:2px solid #222;padding-bottom:6px;\">"
        f"每日研究简报 · {today}</h1>",
    ]

    # ---- Literature ----
    parts.append("<h2 style=\"font-size:17px;margin-top:26px;\">新文献</h2>")
    if not lit_items:
        parts.append("<p style=\"color:#666;\">今日没有匹配到相关新文献。</p>")
    for w in lit_items:
        authors = ", ".join(w.get("authors", []))
        score = w.get("score")
        badge = (
            f"<span style=\"background:#eef;border-radius:4px;padding:1px 6px;"
            f"font-size:12px;color:#334;\">相关度 {_esc(score)}/5</span>"
            if score
            else ""
        )
        parts.append("<div style=\"margin:16px 0;padding-bottom:12px;border-bottom:1px solid #eee;\">")
        title = _esc(w["title"])
        if w.get("url"):
            title = f"<a href=\"{_esc(w['url'])}\" style=\"color:#1a4fa0;text-decoration:none;\">{title}</a>"
        parts.append(f"<div style=\"font-size:15px;font-weight:600;\">{title} {badge}</div>")
        parts.append(
            f"<div style=\"font-size:12px;color:#777;margin:2px 0 6px;\">"
            f"{_esc(w.get('journal'))} · {_esc(w.get('date'))}"
            + (f" · {_esc(authors)}" if authors else "")
            + "</div>"
        )
        if w.get("distillation"):
            parts.append(f"<div style=\"font-size:14px;\">{_esc(w['distillation'])}</div>")
        elif w.get("abstract"):
            excerpt = w["abstract"][:500] + ("…" if len(w["abstract"]) > 500 else "")
            parts.append(
                f"<div style=\"font-size:13px;color:#444;\">{_esc(excerpt)}</div>"
            )
        if w.get("relevance"):
            parts.append(
                f"<div style=\"font-size:13px;color:#555;margin-top:4px;\">"
                f"<em>为何相关：</em>{_esc(w['relevance'])}</div>"
            )
        parts.append("</div>")

    # ---- News ----
    parts.append("<h2 style=\"font-size:17px;margin-top:30px;\">地区政治新闻</h2>")
    for region, summary in region_summaries.items():
        parts.append(f"<h3 style=\"font-size:15px;margin:18px 0 4px;\">{_esc(region)}</h3>")
        parts.append(
            f"<div style=\"font-size:14px;white-space:pre-wrap;\">{_esc(summary)}</div>"
        )

    parts.append(
        "<p style=\"font-size:11px;color:#aaa;margin-top:30px;\">"
        "文献来源 OpenAlex，新闻来源 Google News。本邮件由自动化脚本生成。</p>"
    )
    parts.append("</div>")
    return "\n".join(parts)
