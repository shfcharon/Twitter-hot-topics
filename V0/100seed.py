"""
Step 2: Select Top 100 seed accounts from candidate_pool.json / candidate_pool.jsonl

Requirements (DO NOT CHANGE):
- Filter out accounts if:
  1) followers_count < 200
  2) bio contains any of (case-insensitive):
     giveaway, promo, coupon, discount, free, airdrops, follow back, DM for promo, OnlyFans
- SeedScore:
  SeedScore = 3 * list_appearances + log1p(followers_count) + verified_bonus
  where verified_bonus = 1 if verified is true else 0
- Select Top 100 by SeedScore descending
- Output: seed_100.json with exactly 100 records
- seedscore field MUST exist
- Input file: candidate_pool.json OR candidate_pool.jsonl
"""

import json
import math
import re
from typing import Any, Dict, List


# -----------------------------
# 2.1 Basic filtering rules
# -----------------------------
BAD_BIO_PHRASES = [
    "giveaway",
    "promo",
    "coupon",
    "discount",
    "free",
    "airdrops",
    "follow back",
    "dm for promo",
    "onlyfans",
]

_BAD_BIO_RE = re.compile("|".join(re.escape(p) for p in BAD_BIO_PHRASES), flags=re.IGNORECASE)


def _load_candidates(path: str) -> List[Dict[str, Any]]:
    """
    Load candidates from either:
    - candidate_pool.json   (a JSON array OR a JSON object/dict)
    - candidate_pool.jsonl  (one JSON object per line)
    """
    with open(path, "r", encoding="utf-8") as f:
        first = f.read(1)
        f.seek(0)
        if first == "[":
            # JSON array format
            data = json.load(f)
            if not isinstance(data, list):
                raise ValueError("candidate_pool.json must be a JSON array.")
            return data
        elif first == "{":
            # Could be JSON object (dict) or JSONL
            # Try to load as JSON first
            try:
                data = json.load(f)
                if isinstance(data, dict):
                    # If it's a dict, extract values (account info)
                    return list(data.values())
                elif isinstance(data, list):
                    return data
                else:
                    raise ValueError(f"Unexpected JSON type: {type(data)}")
            except json.JSONDecodeError:
                # If JSON parsing fails, try JSONL
                f.seek(0)
                items: List[Dict[str, Any]] = []
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    items.append(json.loads(line))
                return items
        else:
            # JSONL format (one JSON object per line)
            items: List[Dict[str, Any]] = []
            for line in f:
                line = line.strip()
                if not line:
                    continue
                items.append(json.loads(line))
            return items


def _is_noisy(candidate: Dict[str, Any]) -> bool:
    followers = candidate.get("followers_count", 0)
    if followers is None:
        followers = 0

    if followers < 200:
        return True

    bio = candidate.get("bio", "")
    if bio is None:
        bio = ""

    if _BAD_BIO_RE.search(str(bio)):
        return True

    return False


# -----------------------------
# 2.2 SeedScore calculation
# -----------------------------
def _seed_score(candidate: Dict[str, Any]) -> float:
    list_appearances = candidate.get("list_appearances", 0)
    if list_appearances is None:
        list_appearances = 0

    followers = candidate.get("followers_count", 0)
    if followers is None:
        followers = 0

    verified = candidate.get("verified", False)
    verified_bonus = 1 if bool(verified) else 0

    return 3 * float(list_appearances) + math.log1p(float(followers)) + float(verified_bonus)


# -----------------------------
# Main
# -----------------------------
def select_seed_100(input_path: str, output_path: str = "seed_100.json") -> None:
    candidates = _load_candidates(input_path)

    kept: List[Dict[str, Any]] = []
    for c in candidates:
        if _is_noisy(c):
            continue
        c_out = dict(c)
        c_out["seedscore"] = float(_seed_score(c))
        kept.append(c_out)

    kept.sort(key=lambda x: x["seedscore"], reverse=True)

    seed_100 = kept[:100]
    if len(seed_100) != 100:
        raise ValueError(f"After filtering, only {len(seed_100)} accounts remain; cannot output exactly 100.")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(seed_100, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    # Change this to your actual candidate file path:
    INPUT = "candidate_pool.json"  # or "candidate_pool.jsonl"
    select_seed_100(INPUT, "seed_100.json")
