"""Daily research digest: new political science literature + regional news,
delivered by email. Run once; schedule with GitHub Actions or cron."""

import os
import sys
from datetime import date

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src import literature, news, digest, mailer  # noqa: E402


def get_client(api_key):
    """Return an Anthropic client, or None to run in the no-model fallback."""
    if not api_key:
        print("No ANTHROPIC_API_KEY set -> running without model (headlines / keyword ranking only).")
        return None
    import anthropic

    return anthropic.Anthropic(api_key=api_key)


def main():
    cfg_path = os.environ.get("CONFIG", "config.yaml")
    with open(cfg_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    client = get_client(api_key)
    model = cfg.get("model", "claude-haiku-4-5-20251001")
    mailto = cfg["contact_email"]  # OpenAlex "polite pool" identifier

    # ---------- Literature ----------
    print("Resolving journals...")
    resolved = literature.resolve_source_ids(
        cfg["journals"], mailto, cfg.get("source_cache", "sources.json")
    )
    source_ids = list(resolved.values())

    print("Fetching recent works...")
    works = literature.fetch_recent_works(
        source_ids, cfg.get("lookback_days", 7), mailto
    )
    works, seen = literature.drop_seen(works, cfg.get("seen_cache", "seen.json"))
    print(f"  {len(works)} new works before filtering")

    works = literature.keyword_prefilter(works, cfg.get("keywords", []))
    print(f"  {len(works)} works after keyword prefilter")

    if client:
        lit_items = literature.score_and_distil(
            works, cfg["interest_profile"], client, model,
            max_items=cfg.get("max_articles", 15),
        )
    else:
        lit_items = works[: cfg.get("max_articles", 15)]

    literature.record_seen(lit_items, seen, cfg.get("seen_cache", "seen.json"))
    print(f"  {len(lit_items)} articles selected")

    # ---------- News ----------
    regions = []
    for r in cfg["regions"]:
        print(f"Fetching news: {r['name']}")
        items = news.fetch_region_news(
            r["query"], r["hl"], r["gl"], r["ceid"],
            max_items=cfg.get("max_news_per_region", 15),
        )
        summary = news.summarize_region(
            r["name"], items, client, model,
            out_language=cfg.get("news_language", "English"),
        )
        regions.append({"name": r["name"], "themes": summary, "items": items})

    # ---------- Email ----------
    html_body = digest.build_html(
        lit_items, regions, base_font_size=cfg.get("base_font_size", 15)
    )
    email = cfg["email"]
    mailer.send_email(
        smtp_host=email["smtp_host"],
        smtp_port=email["smtp_port"],
        username=os.environ["SMTP_USERNAME"],
        password=os.environ["SMTP_PASSWORD"],
        sender=email["from"],
        recipients=email["to"],
        subject=f"{email.get('subject_prefix', '每日研究简报')} · {date.today().isoformat()}",
        html_body=html_body,
    )


if __name__ == "__main__":
    main()
