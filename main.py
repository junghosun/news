"""Weekly research digest: Academic Publications (top picks for the research
project) followed by regional political news, delivered by email."""

import os
import sys
from datetime import date

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src import literature, news, digest, mailer  # noqa: E402


def get_client(api_key):
    """Return an Anthropic client, or None to run in the no-model fallback."""
    if not api_key:
        print("No ANTHROPIC_API_KEY set -> running without a model (no scoring or summaries).")
        return None
    import anthropic

    return anthropic.Anthropic(api_key=api_key)


def main():
    cfg_path = os.environ.get("CONFIG", "config.yaml")
    with open(cfg_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    client = get_client(os.environ.get("ANTHROPIC_API_KEY", ""))
    model = cfg.get("model", "claude-haiku-4-5-20251001")
    mailto = cfg["contact_email"]
    ignore_seen = os.environ.get("IGNORE_SEEN", "").strip().lower() in ("1", "true", "yes")
    seen_path = cfg.get("seen_cache", "seen.json")

    # ---------- Academic publications ----------
    print("Resolving journals...")
    resolved = literature.resolve_source_ids(
        cfg["journals"], mailto, cfg.get("source_cache", "sources.json")
    )
    print("Fetching recent works...")
    works = literature.fetch_recent_works(
        list(resolved.values()), cfg.get("lookback_days", 10), mailto
    )
    print(f"  {len(works)} works fetched")
    if ignore_seen:
        print("  IGNORE_SEEN set -> including already-sent papers, not recording them")
        seen = set()
    else:
        works, seen = literature.drop_seen(works, seen_path)
        print(f"  {len(works)} not previously sent")

    candidates = literature.keyword_prefilter(
        works, cfg.get("keywords", []), cap=cfg.get("max_candidates", 120)
    )
    print(f"  {len(candidates)} candidates after keyword prefilter")
    lit_items = literature.select_top(
        candidates, cfg["interest_profile"], client, model,
        top_n=cfg.get("max_articles", 7),
        min_score=cfg.get("min_relevance_score", 2),
    )
    print(f"  {len(lit_items)} articles selected")

    # ---------- Regional news ----------
    window = str(cfg.get("news_window", "7d"))
    regions = []
    for r in cfg["regions"]:
        print(f"Fetching news: {r['name']}")
        queries = [r["query"]] + list(r.get("extra_queries", []))
        items = news.fetch_region_news(
            queries, r["hl"], r["gl"], r["ceid"], window=window,
            max_total=cfg.get("news_candidates_per_region", 40),
        )
        print(f"  {len(items)} candidate headlines")
        stories = news.curate_region(
            r["name"], items, client, model, cfg["news_focus"],
            max_stories=cfg.get("max_news_per_region", 5),
            window_desc="week" if window == "7d" else window,
            out_language=cfg.get("news_language", "English"),
        )
        regions.append({"name": r["name"], "stories": stories})

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
        subject=f"{email.get('subject_prefix', 'Weekly Brief')} \u00b7 {date.today().isoformat()}",
        html_body=html_body,
    )

    # Mark papers as sent only after the email went out, and never on a preview run.
    if not ignore_seen:
        literature.record_seen(lit_items, seen, seen_path)
        print(f"  recorded {len(lit_items)} papers as seen")


if __name__ == "__main__":
    main()
