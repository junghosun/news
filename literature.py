"""Fetch recent articles from top political science journals via OpenAlex,
then filter for relevance to the researcher's profile and distil abstracts."""

import json
import time
from datetime import date, timedelta
from pathlib import Path

import requests

OPENALEX = "https://api.openalex.org"


def resolve_source_ids(journal_names, mailto, cache_path):
    """Turn journal display names into OpenAlex source IDs (S...), cached on disk
    so we only hit the API once per journal."""
    cache = {}
    p = Path(cache_path)
    if p.exists():
        cache = json.loads(p.read_text(encoding="utf-8"))
    changed = False
    for name in journal_names:
        if name in cache:
            continue
        try:
            r = requests.get(
                f"{OPENALEX}/sources",
                params={"search": name, "mailto": mailto},
                timeout=30,
            )
            r.raise_for_status()
            results = r.json().get("results", [])
            if results:
                cache[name] = results[0]["id"].split("/")[-1]  # e.g. S12345678
                changed = True
                print(f"  resolved '{name}' -> {cache[name]} ({results[0]['display_name']})")
            else:
                print(f"  WARNING: could not resolve journal '{name}'")
        except Exception as e:
            print(f"  WARNING: error resolving '{name}': {e}")
        time.sleep(0.2)
    if changed:
        p.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
    return cache


def _reconstruct_abstract(inv_index):
    if not inv_index:
        return ""
    positions = []
    for word, idxs in inv_index.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort()
    return " ".join(w for _, w in positions)


def fetch_recent_works(source_ids, days, mailto, per_source=50):
    """Return recent journal articles (last `days` days) as plain dicts."""
    since = (date.today() - timedelta(days=days)).isoformat()
    works = []
    for sid in source_ids:
        params = {
            "filter": (
                f"primary_location.source.id:{sid},"
                f"from_publication_date:{since},"
                f"type:article"
            ),
            "sort": "publication_date:desc",
            "per-page": per_source,
            "mailto": mailto,
        }
        try:
            r = requests.get(f"{OPENALEX}/works", params=params, timeout=30)
            if r.status_code != 200:
                continue
            for w in r.json().get("results", []):
                doi = w.get("doi")
                works.append(
                    {
                        "title": (w.get("title") or "").strip(),
                        "abstract": _reconstruct_abstract(w.get("abstract_inverted_index")),
                        "doi": doi,
                        "url": doi or (w.get("primary_location") or {}).get("landing_page_url", ""),
                        "journal": ((w.get("primary_location") or {}).get("source") or {}).get(
                            "display_name", ""
                        ),
                        "date": w.get("publication_date", ""),
                        "authors": [
                            a["author"]["display_name"]
                            for a in w.get("authorships", [])
                            if a.get("author")
                        ][:6],
                    }
                )
        except Exception as e:
            print(f"  WARNING: fetch failed for source {sid}: {e}")
        time.sleep(0.2)
    return works


def drop_seen(works, seen_path):
    """Skip DOIs already emailed on a previous run."""
    seen = set()
    p = Path(seen_path)
    if p.exists():
        seen = set(json.loads(p.read_text(encoding="utf-8")))
    fresh = [w for w in works if w.get("doi") and w["doi"] not in seen]
    return fresh, seen


def record_seen(works, seen, seen_path):
    for w in works:
        if w.get("doi"):
            seen.add(w["doi"])
    Path(seen_path).write_text(
        json.dumps(sorted(seen), ensure_ascii=False), encoding="utf-8"
    )


def keyword_prefilter(works, keywords):
    """Cheap first pass so we send fewer abstracts to the model."""
    if not keywords:
        return works
    kws = [k.lower() for k in keywords]
    out = []
    for w in works:
        text = (w["title"] + " " + w["abstract"]).lower()
        if any(k in text for k in kws):
            out.append(w)
    return out


def score_and_distil(works, profile, client, model, max_items=15):
    """Ask Claude to pick the genuinely relevant articles and distil each one.
    Returns the works annotated with score / distillation / relevance."""
    if not works:
        return []
    catalog = []
    for i, w in enumerate(works):
        catalog.append(
            f"[{i}] {w['title']} ({w['journal']}, {w['date']})\n"
            f"Abstract: {w['abstract'][:1200]}"
        )
    prompt = (
        "You are screening new political science articles for a researcher.\n\n"
        f"Researcher profile:\n{profile}\n\n"
        "Below are candidate articles. Select ONLY those genuinely relevant to the "
        "profile. For each selected article return: its index, a relevance score 1-5, "
        "a 2-3 sentence distillation of the core question / finding / method, and a "
        "short note on why it fits this researcher.\n\n"
        'Return ONLY valid JSON: a list of objects with keys "index", "score", '
        '"distillation", "relevance". No prose, no markdown.\n\n'
        "Articles:\n" + "\n\n".join(catalog)
    )
    msg = client.messages.create(
        model=model,
        max_tokens=2500,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("[") :] if "[" in text else text
    try:
        picks = json.loads(text)
    except Exception:
        print("  WARNING: could not parse model JSON; returning keyword matches only")
        return works[:max_items]
    result = []
    for p in picks:
        idx = p.get("index")
        if idx is None or idx >= len(works):
            continue
        w = dict(works[idx])
        w.update(
            score=p.get("score"),
            distillation=p.get("distillation", ""),
            relevance=p.get("relevance", ""),
        )
        result.append(w)
    result.sort(key=lambda x: x.get("score") or 0, reverse=True)
    return result[:max_items]
