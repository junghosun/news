"""Small helpers shared by the literature and news modules."""

import json


def extract_json(text, open_char, close_char):
    """Pull the first JSON array/object out of a model reply, tolerating
    stray prose or markdown fences around it."""
    start = text.find(open_char)
    end = text.rfind(close_char)
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON found in model reply")
    return json.loads(text[start : end + 1])


def model_text(msg):
    return "".join(
        b.text for b in msg.content if getattr(b, "type", None) == "text"
    ).strip()
