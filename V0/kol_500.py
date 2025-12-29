import json
from datetime import datetime, timezone
from typing import Dict, List, Optional
import os


# -----------------------------
# Utils
# -----------------------------
def load_jsonl(path: str) -> List[dict]:
    items = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
    return items


def norm(username: str) -> str:
    if username is None:
        return ""
    return username.lower().lstrip("@").strip()


# -----------------------------
# Main logic
# -----------------------------
def build_initial_kol_500(
    expansion_candidates_path: str,
    profiles_expansion_path: Optional[str],
    seed_100_path: str,
    expansion_output_path: str = "expansion_candidates.jsonl",
    output_path: str = "initial_kol_500.json",
):
    """
    3.4 排序补齐（若超过 400）
    3.5 输出文件
    """
    # Load inputs
    expansion_candidates = load_jsonl(expansion_candidates_path)

    # Load profiles if available
    profiles: Dict[str, dict] = {}
    if profiles_expansion_path and os.path.exists(profiles_expansion_path):
        with open(profiles_expansion_path, "r", encoding="utf-8") as f:
            profiles_expansion: Dict[str, dict] = json.load(f)
            # Normalize profile keys
            profiles = {norm(k): v for k, v in profiles_expansion.items()}

    with open(seed_100_path, "r", encoding="utf-8") as f:
        seeds = json.load(f)

    # -------------------------
    # Calculate ExpandScore for all candidates
    # -------------------------
    expanded_with_score = []

    for c in expansion_candidates:
        username = norm(c["username"])

        # Get user_id from profiles if available
        profile = profiles.get(username, {})
        user_id = profile.get("user_id") if profile else None

        cnt_f = c.get("cnt_followed_by_seeds", 0)
        cnt_m = c.get("cnt_mentioned_by_seeds", 0)
        cnt_i = c.get("cnt_interacted_by_seeds", 0)

        # ExpandScore = 2 * cnt_interacted_by_seeds + 1 * cnt_mentioned_by_seeds + 1 * cnt_followed_by_seeds
        expandscore = 2 * cnt_i + 1 * cnt_m + 1 * cnt_f

        record = {
            "username": username,
            "user_id": user_id,
            "cnt_followed_by_seeds": cnt_f,
            "cnt_mentioned_by_seeds": cnt_m,
            "cnt_interacted_by_seeds": cnt_i,
            "expandscore": float(expandscore),
            "evidence": c.get("evidence", {}),
        }

        expanded_with_score.append(record)

    # -------------------------
    # Sort & take Top 400 (if > 400)
    # -------------------------
    if len(expanded_with_score) > 400:
        expanded_with_score.sort(key=lambda x: x["expandscore"], reverse=True)
        top_400_expanded = expanded_with_score[:400]
    else:
        # If <= 400, use all candidates
        top_400_expanded = expanded_with_score

    # -------------------------
    # Output 1: expansion_candidates.jsonl (with expandscore)
    # -------------------------
    with open(expansion_output_path, "w", encoding="utf-8") as f:
        for record in expanded_with_score:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # -------------------------
    # Output 2: initial_kol_500.json
    # -------------------------
    all_kol = seeds + top_400_expanded

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seeds": seeds,
        "expanded": top_400_expanded,
        "all": all_kol,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


# -----------------------------
# CLI entry
# -----------------------------
if __name__ == "__main__":
    build_initial_kol_500(
        expansion_candidates_path="expansion_candidates.jsonl",
        profiles_expansion_path="profiles_expansion.json",  # Optional, can be None if not available
        seed_100_path="seed_100.json",
        expansion_output_path="expansion_candidates.jsonl",
        output_path="initial_kol_500.json",
    )
