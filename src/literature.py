"""Fetch recent articles from the watched journals via OpenAlex, shortlist the
ones that bear on the research project with Claude, then pick the top N and
say briefly why each is relevant."""

import json
import re
import time
from datetime import date, timedelta
from pathlib import Path

import requests

from .util import extract_json, model_text

OPENALEX = "https://api.openalex.org"

_SKIP_TITLE = re.compile(
    r"^\s*(correction|corrigendum|erratum|errata|retraction|editorial board|"
    r"front matter|back matter|issue information|cover|index|"
    r"notes on contributors|call for papers|announcement)\b",
    re.I,
)


def _norm(name):
    s = name.lower().replace("&", " and ").strip()
    s = re.sub(r"^the\s+", "", s)
    return re.sub(r"[^a-z0-9]+", "", s)


def resolve_source_ids(journal_names, mailto, cache_path):
    """Map journal names to OpenAlex source IDs. Exact name matches are cached
    on disk; approximate matches are used for this run only and flagged."""
    cache = {}
    p = Path(cache_path)
    if p.exists():
        cache = json.loads(p.read_text(encoding="utf-8"))
    resolved, changed = {}, False
    for name in journal_names:
        if name in cache:
            resolved[name] = cache[name]
            continue
        try:
            r = requests.get(
                f"{OPENALEX}/sources",
                params={"search": name, "per-page": 10, "mailto": mailto},
                timeout=30,
            )
            r.raise_for_status()
            results = [
                s for s in r.json().get("results", [])
                if s.get("type", "journal") == "journal"
            ]
            if not results:
                print(f"  WARNING: could not resolve journal '{name}'")
                continue
            exact = [s for s in results if _norm(s.get("display_name", "")) == _norm(name)]
            if exact:
                best = max(exact, key=lambda s: s.get("works_count", 0))
                sid = best["id"].split("/")[-1]
                cache[name] = sid
                changed = True
                print(f"  resolved '{name}' -> {sid}")
            else:
                best = results[0]
                sid = best["id"].split("/")[-1]
                print(
                    f"  WARNING: no exact match for '{name}'; using "
                    f"'{best.get('display_name')}' ({sid}). Check this is right."
                )
            resolved[name] = sid
        except Exception as e:
            print(f"  WARNING: error resolving '{name}': {e}")
        time.sleep(0.2)
    if changed:
        p.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
    return resolved


def _reconstruct_abstract(inv_index):
    if not inv_index:
        return ""
    positions = []
    for word, idxs in inv_index.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort()
    return " ".join(w for _, w in positions)


def fetch_recent_works(source_ids, days, mailto, per_source=100):
    """Return articles published in the last `days` days as plain dicts."""
    since = (date.today() - timedelta(days=days)).isoformat()
    works, seen_keys = [], set()
    for sid in source_ids:
        params = {
            "filter": (
                f"primary_location.source.id:{sid},"
                f"from_publication_date:{since},type:article"
            ),
            "sort": "publication_date:desc",
            "per-page": per_source,
            "mailto": mailto,
        }
        try:
            r = requests.get(f"{OPENALEX}/works", params=params, timeout=30)
        except Exception as e:
            print(f"  WARNING: fetch failed for source {sid}: {e}")
            continue
        if r.status_code != 200:
            print(f"  WARNING: OpenAlex returned {r.status_code} for {sid}: {r.text[:120]}")
            continue
        for w in r.json().get("results", []):
            title = (w.get("title") or "").strip()
            if not title or _SKIP_TITLE.match(title):
                continue
            doi = w.get("doi")
            key = doi or w.get("id")
            if key in seen_keys:
                continue
            seen_keys.add(key)
            names = [
                a["author"]["display_name"]
                for a in w.get("authorships", [])
                if a.get("author") and a["author"].get("display_name")
            ]
            authors = names[:8] + (["et al."] if len(names) > 8 else [])
            loc = w.get("primary_location") or {}
            works.append(
                {
                    "key": key,
                    "title": title,
                    "abstract": _reconstruct_abstract(w.get("abstract_inverted_index")),
                    "url": doi or loc.get("landing_page_url", ""),
                    "journal": (loc.get("source") or {}).get("display_name", ""),
                    "date": w.get("publication_date", ""),
                    "authors": authors,
                }
            )
        time.sleep(0.2)
    return works


def drop_seen(works, seen_path):
    """Skip papers already emailed on a previous run."""
    seen = set()
    p = Path(seen_path)
    if p.exists():
        seen = set(json.loads(p.read_text(encoding="utf-8")))
    return [w for w in works if w["key"] not in seen], seen


def record_seen(works, seen, seen_path):
    for w in works:
        seen.add(w["key"])
    Path(seen_path).write_text(json.dumps(sorted(seen), ensure_ascii=False), encoding="utf-8")


