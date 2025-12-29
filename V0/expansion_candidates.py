import json
from collections import defaultdict
from typing import Dict, Set, List


# -----------------------------
# Utils
# -----------------------------
def norm(username: str) -> str:
    """
    Normalize Twitter/X username:
    - lowercase
    - remove leading '@'
    - strip spaces
    """
    if username is None:
        return ""
    return username.lower().lstrip("@").strip()


def load_jsonl(path: str) -> List[dict]:
    items = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
    return items


def load_seed_usernames(seed_path: str) -> Set[str]:
    """
    Load seed_100.json and return a set of normalized seed usernames
    """
    with open(seed_path, "r", encoding="utf-8") as f:
        seeds = json.load(f)

    seed_set = set()
    for s in seeds:
        u = s.get("username")
        if u:
            seed_set.add(norm(u))
    return seed_set


# -----------------------------
# Main computation
# -----------------------------
def compute_expansion_candidates(
    edges_following_path: str,
    edges_mentions_path: str,
    edges_interactions_path: str,
    seed_100_path: str,
    output_path: str = "expansion_candidates.jsonl",
) -> None:
    # Load seeds
    seed_set = load_seed_usernames(seed_100_path)

    # Initialize maps: target -> set(seed)
    followed_by: Dict[str, Set[str]] = defaultdict(set)
    mentioned_by: Dict[str, Set[str]] = defaultdict(set)
    interacted_by: Dict[str, Set[str]] = defaultdict(set)

    # -------------------------
    # Scan following edges
    # -------------------------
    following_edges = load_jsonl(edges_following_path)
    for e in following_edges:
        seed = norm(e.get("seed_username"))
        target = norm(e.get("target_username"))

        if not seed or not target:
            continue
        if seed not in seed_set:
            continue

        followed_by[target].add(seed)

    # -------------------------
    # Scan mention edges
    # -------------------------
    mention_edges = load_jsonl(edges_mentions_path)
    for e in mention_edges:
        seed = norm(e.get("seed_username"))
        target = norm(e.get("target_username"))

        if not seed or not target:
            continue
        if seed not in seed_set:
            continue

        mentioned_by[target].add(seed)

    # -------------------------
    # Scan interaction edges
    # -------------------------
    interaction_edges = load_jsonl(edges_interactions_path)
    for e in interaction_edges:
        seed = norm(e.get("seed_username"))
        target = norm(e.get("target_username"))  # MUST be author_username

        if not seed or not target:
            continue
        if seed not in seed_set:
            continue

        interacted_by[target].add(seed)

    # -------------------------
    # Build candidate universe
    # -------------------------
    all_targets = set(followed_by) | set(mentioned_by) | set(interacted_by)

    # Remove seeds themselves
    candidates = [c for c in all_targets if c not in seed_set]

    # -------------------------
    # Apply qualification rule
    # -------------------------
    with open(output_path, "w", encoding="utf-8") as fout:
        for c in sorted(candidates):
            f_cnt = len(followed_by.get(c, set()))
            m_cnt = len(mentioned_by.get(c, set()))
            i_cnt = len(interacted_by.get(c, set()))

            # Qualification rule
            if not (f_cnt >= 2 or m_cnt >= 2 or i_cnt >= 2):
                continue

            record = {
                "username": c,
                "cnt_followed_by_seeds": f_cnt,
                "cnt_mentioned_by_seeds": m_cnt,
                "cnt_interacted_by_seeds": i_cnt,
                "evidence": {
                    "seed_usernames_followed": sorted(followed_by.get(c, set())),
                    "seed_usernames_mentioned": sorted(mentioned_by.get(c, set())),
                    "seed_usernames_interacted": sorted(interacted_by.get(c, set())),
                },
            }

            fout.write(json.dumps(record, ensure_ascii=False) + "\n")


# -----------------------------
# CLI entry
# -----------------------------
if __name__ == "__main__":
    compute_expansion_candidates(
        edges_following_path="edges_following.jsonl",
        edges_mentions_path="edges_mentions.jsonl",
        edges_interactions_path="edges_interactions.jsonl",
        seed_100_path="seed_100.json",
        output_path="expansion_candidates.jsonl",
    )
