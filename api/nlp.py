import re
from typing import Optional
from api.utils import lookup_country_id

_MALE_RE = re.compile(r"\b(male|males|man|men|boy|boys|gentleman|gentlemen)\b")
_FEMALE_RE = re.compile(r"\b(female|females|woman|women|girl|girls|lady|ladies)\b")
_AGE_GROUP_PATTERNS = [
    (re.compile(r"\b(child|children|kid|kids)\b"), "child"),
    (re.compile(r"\b(teenager|teenagers|teen|teens|adolescent|adolescents)\b"), "teenager"),
    (re.compile(r"\b(adult|adults)\b"), "adult"),
    (re.compile(r"\b(senior|seniors|elderly)\b"), "senior"),
]
_YOUNG_RE = re.compile(r"\byoung\b")
_MIN_AGE_RE = re.compile(r"\b(?:above|over|older than|at least|more than)\s+(\d+)")
_MAX_AGE_RE = re.compile(r"\b(?:below|under|younger than|less than|at most)\s+(\d+)")
_BETWEEN_RE = re.compile(r"\bbetween\s+(?:ages?\s+)?(\d+)\s+and\s+(\d+)")
_AGE_RANGE_RE = re.compile(r"\b(?:ages?|aged)\s+(\d+)\s*(?:to|and|[-–])\s*(\d+)")
_COUNTRY_RE = re.compile(
    r"\b(?:from|in|living\s+in|based\s+in)\s+([a-z][a-z\s'\-]*?)(?=\s*(?:$|\b(?:above|below|over|under|between|aged?|who|that|with|and)))"
)
# Bare-token country scan: matches single words like "Nigerian", "British"
# even when no "from"/"in" preposition is present. Word characters only;
# the result is validated against COUNTRY_LOOKUP, so non-country tokens
# silently miss.
_TOKEN_RE = re.compile(r"\b([a-z]+(?:\s+[a-z]+)?)\b")


def parse_query(raw: str) -> Optional[dict]:
    q = raw.lower().strip()
    if not q:
        return None

    filters: dict = {}

    # Gender
    has_male = bool(_MALE_RE.search(q))
    has_female = bool(_FEMALE_RE.search(q))
    if has_male and not has_female:
        filters["gender"] = "male"
    elif has_female and not has_male:
        filters["gender"] = "female"

    # Age group (stored groups take precedence over "young")
    for pattern, group in _AGE_GROUP_PATTERNS:
        if pattern.search(q):
            filters["age_group"] = group
            break

    # "young" maps to 16–24 (not a stored age group)
    if _YOUNG_RE.search(q) and "age_group" not in filters:
        filters["min_age"] = 16
        filters["max_age"] = 24

    # Age range modifiers
    m = _BETWEEN_RE.search(q)
    if m:
        filters["min_age"] = int(m.group(1))
        filters["max_age"] = int(m.group(2))
    else:
        m = _AGE_RANGE_RE.search(q)
        if m:
            filters["min_age"] = int(m.group(1))
            filters["max_age"] = int(m.group(2))
        else:
            m = _MIN_AGE_RE.search(q)
            if m:
                filters["min_age"] = int(m.group(1))
            m = _MAX_AGE_RE.search(q)
            if m:
                filters["max_age"] = int(m.group(1))

    # Country — first try a prepositional phrase ("from X", "in X", …),
    # then fall back to bare demonyms ("Nigerian", "British") scanned
    # token-by-token against the lookup table.
    m = _COUNTRY_RE.search(q)
    if m:
        country_id = lookup_country_id(m.group(1).strip())
        if country_id:
            filters["country_id"] = country_id
    if "country_id" not in filters:
        # 2-grams first ("south korean") so "south" doesn't shadow them.
        tokens = re.findall(r"[a-z]+", q)
        for n in (2, 1):
            for i in range(len(tokens) - n + 1):
                phrase = " ".join(tokens[i:i + n])
                cid = lookup_country_id(phrase)
                if cid:
                    filters["country_id"] = cid
                    break
            if "country_id" in filters:
                break

    return filters if filters else None