def keyword_prefilter(works, keywords, cap=120):
    """Cheap first pass: keep works that mention at least one keyword, ranked by
    the number of distinct keyword hits, capped so the model sees a manageable set."""
    if not keywords:
        return works[:cap]
    kws = [k.lower() for k in keywords]
    scored = []
    for w in works:
        text = (w["title"] + " " + w["abstract"]).lower()
        hits = sum(1 for k in kws if k in text)
        if hits:
            scored.append((hits, w))
    scored.sort(key=lambda x: -x[0])
    return [w for _, w in scored[:cap]]


def _abstract_or_na(w, limit):
    return w["abstract"][:limit] if w["abstract"] else "Not available"


def _shortlist(works, profile, client, model, min_score, batch_size=30, shortlist_size=15):
    """Pass 1: score every candidate in batches, keep those at or above min_score."""
    scored = []
    for start in range(0, len(works), batch_size):
        batch = works[start : start + batch_size]
        catalog = "\n\n".join(
            f"[{i}] {w['title']} ({w['journal']})\nAbstract: {_abstract_or_na(w, 900)}"
            for i, w in enumerate(batch)
        )
        prompt = (
            "You are screening new journal articles for a researcher.\n\n"
            f"Researcher profile and project:\n{profile}\n\n"
            "Score each article below from 0 to 5 for how relevant it is to the project "
            "described (5 = directly addresses its core questions or cases; 3 = clearly "
            "useful; 0 to 2 = peripheral or unrelated). When the abstract is not "
            "available, judge on the title alone and be conservative. Give 0 to book "
            "reviews, editorials, corrections and other non-research items.\n\n"
            f"Return ONLY a JSON array of [index, score] pairs for every article scoring "
            f"{min_score} or higher, for example [[0, 4], [7, 3]]. Return [] if none "
            "qualify. No prose, no markdown.\n\n"
            f"Articles:\n{catalog}"
        )
        try:
            msg = client.messages.create(
                model=model, max_tokens=1500, messages=[{"role": "user", "content": prompt}]
            )
            pairs = extract_json(model_text(msg), "[", "]")
        except Exception as e:
            print(f"  WARNING: scoring batch starting at {start} failed: {e}")
            continue
        for pair in pairs:
            try:
                idx, score = int(pair[0]), float(pair[1])
            except Exception:
                continue
            if 0 <= idx < len(batch) and score >= min_score:
                scored.append((score, batch[idx]))
    scored.sort(key=lambda x: -x[0])
    return [w for _, w in scored[:shortlist_size]], {id(w): s for s, w in scored}


def select_top(works, profile, client, model, top_n=7, min_score=3):
    """Return up to top_n articles, each with a 'why_relevant' sentence or two.
    Without a model client, fall back to keyword-ranked order with no reasons."""
    if not works:
        return []
    if client is None:
        return [dict(w, why_relevant="") for w in works[:top_n]]

    shortlist, _ = _shortlist(works, profile, client, model, min_score)
    print(f"  {len(shortlist)} shortlisted at score >= {min_score}")
    if not shortlist:
        return []

    catalog = "\n\n".join(
        f"[{i}] {w['title']} ({w['journal']}, {w['date']})\nAbstract: {_abstract_or_na(w, 1200)}"
        for i, w in enumerate(shortlist)
    )
    prompt = (
        "You are choosing the most relevant new journal articles for a researcher.\n\n"
        f"Researcher profile and project:\n{profile}\n\n"
        f"From the shortlisted articles below, choose at most {top_n} that are most "
        "relevant to the project, ordered from most to least relevant. For each, write "
        '"why_relevant": one or two sentences in British English saying specifically how '
        "the article bears on the project (its cases, hypotheses, outcomes or methods). "
        "Be concrete and do not overstate; if the link is indirect, say so. Do not use "
        "em dashes.\n\n"
        'Return ONLY a JSON array of objects with keys "index" and "why_relevant". '
        "No prose, no markdown.\n\n"
        f"Articles:\n{catalog}"
    )
    try:
        msg = client.messages.create(
            model=model, max_tokens=2500, messages=[{"role": "user", "content": prompt}]
        )
        picks = extract_json(model_text(msg), "[", "]")
    except Exception as e:
        print(f"  WARNING: final selection failed ({e}); using shortlist order")
        return [dict(w, why_relevant="") for w in shortlist[:top_n]]

    result, used = [], set()
    for p in picks:
        try:
            idx = int(p.get("index"))
        except Exception:
            continue
        if 0 <= idx < len(shortlist) and idx not in used:
            used.add(idx)
            result.append(dict(shortlist[idx], why_relevant=p.get("why_relevant", "").strip()))
    return result[:top_n]
