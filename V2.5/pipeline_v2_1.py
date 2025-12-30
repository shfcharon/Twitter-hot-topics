"""
Pipeline V2.5 (Local LLM via Ollama, code-governed)

Key principle:
- LLM only outputs structured judgments + confidence + reason.
- Code performs filtering, candidate generation (downsampling), merge execution, scoring, reporting, and logging.

Inputs (default under ./inputs):
- tweets_24h_clean.jsonl
- kol_profiles.jsonl
- (optional) edges_24h.jsonl

Assets (default under ./assets):
- event_definition.md
- event_schema.json
- examples_positive.jsonl
- examples_negative.jsonl

Outputs (default under ./outputs):
- events_structured.jsonl
- events_filtered.jsonl
- event_pairs_candidates.jsonl
- event_pairs_same_event.jsonl
- event_clusters.json
- hot_events_top5.json
- daily_report.json
- daily_report_readable.json

Run (local, no paid API):
  python3 pipeline_v2_1.py --llm_enabled --ollama_model qwen2.5:7b-instruct
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import itertools
import json
import math
import os
import random
import re
import time
import sys
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

# local modules (Ollama)
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from llm.client import OllamaConfig, ollama_generate  # noqa: E402
from llm.retry import RetryConfig, call_llm_json as call_llm_json_local  # noqa: E402

# =============================================================================
# Basic IO
# =============================================================================


def read_jsonl(path: str) -> List[dict]:
    items: List[dict] = []
    if not os.path.exists(path):
        return items
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return items


def write_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def write_jsonl(path: str, rows: Iterable[dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def append_jsonl(path: str, row: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def now_utc_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


# =============================================================================
# Minimal schema / key validation
# =============================================================================


def _is_number(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def validate_exact_keys(obj: Any, expected_keys: Sequence[str]) -> Tuple[bool, str]:
    if not isinstance(obj, dict):
        return False, "not_a_dict"
    got = set(obj.keys())
    exp = set(expected_keys)
    if got != exp:
        missing = sorted(exp - got)
        extra = sorted(got - exp)
        return False, f"keys_mismatch missing={missing} extra={extra}"
    return True, "ok"


def validate_step1(obj: dict) -> Tuple[bool, str]:
    keys = [
        "is_event",
        "relevance_captech",
        "subject",
        "action",
        "object",
        "event_type",
        "topic_tags",
        "evidence_spans",
        "confidence",
        "why",
    ]
    ok, msg = validate_exact_keys(obj, keys)
    if not ok:
        return ok, msg
    if not isinstance(obj["is_event"], bool):
        return False, "is_event_not_bool"
    if not isinstance(obj["relevance_captech"], bool):
        return False, "relevance_captech_not_bool"
    if not isinstance(obj["subject"], list) or not all(isinstance(x, str) for x in obj["subject"]):
        return False, "subject_not_str_array"
    if not (obj["action"] is None or isinstance(obj["action"], str)):
        return False, "action_type_invalid"
    if not isinstance(obj["object"], list) or not all(isinstance(x, str) for x in obj["object"]):
        return False, "object_not_str_array"
    if not (obj["event_type"] is None or isinstance(obj["event_type"], str)):
        return False, "event_type_invalid"
    if not isinstance(obj["topic_tags"], list) or not all(isinstance(x, str) for x in obj["topic_tags"]):
        return False, "topic_tags_invalid"
    if not isinstance(obj["evidence_spans"], list) or not all(isinstance(x, str) for x in obj["evidence_spans"]):
        return False, "evidence_spans_invalid"
    if not _is_number(obj["confidence"]) or not (0 <= float(obj["confidence"]) <= 1):
        return False, "confidence_invalid"
    if not isinstance(obj["why"], str) or not obj["why"].strip():
        return False, "why_invalid"
    return True, "ok"


def validate_step2(obj: dict) -> Tuple[bool, str]:
    keys = ["keep", "reason", "relevance_captech", "quality_score"]
    ok, msg = validate_exact_keys(obj, keys)
    if not ok:
        return ok, msg
    if not isinstance(obj["keep"], bool):
        return False, "keep_not_bool"
    if not isinstance(obj["relevance_captech"], bool):
        return False, "relevance_captech_not_bool"
    if not isinstance(obj["reason"], str) or not obj["reason"].strip():
        return False, "reason_invalid"
    if not _is_number(obj["quality_score"]) or not (0 <= float(obj["quality_score"]) <= 1):
        return False, "quality_score_invalid"
    return True, "ok"


def validate_step5(obj: dict) -> Tuple[bool, str]:
    keys = [
        "same_event",
        "confidence",
        "merge_reason",
        "canonical_subject",
        "canonical_action",
        "canonical_object",
    ]
    ok, msg = validate_exact_keys(obj, keys)
    if not ok:
        return ok, msg
    if not isinstance(obj["same_event"], bool):
        return False, "same_event_not_bool"
    if not _is_number(obj["confidence"]) or not (0 <= float(obj["confidence"]) <= 1):
        return False, "confidence_invalid"
    if not isinstance(obj["merge_reason"], str) or not obj["merge_reason"].strip():
        return False, "merge_reason_invalid"
    if not (obj["canonical_subject"] is None or (isinstance(obj["canonical_subject"], list) and all(isinstance(x, str) for x in obj["canonical_subject"]))):
        return False, "canonical_subject_invalid"
    if not (obj["canonical_action"] is None or isinstance(obj["canonical_action"], str)):
        return False, "canonical_action_invalid"
    if not (obj["canonical_object"] is None or (isinstance(obj["canonical_object"], list) and all(isinstance(x, str) for x in obj["canonical_object"]))):
        return False, "canonical_object_invalid"
    return True, "ok"


def validate_step8(obj: dict) -> Tuple[bool, str]:
    keys = ["title_cn", "summary_bullets_cn", "why_hot_cn"]
    ok, msg = validate_exact_keys(obj, keys)
    if not ok:
        return ok, msg
    if not isinstance(obj["title_cn"], str) or not obj["title_cn"].strip():
        return False, "title_cn_invalid"
    if not isinstance(obj["why_hot_cn"], str) or not obj["why_hot_cn"].strip():
        return False, "why_hot_cn_invalid"
    if not isinstance(obj["summary_bullets_cn"], list) or len(obj["summary_bullets_cn"]) != 3 or not all(isinstance(x, str) and x.strip() for x in obj["summary_bullets_cn"]):
        return False, "summary_bullets_cn_invalid"
    return True, "ok"


# =============================================================================
# Prompts (Step 0 global system prompt + step templates)
# =============================================================================


def read_prompt(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


ACTION_TAXONOMY = [
    "launch_release",
    "announce",
    "open_source",
    "funding_investment",
    "acquisition_merger",
    "partnership",
    "regulation_legal",
    "outage_incident",
    "benchmark_result",
    "product_update",
    "recognition_ranking",
    "hiring_org_change",
    "research_breakthrough",
    "other_event",
]

TOPIC_TAGS = [
    "AI_Model",
    "AI_Agent",
    "GPU_Infra",
    "Cloud_Data",
    "Robotics",
    "Startup_VC",
    "BigTech",
    "Regulation",
    "Security_Incident",
    "Science_Biotech",
    "Consumer_Tech",
    "Other",
]


def build_prompt_step1(author: str, created_at: str, text: str) -> str:
    return f"""Task:
Given ONE tweet, decide if it describes a real-world event (as defined). If yes, extract a structured event.

Action taxonomy (choose ONE best action):
{chr(10).join([f"- {a}" for a in ACTION_TAXONOMY])}

Topic tags (choose 0-3):
{chr(10).join([f"- {t}" for t in TOPIC_TAGS])}

Input tweet:
AUTHOR: {author}
TIME: {created_at}
TEXT: {text}

Return JSON with EXACT keys:
{{
  "is_event": <true/false>,
  "relevance_captech": <true/false>,
  "subject": <array of strings>,
  "action": <string or null>,
  "object": <array of strings>,
  "event_type": <string or null>,
  "topic_tags": <array of strings>,
  "evidence_spans": <array of short quotes from the tweet>,
  "confidence": <number between 0 and 1>,
  "why": <one sentence>
}}

Rules:
- If the tweet is only marketing/promo/training with no concrete change, set is_event=false.
- Generic buzzwords (AI/AGI/Autonomous/scale) alone are NOT valid subject/object.
- Prefer concrete entities (company/product/person/org names).
- If relevance_captech is false, is_event can still be true (e.g., medical imaging), but it will be filtered later.
- No extra keys. JSON only.
"""


def build_prompt_step2(text: str, event_json: dict) -> str:
    return f"""Task:
You will receive a structured event extracted from a tweet. Decide:
1) Is it specific enough to be a valid event record?
2) Is it relevant to capital+technology frontier hotspot monitoring?

Return JSON only with keys:
{{
  "keep": <true/false>,
  "reason": <short>,
  "relevance_captech": <true/false>,
  "quality_score": <0 to 1>
}}

Input:
TWEET_TEXT: {text}
EVENT_JSON: {json.dumps(event_json, ensure_ascii=False)}

Guidelines:
- Keep=false if subject/action/object is missing or too generic.
- Keep=false if it's mainly marketing/training promo without a concrete event.
- relevance_captech=true if it relates to AI/infra/cloud/gpu/robotics/startups/VC/bigtech/regulation/security incidents affecting tech/capital.
- A scientific/medical event with no capital/tech frontier implication => relevance_captech=false.
"""


def build_prompt_step5(text_a: str, event_a: dict, text_b: str, event_b: dict) -> str:
    return f"""Task:
Decide whether two event records refer to the SAME real-world event.
This is NOT about semantic similarity; it is about real-world identity.

Return JSON only:
{{
  "same_event": <true/false>,
  "confidence": <0 to 1>,
  "merge_reason": <short>,
  "canonical_subject": <array or null>,
  "canonical_action": <string or null>,
  "canonical_object": <array or null>
}}

Event A:
TWEET_A: {text_a}
EVENT_A: {json.dumps(event_a, ensure_ascii=False)}

Event B:
TWEET_B: {text_b}
EVENT_B: {json.dumps(event_b, ensure_ascii=False)}

Rules:
- same_event=true only if they clearly refer to the same occurrence (e.g., same product release, same funding round, same ranking/award, same outage incident).
- If they share only generic terms (AI/AGI/Autonomous/scale) => NOT same event.
- If subject matches but object differs significantly => NOT same event.
- If unsure, set same_event=false with lower confidence.
- Provide canonical_* fields for merged representation when same_event=true.
"""


def build_prompt_step8(
    canonical_subject: List[str],
    canonical_action: Optional[str],
    canonical_object: List[str],
    top_tweets: List[str],
    score_breakdown: dict,
) -> str:
    return f"""Task:
Given an event cluster (multiple tweets about the same real-world event), write:
1) A clear Chinese title that a manager can understand in 5 seconds
2) 3 bullet summary points (Chinese)
3) A short "why hot" explanation (Chinese)

Return JSON only:
{{
  "title_cn": <string>,
  "summary_bullets_cn": <array of 3 strings>,
  "why_hot_cn": <string>
}}

Input:
CANONICAL_SUBJECT: {json.dumps(canonical_subject, ensure_ascii=False)}
CANONICAL_ACTION: {json.dumps(canonical_action, ensure_ascii=False)}
CANONICAL_OBJECT: {json.dumps(canonical_object, ensure_ascii=False)}
TOP_TWEETS: {json.dumps(top_tweets, ensure_ascii=False)}
SCORE_BREAKDOWN: {json.dumps(score_breakdown, ensure_ascii=False)}

Rules:
- Title must include concrete subject + concrete object + event nature (e.g., 发布/融资/被认可/事故).
- Avoid generic buzzwords alone (AI/AGI/Autonomous) as title core.
- Do NOT hallucinate details not in tweets.
- Keep title <= 28 Chinese characters if possible.
"""


# =============================================================================
# Rules / heuristics (Step 2.1 hard rules; Step 4 blocking)
# =============================================================================


URL_RE = re.compile(r"https?://\\S+")
WORD_RE = re.compile(r"[A-Za-z0-9_\\-]{2,}")

PROMO_PATTERNS = [
    re.compile(r"\\bwebinar\\b", re.I),
    re.compile(r"\\bregister\\b", re.I),
    re.compile(r"\\bsubscribe\\b", re.I),
    re.compile(r"\\bjoin\\s+us\\b", re.I),
    re.compile(r"\\blimited\\s+seats\\b", re.I),
    re.compile(r"\\bsign\\s+up\\b", re.I),
    re.compile(r"\\bcourse\\b", re.I),
    re.compile(r"\\bworkshop\\b", re.I),
]

PLATFORM_DOMAINS = {"x.com", "twitter.com", "t.co", "youtube.com", "youtu.be", "tiktok.com", "instagram.com"}


def strip_urls(text: str) -> str:
    return URL_RE.sub(" ", text or "").strip()


def extract_domains(text: str) -> Set[str]:
    domains = set()
    for m in re.findall(r"https?://([^/\\s]+)", text or ""):
        dom = m.lower()
        if dom.startswith("www."):
            dom = dom[4:]
        domains.add(dom)
    return domains


def is_rule_drop(text: str, min_len: int) -> Tuple[bool, str]:
    t = (text or "").strip()
    if not t:
        return True, "empty_text"
    without_urls = strip_urls(t)
    if not without_urls:
        return True, "url_only"
    if len(without_urls) < min_len:
        return True, "too_short"
    for pat in PROMO_PATTERNS:
        if pat.search(t):
            return True, "promo_template"
    doms = extract_domains(t)
    if doms and doms.issubset(PLATFORM_DOMAINS) and len(without_urls) < (min_len + 10):
        return True, "platform_link_low_content"
    return False, "ok"


def norm_username(u: str) -> str:
    return (u or "").lower().lstrip("@").strip()


def safe_get_text(tweet: dict) -> str:
    return (tweet.get("clean_text") or tweet.get("text") or "").strip()


def tokenize_for_overlap(items: Sequence[str]) -> Set[str]:
    toks: Set[str] = set()
    for s in items:
        for w in WORD_RE.findall((s or "").lower()):
            if len(w) >= 3:
                toks.add(w)
    return toks


def pick_block_tokens(subject: Sequence[str], obj: Sequence[str], max_tokens: int = 4) -> List[str]:
    toks = list(tokenize_for_overlap(list(subject) + list(obj)))
    toks.sort(key=lambda x: (-len(x), x))
    return toks[:max_tokens]


# =============================================================================
# Data model (EventCard + Cluster)
# =============================================================================


@dataclasses.dataclass
class EventCard:
    event_id: str
    source_tweet_id: str
    tweet_text: str
    author: str
    created_at: str
    created_ts: int
    subject: List[str]
    action: Optional[str]
    object: List[str]
    event_type: Optional[str]
    topic_tags: List[str]
    evidence_spans: List[str]
    llm_confidence: float
    llm_why: str
    relevance_captech: bool
    # computed / enrichment
    engagement: Dict[str, int]
    engagement_score: float
    author_weight: float
    followers_count: int
    verified: Optional[bool]
    domain: Optional[str]
    kol_tier: Optional[str]
    anchor_target: Optional[str]

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class Cluster:
    cluster_id: str
    member_event_ids: List[str]
    canonical_subject: List[str]
    canonical_action: Optional[str]
    canonical_object: List[str]
    topic_tags: List[str]
    evidence_spans: List[str]
    authors: List[str]
    representative_event_id: str
    # aggregated metrics
    tweet_count: int
    author_count: int
    engagement: Dict[str, int]
    engagement_score: float
    kol_weight_sum: float
    propagation_count: int
    score: float
    score_breakdown: dict
    # Step 8 outputs (optional)
    title_cn: Optional[str] = None
    summary_bullets_cn: Optional[List[str]] = None
    why_hot_cn: Optional[str] = None

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


# =============================================================================
# KOL profiles
# =============================================================================


def load_kol_profiles(path: str) -> Dict[str, dict]:
    profiles = {}
    for r in read_jsonl(path):
        u = norm_username(r.get("username", ""))
        if not u:
            continue
        profiles[u] = r
    return profiles


def eventcard_from_row(rr: dict) -> Optional[EventCard]:
    """
    Robust loader for EventCard from a dict row (e.g., from events_filtered.jsonl).
    Returns None if critical fields are missing.
    """
    field_names = {f.name for f in dataclasses.fields(EventCard)}
    data = {k: rr.get(k) for k in field_names}
    if not data.get("event_id"):
        return None
    # Fill minimal defaults for older / partial rows
    data["source_tweet_id"] = data.get("source_tweet_id") or data["event_id"]
    data["tweet_text"] = data.get("tweet_text") or ""
    data["author"] = data.get("author") or ""
    data["created_at"] = data.get("created_at") or ""
    data["created_ts"] = int(data.get("created_ts") or 0)
    data["subject"] = list(data.get("subject") or [])
    data["object"] = list(data.get("object") or [])
    data["topic_tags"] = list(data.get("topic_tags") or [])
    data["evidence_spans"] = list(data.get("evidence_spans") or [])
    data["llm_confidence"] = float(data.get("llm_confidence") or 0.0)
    data["llm_why"] = str(data.get("llm_why") or "")
    data["relevance_captech"] = bool(data.get("relevance_captech") or False)
    data["engagement"] = dict(data.get("engagement") or {"like": 0, "reply": 0, "repost": 0, "quote": 0})
    data["engagement_score"] = float(data.get("engagement_score") or engagement_score(data["engagement"]))
    data["author_weight"] = float(data.get("author_weight") or 1.0)
    data["followers_count"] = int(data.get("followers_count") or 0)
    # verified/domain/kol_tier/anchor_target may be None
    return EventCard(**data)  # type: ignore[arg-type]


def kol_weight_for(username: str, profiles: Dict[str, dict]) -> Tuple[float, int, Optional[bool], Optional[str], Optional[str]]:
    u = norm_username(username)
    p = profiles.get(u)
    if not p:
        return 1.0, 0, None, None, None
    return (
        float(p.get("kol_weight") or 1.0),
        int(p.get("followers_count") or 0),
        p.get("verified", None),
        p.get("domain", None),
        p.get("kol_tier", None),
    )


# =============================================================================
# Step 1-3: per-tweet extraction + gate + normalization
# =============================================================================


def compute_engagement(metrics: dict) -> Dict[str, int]:
    like = int((metrics or {}).get("like_count", 0) or 0)
    reply = int((metrics or {}).get("reply_count", 0) or 0)
    repost = int((metrics or {}).get("repost_count", 0) or 0)
    quote = int((metrics or {}).get("quote_count", 0) or 0)
    return {"like": like, "reply": reply, "repost": repost, "quote": quote}


def engagement_score(e: Dict[str, int]) -> float:
    return float(e["like"] + 2 * e["repost"] + 0.5 * e["reply"] + 1.5 * e["quote"])


def parse_created_ts(created_at: str) -> int:
    # tweets in this repo are ISO-8601; handle trailing Z.
    if not created_at:
        return 0
    s = created_at.strip()
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return int(dt.datetime.fromisoformat(s).timestamp())
    except Exception:
        return 0


def extract_anchor_target(tweet: dict) -> Optional[str]:
    refs = tweet.get("referenced_tweets", [])
    if isinstance(refs, list):
        for r in refs:
            if isinstance(r, dict) and r.get("id"):
                return str(r["id"])
    return None


def normalize_event_card(
    tweet: dict,
    step1: dict,
    profiles: Dict[str, dict],
) -> EventCard:
    tweet_id = str(tweet.get("tweet_id", "") or "")
    author = norm_username(tweet.get("author_username", "") or tweet.get("author", ""))
    text = safe_get_text(tweet)
    created_at = tweet.get("created_at", "") or tweet.get("created_at_local", "") or ""
    created_ts = int(tweet.get("created_ts", 0) or 0) or parse_created_ts(created_at)
    eng = compute_engagement(tweet.get("public_metrics", {}))
    eng_score = engagement_score(eng)
    w, followers, verified, domain, tier = kol_weight_for(author, profiles)
    anchor = extract_anchor_target(tweet)

    return EventCard(
        event_id=tweet_id,
        source_tweet_id=tweet_id,
        tweet_text=text,
        author=author,
        created_at=created_at,
        created_ts=created_ts,
        subject=[s for s in (step1.get("subject") or []) if isinstance(s, str) and s.strip()],
        action=step1.get("action", None),
        object=[s for s in (step1.get("object") or []) if isinstance(s, str) and s.strip()],
        event_type=step1.get("event_type", None),
        topic_tags=[t for t in (step1.get("topic_tags") or []) if isinstance(t, str) and t.strip()],
        evidence_spans=[s for s in (step1.get("evidence_spans") or []) if isinstance(s, str) and s.strip()],
        llm_confidence=float(step1.get("confidence", 0.0) or 0.0),
        llm_why=str(step1.get("why", "") or ""),
        relevance_captech=bool(step1.get("relevance_captech", False)),
        engagement=eng,
        engagement_score=eng_score,
        author_weight=float(w),
        followers_count=int(followers),
        verified=verified,
        domain=domain,
        kol_tier=tier,
        anchor_target=anchor,
    )


# =============================================================================
# Step 4-6: candidate pair generation, same-event judge, clustering/merge
# =============================================================================


def generate_candidate_pairs(
    events: List[EventCard],
    *,
    max_bucket_size: int,
    max_pairs_total: int,
    rng_seed: int = 42,
) -> List[Tuple[str, str, dict]]:
    """
    Downsample O(n^2) -> candidate pairs via blocking keys:
    - anchor_target
    - topic tags
    - subject/object tokens (weak overlap)

    Returns list of (a_id, b_id, reason_dict).
    """
    rnd = random.Random(rng_seed)
    by_id = {e.event_id: e for e in events}

    buckets: Dict[str, List[str]] = defaultdict(list)

    for e in events:
        if e.anchor_target:
            buckets[f"anchor:{e.anchor_target}"].append(e.event_id)
        for t in e.topic_tags:
            buckets[f"tag:{t}"].append(e.event_id)
        for tok in pick_block_tokens(e.subject, e.object, max_tokens=4):
            buckets[f"tok:{tok}"].append(e.event_id)

    # prune huge buckets (keep top by engagement)
    for k, ids in list(buckets.items()):
        if len(ids) > max_bucket_size:
            ids_sorted = sorted(ids, key=lambda eid: by_id[eid].engagement_score, reverse=True)
            buckets[k] = ids_sorted[:max_bucket_size]

    pair_set: Set[Tuple[str, str]] = set()
    pairs: List[Tuple[str, str, dict]] = []

    def add_pair(a: str, b: str, why: str) -> None:
        x, y = (a, b) if a < b else (b, a)
        if x == y:
            return
        if (x, y) in pair_set:
            return
        pair_set.add((x, y))
        pairs.append((x, y, {"by": why}))

    for key, ids in buckets.items():
        if len(ids) < 2:
            continue
        # If bucket still large, sample pairs to avoid explosion.
        if len(ids) > 60:
            # sample limited pairings
            sample_n = min(60, len(ids))
            sample_ids = ids[:sample_n]
            for a, b in rnd.sample(list(itertools.combinations(sample_ids, 2)), k=min(200, sample_n * 3)):
                add_pair(a, b, key)
        else:
            for a, b in itertools.combinations(ids, 2):
                add_pair(a, b, key)

        if len(pairs) >= max_pairs_total:
            break

    # final sanity: keep pairs where there is at least one strong match:
    filtered: List[Tuple[str, str, dict]] = []
    for a, b, reason in pairs:
        ea, eb = by_id[a], by_id[b]
        # time constraint (<= 48h) to avoid obvious non-identity pairs
        if ea.created_ts and eb.created_ts:
            if abs(int(ea.created_ts) - int(eb.created_ts)) > 48 * 3600:
                continue
        conds = 0
        if ea.anchor_target and ea.anchor_target == eb.anchor_target:
            conds += 2
        if set(ea.topic_tags) & set(eb.topic_tags):
            conds += 1
        if tokenize_for_overlap(ea.subject) & tokenize_for_overlap(eb.subject):
            conds += 1
        if tokenize_for_overlap(ea.object) & tokenize_for_overlap(eb.object):
            conds += 1
        if conds >= 1:
            filtered.append((a, b, {"bucket": reason["by"], "conds": conds}))

    return filtered[:max_pairs_total]


class UnionFind:
    def __init__(self):
        self.parent: Dict[str, str] = {}
        self.rank: Dict[str, int] = {}

    def find(self, x: str) -> str:
        if x not in self.parent:
            self.parent[x] = x
            self.rank[x] = 0
            return x
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            self.parent[ra] = rb
        elif self.rank[ra] > self.rank[rb]:
            self.parent[rb] = ra
        else:
            self.parent[rb] = ra
            self.rank[ra] += 1


def build_clusters(
    events: List[EventCard],
    same_event_edges: List[dict],
    *,
    edges_24h: Optional[List[dict]] = None,
) -> List[Cluster]:
    by_id = {e.event_id: e for e in events}
    uf = UnionFind()
    for e in events:
        uf.find(e.event_id)

    # union edges
    for ed in same_event_edges:
        a = ed["a_event_id"]
        b = ed["b_event_id"]
        uf.union(a, b)

    comps: Dict[str, List[str]] = defaultdict(list)
    for eid in by_id.keys():
        comps[uf.find(eid)].append(eid)

    # build propagation counts from edges_24h if provided
    propagation_map: Dict[str, int] = defaultdict(int)
    if edges_24h:
        targets = defaultdict(list)
        for e in edges_24h:
            tgt = str(e.get("target_tweet_id", "") or "")
            if not tgt:
                continue
            targets[tgt].append(e)
        for eid in by_id.keys():
            propagation_map[eid] = len(targets.get(eid, []))

    clusters: List[Cluster] = []
    idx = 0
    for root, member_ids in comps.items():
        member_events = [by_id[x] for x in member_ids]
        # canonical by frequency
        subj_counter = Counter()
        obj_counter = Counter()
        act_counter = Counter()
        tag_counter = Counter()
        ev_spans: List[str] = []
        authors_set: Set[str] = set()

        for ev in member_events:
            for s in ev.subject:
                subj_counter[s.strip()] += 1
            for o in ev.object:
                obj_counter[o.strip()] += 1
            if ev.action:
                act_counter[ev.action] += 1
            for t in ev.topic_tags:
                tag_counter[t] += 1
            for sp in ev.evidence_spans:
                if sp and sp not in ev_spans:
                    ev_spans.append(sp)
            if ev.author:
                authors_set.add(ev.author)

        # incorporate LLM-proposed canonical fields from Step5 edges within the component
        member_set = set(member_ids)
        for ed in same_event_edges:
            a = ed.get("a_event_id")
            b = ed.get("b_event_id")
            if not a or not b or a not in member_set or b not in member_set:
                continue
            cs = ed.get("canonical_subject")
            ca = ed.get("canonical_action")
            co = ed.get("canonical_object")
            if isinstance(cs, list):
                for s in cs:
                    if isinstance(s, str) and s.strip():
                        subj_counter[s.strip()] += 2
            if isinstance(ca, str) and ca.strip():
                act_counter[ca.strip()] += 2
            if isinstance(co, list):
                for o in co:
                    if isinstance(o, str) and o.strip():
                        obj_counter[o.strip()] += 2

        canonical_subject = [s for s, _ in subj_counter.most_common(3)]
        canonical_object = [o for o, _ in obj_counter.most_common(5)]
        canonical_action = act_counter.most_common(1)[0][0] if act_counter else None
        topic_tags = [t for t, _ in tag_counter.most_common(3)]
        evidence_spans = ev_spans[:12]

        # representative event: highest (engagement_score + author_weight*10)
        rep = max(member_events, key=lambda e: (e.engagement_score + 10.0 * e.author_weight, e.llm_confidence))

        # aggregate engagement
        agg_eng = {"like": 0, "reply": 0, "repost": 0, "quote": 0}
        for ev in member_events:
            for k in agg_eng.keys():
                agg_eng[k] += int(ev.engagement.get(k, 0))
        agg_eng_score = engagement_score(agg_eng)
        kol_weight_sum = sum({ev.author: ev.author_weight for ev in member_events}.values())
        prop_cnt = sum(propagation_map.get(ev.event_id, 0) for ev in member_events)

        clusters.append(
            Cluster(
                cluster_id=f"cl_{idx:04d}",
                member_event_ids=sorted(member_ids),
                canonical_subject=canonical_subject,
                canonical_action=canonical_action,
                canonical_object=canonical_object,
                topic_tags=topic_tags,
                evidence_spans=evidence_spans,
                authors=sorted(authors_set),
                representative_event_id=rep.event_id,
                tweet_count=len(member_ids),
                author_count=len(authors_set),
                engagement=agg_eng,
                engagement_score=agg_eng_score,
                kol_weight_sum=float(kol_weight_sum),
                propagation_count=int(prop_cnt),
                score=0.0,
                score_breakdown={},
            )
        )
        idx += 1

    return clusters


# =============================================================================
# Step 7: scoring
# =============================================================================


def score_cluster(c: Cluster) -> Tuple[float, dict]:
    eng = c.engagement_score
    authors = c.author_count
    tweets = c.tweet_count
    prop = c.propagation_count
    kolw = c.kol_weight_sum

    # Score is intentionally code-governed (LLM does not decide rank).
    s_eng = 1.0 * math.log1p(eng)
    s_auth = 2.5 * authors
    s_kol = 2.0 * math.log1p(10.0 * kolw)
    s_prop = 1.2 * math.log1p(prop)
    s_size = 0.8 * math.log1p(tweets)

    score = s_eng + s_auth + s_kol + s_prop + s_size
    breakdown = {
        "engagement_score": eng,
        "tweet_count": tweets,
        "author_count": authors,
        "kol_weight_sum": kolw,
        "propagation_count": prop,
        "terms": {
            "log_engagement": round(s_eng, 4),
            "author_cnt": round(s_auth, 4),
            "log_kol_weight": round(s_kol, 4),
            "log_propagation": round(s_prop, 4),
            "log_size": round(s_size, 4),
        },
    }
    return score, breakdown


ACTION_CN = {
    "launch_release": "发布",
    "announce": "宣布",
    "open_source": "开源",
    "funding_investment": "融资/投资",
    "acquisition_merger": "并购",
    "partnership": "合作",
    "regulation_legal": "监管/法律",
    "outage_incident": "事故/故障",
    "benchmark_result": "测评/榜单",
    "product_update": "更新",
    "recognition_ranking": "获奖/排名",
    "hiring_org_change": "组织变动",
    "research_breakthrough": "研究突破",
    "other_event": "事件",
}


def fallback_title_cn(c: Cluster) -> str:
    subj = c.canonical_subject[0] if c.canonical_subject else "某主体"
    obj = c.canonical_object[0] if c.canonical_object else "相关事项"
    act = ACTION_CN.get(c.canonical_action or "other_event", "事件")
    title = f"{subj}{act}{obj}"
    return title[:40]


# =============================================================================
# Step 9: optional human edits
# =============================================================================


def apply_human_edits(
    clusters: List[Cluster],
    edits_path: str,
) -> Tuple[List[Cluster], List[dict]]:
    """
    Human edits file (jsonl), each row:
    {"op":"merge","a":"cl_0001","b":"cl_0007","note":"..."}
    {"op":"delete","cluster_id":"cl_0012","note":"..."}
    {"op":"rename","cluster_id":"cl_0003","title_cn":"...","note":"..."}
    """
    if not os.path.exists(edits_path):
        return clusters, []

    edits = read_jsonl(edits_path)
    by_id = {c.cluster_id: c for c in clusters}
    applied: List[dict] = []

    # merges first using union-find on cluster ids
    uf = UnionFind()
    for c in clusters:
        uf.find(c.cluster_id)
    for e in edits:
        if e.get("op") == "merge" and e.get("a") and e.get("b"):
            a, b = e["a"], e["b"]
            if a in by_id and b in by_id:
                uf.union(a, b)
                applied.append({"op": "merge", "a": a, "b": b, "note": e.get("note", "")})

    groups: Dict[str, List[str]] = defaultdict(list)
    for cid in by_id.keys():
        groups[uf.find(cid)].append(cid)

    # rebuild merged clusters by concatenation (simple but deterministic)
    new_clusters: List[Cluster] = []
    used: Set[str] = set()
    for root, member_cids in groups.items():
        if len(member_cids) == 1:
            cid = member_cids[0]
            new_clusters.append(by_id[cid])
            used.add(cid)
            continue
        # merge fields
        members = [by_id[cid] for cid in member_cids]
        member_event_ids = sorted({eid for m in members for eid in m.member_event_ids})
        canonical_subject = [s for s, _ in Counter([s for m in members for s in m.canonical_subject]).most_common(3)]
        canonical_object = [o for o, _ in Counter([o for m in members for o in m.canonical_object]).most_common(5)]
        canonical_action = Counter([m.canonical_action for m in members if m.canonical_action]).most_common(1)[0][0] if any(m.canonical_action for m in members) else None
        topic_tags = [t for t, _ in Counter([t for m in members for t in m.topic_tags]).most_common(3)]
        evidence_spans = []
        for m in members:
            for sp in m.evidence_spans:
                if sp not in evidence_spans:
                    evidence_spans.append(sp)
        authors = sorted({a for m in members for a in m.authors})
        rep = max(members, key=lambda m: (m.score, m.engagement_score))
        agg_eng = {"like": 0, "reply": 0, "repost": 0, "quote": 0}
        for m in members:
            for k in agg_eng.keys():
                agg_eng[k] += int(m.engagement.get(k, 0))
        merged = Cluster(
            cluster_id=min(member_cids),  # stable id: smallest
            member_event_ids=member_event_ids,
            canonical_subject=canonical_subject,
            canonical_action=canonical_action,
            canonical_object=canonical_object,
            topic_tags=topic_tags,
            evidence_spans=evidence_spans[:12],
            authors=authors,
            representative_event_id=rep.representative_event_id,
            tweet_count=len(member_event_ids),
            author_count=len(authors),
            engagement=agg_eng,
            engagement_score=engagement_score(agg_eng),
            kol_weight_sum=sum(m.kol_weight_sum for m in members),
            propagation_count=sum(m.propagation_count for m in members),
            score=0.0,
            score_breakdown={},
        )
        new_clusters.append(merged)
        used.update(member_cids)

    # deletes and renames
    deleted: Set[str] = set()
    renames: Dict[str, str] = {}
    for e in edits:
        if e.get("op") == "delete" and e.get("cluster_id"):
            deleted.add(e["cluster_id"])
            applied.append({"op": "delete", "cluster_id": e["cluster_id"], "note": e.get("note", "")})
        if e.get("op") == "rename" and e.get("cluster_id") and e.get("title_cn"):
            renames[e["cluster_id"]] = e["title_cn"]
            applied.append({"op": "rename", "cluster_id": e["cluster_id"], "title_cn": e["title_cn"], "note": e.get("note", "")})

    final_clusters: List[Cluster] = []
    for c in new_clusters:
        if c.cluster_id in deleted:
            continue
        if c.cluster_id in renames:
            c.title_cn = renames[c.cluster_id]
        final_clusters.append(c)

    return final_clusters, applied


# =============================================================================
# Main pipeline
# =============================================================================


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input_dir", default="inputs")
    ap.add_argument("--output_dir", default="outputs")
    ap.add_argument("--assets_dir", default="assets")
    ap.add_argument("--logs_dir", default="logs")
    ap.add_argument("--ollama_url", default="http://localhost:11434")
    ap.add_argument("--ollama_model", default="qwen2.5:7b-instruct")
    ap.add_argument("--ollama_timeout_s", type=int, default=120)
    ap.add_argument("--ollama_num_predict", type=int, default=800)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--max_tweets", type=int, default=0, help="0 means all")
    ap.add_argument("--min_text_len", type=int, default=30)
    ap.add_argument("--same_event_threshold", type=float, default=0.75)
    ap.add_argument("--max_bucket_size", type=int, default=120)
    ap.add_argument("--max_pairs_total", type=int, default=4000)
    ap.add_argument("--llm_enabled", action="store_true")
    ap.add_argument("--no_llm", action="store_true")
    ap.add_argument("--overwrite_outputs", action="store_true", help="Delete existing outputs/logs in the target dirs before running")
    args = ap.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    input_dir = os.path.join(base_dir, args.input_dir)
    output_dir = os.path.join(base_dir, args.output_dir)
    logs_dir = os.path.join(base_dir, args.logs_dir)
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(logs_dir, exist_ok=True)

    if args.overwrite_outputs:
        for fn in [
            "events_structured.jsonl",
            "events_filtered.jsonl",
            "event_pairs_candidates.jsonl",
            "event_pairs_same_event.jsonl",
            "event_clusters.json",
            "hot_events_top5.json",
            "daily_report.json",
            "daily_report_readable.json",
        ]:
            p = os.path.join(output_dir, fn)
            if os.path.exists(p):
                os.remove(p)
        for fn in ["llm_raw.jsonl", "run_stats.json"]:
            p = os.path.join(logs_dir, fn)
            if os.path.exists(p):
                os.remove(p)

    llm_enabled = bool(args.llm_enabled) and not bool(args.no_llm)
    raw_log = os.path.join(logs_dir, "llm_raw.jsonl")
    retry_cfg = RetryConfig(max_retry=3, backoff_s=1.0)
    ollama_cfg = OllamaConfig(
        base_url=args.ollama_url,
        model=args.ollama_model,
        temperature=float(args.temperature),
        num_predict=int(args.ollama_num_predict),
        timeout_s=int(args.ollama_timeout_s),
    )

    prompts_dir = os.path.join(base_dir, "prompts")
    system_prompt = read_prompt(os.path.join(prompts_dir, "system.txt"))
    p_event_extract = read_prompt(os.path.join(prompts_dir, "event_extract.txt"))
    p_event_filter = read_prompt(os.path.join(prompts_dir, "event_filter.txt"))
    p_same_event = read_prompt(os.path.join(prompts_dir, "same_event.txt"))
    p_title_summary = read_prompt(os.path.join(prompts_dir, "title_summary.txt"))

    # Inputs
    tweets_path = os.path.join(input_dir, "tweets_24h_clean.jsonl")
    kol_profiles_path = os.path.join(input_dir, "kol_profiles.jsonl")
    edges_path = os.path.join(input_dir, "edges_24h.jsonl")
    edits_path = os.path.join(input_dir, "human_edits.jsonl")

    tweets = read_jsonl(tweets_path)
    if args.max_tweets and args.max_tweets > 0:
        tweets = tweets[: args.max_tweets]

    profiles = load_kol_profiles(kol_profiles_path)
    edges_24h = read_jsonl(edges_path) if os.path.exists(edges_path) else None

    stats: Dict[str, Any] = {"generated_at": now_utc_iso(), "steps": {}}

    # -------------------------------------------------------------------------
    # Step 1: per-tweet event extraction (LLM)
    # -------------------------------------------------------------------------
    out_step1 = os.path.join(output_dir, "events_structured.jsonl")
    done_step1: Set[str] = set()
    if os.path.exists(out_step1):
        for r in read_jsonl(out_step1):
            tid = str(r.get("tweet_id", "") or "")
            if tid:
                done_step1.add(tid)

    step1_rows = []
    step1_counts = {"input": len(tweets), "skipped_existing": 0, "llm_called": 0, "llm_failed": 0}

    for tw in tweets:
        tid = str(tw.get("tweet_id", "") or "")
        if not tid:
            continue
        if tid in done_step1:
            step1_counts["skipped_existing"] += 1
            continue

        text = safe_get_text(tw)
        author = norm_username(tw.get("author_username", "") or tw.get("author", ""))
        created_at = tw.get("created_at", "") or tw.get("created_at_local", "") or ""

        # If LLM disabled, use conservative fallback: non-event.
        if not llm_enabled:
            step1 = {
                "is_event": False,
                "relevance_captech": False,
                "subject": [],
                "action": None,
                "object": [],
                "event_type": None,
                "topic_tags": [],
                "evidence_spans": [],
                "confidence": 0.0,
                "why": "LLM disabled; no extraction performed.",
            }
        else:
            try:
                step1_counts["llm_called"] += 1
                prompt = system_prompt + "\n\n" + p_event_extract.format(author=author, text=text)

                def _call(p: str) -> str:
                    return ollama_generate(cfg=ollama_cfg, prompt=p, stream=False)

                def _on_raw(resp_text: str, attempt: int) -> None:
                    append_jsonl(raw_log, {"ts": now_utc_iso(), "call_id": f"step1:{tid}", "attempt": attempt, "model": ollama_cfg.model, "content": resp_text})

                step1 = call_llm_json_local(
                    _call,
                    prompt,
                    expected_keys=["is_event", "relevance_captech", "subject", "action", "object", "event_type", "topic_tags", "evidence_spans", "confidence", "why"],
                    validator_fn=validate_step1,
                    retry_cfg=retry_cfg,
                    on_raw_response=_on_raw,
                )
            except Exception as e:
                step1_counts["llm_failed"] += 1
                step1 = {
                    "is_event": False,
                    "relevance_captech": False,
                    "subject": [],
                    "action": None,
                    "object": [],
                    "event_type": None,
                    "topic_tags": [],
                    "evidence_spans": [],
                    "confidence": 0.0,
                    "why": f"LLM error: {str(e)[:200]}",
                }

        row = {
            "tweet_id": tid,
            "author": author,
            "created_at": created_at,
            "text": text,
            "public_metrics": tw.get("public_metrics", {}),
            "referenced_tweets": tw.get("referenced_tweets", []),
            "step1": step1,
            "llm": {"enabled": llm_enabled, "provider": "ollama", "model": ollama_cfg.model, "temperature": ollama_cfg.temperature},
        }
        append_jsonl(out_step1, row)
        step1_rows.append(row)

    stats["steps"]["step1"] = step1_counts

    # Load full step1 output as base for next steps
    structured = read_jsonl(out_step1)

    # -------------------------------------------------------------------------
    # Step 2: hard rules + LLM gate (quality & captech relevance)
    # -------------------------------------------------------------------------
    out_filtered = os.path.join(output_dir, "events_filtered.jsonl")
    done_step2: Set[str] = set()
    if os.path.exists(out_filtered):
        for r in read_jsonl(out_filtered):
            tid = str(r.get("event_id", "") or r.get("tweet_id", "") or "")
            if tid:
                done_step2.add(tid)

    filtered_events: List[EventCard] = []
    step2_counts = {
        "input": len(structured),
        "skipped_existing": 0,
        "rule_dropped": 0,
        "llm_gate_called": 0,
        "llm_gate_failed": 0,
        "kept": 0,
    }
    drop_reasons = Counter()

    for r in structured:
        tid = str(r.get("tweet_id", "") or "")
        if not tid:
            continue
        if tid in done_step2:
            step2_counts["skipped_existing"] += 1
            continue

        text = str(r.get("text", "") or "")
        step1 = r.get("step1", {}) or {}
        is_ev = bool(step1.get("is_event", False))

        # Hard rule filter (applies before LLM gate)
        rule_drop, rule_reason = is_rule_drop(text, min_len=args.min_text_len)
        if rule_drop:
            step2_counts["rule_dropped"] += 1
            drop_reasons[rule_reason] += 1
            continue

        # Only gate candidates that are events (step1)
        if not is_ev:
            drop_reasons["step1_not_event"] += 1
            continue

        if not llm_enabled:
            gate = {"keep": True, "reason": "LLM disabled; keep for downstream (debug).", "relevance_captech": bool(step1.get("relevance_captech", False)), "quality_score": float(step1.get("confidence", 0.0))}
        else:
            try:
                step2_counts["llm_gate_called"] += 1
                prompt = system_prompt + "\n\n" + p_event_filter.format(event_json=json.dumps(step1, ensure_ascii=False))

                def _call(p: str) -> str:
                    return ollama_generate(cfg=ollama_cfg, prompt=p, stream=False)

                def _on_raw(resp_text: str, attempt: int) -> None:
                    append_jsonl(raw_log, {"ts": now_utc_iso(), "call_id": f"step2:{tid}", "attempt": attempt, "model": ollama_cfg.model, "content": resp_text})

                gate = call_llm_json_local(
                    _call,
                    prompt,
                    expected_keys=["keep", "relevance_captech", "quality_score", "reason"],
                    validator_fn=validate_step2,
                    retry_cfg=retry_cfg,
                    on_raw_response=_on_raw,
                )
            except Exception as e:
                step2_counts["llm_gate_failed"] += 1
                gate = {"keep": False, "reason": f"LLM error: {str(e)[:200]}", "relevance_captech": False, "quality_score": 0.0}

        keep = bool(gate.get("keep", False)) and bool(gate.get("relevance_captech", False))
        if not keep:
            drop_reasons["gate_rejected"] += 1
            continue
        if float(gate.get("quality_score", 0.0) or 0.0) < 0.45:
            drop_reasons["quality_low"] += 1
            continue

        # Step 3: normalize to EventCard
        # We need original tweet dict for metrics; re-find from tweets map
        # (structured already has metrics; good enough)
        fake_tweet = {
            "tweet_id": tid,
            "author_username": r.get("author", ""),
            "created_at": r.get("created_at", ""),
            "clean_text": r.get("text", ""),
            "public_metrics": r.get("public_metrics", {}),
            "referenced_tweets": r.get("referenced_tweets", []),
        }
        ev = normalize_event_card(fake_tweet, step1, profiles)
        step2_counts["kept"] += 1

        out_row = ev.to_dict()
        out_row["step2_gate"] = gate
        append_jsonl(out_filtered, out_row)
        filtered_events.append(ev)

    stats["steps"]["step2"] = step2_counts
    stats["steps"]["step2_drop_reasons"] = dict(drop_reasons)

    # Load full filtered events (in case of resume)
    filtered_rows = read_jsonl(out_filtered)
    filtered_events = []
    for rr in filtered_rows:
        ev = eventcard_from_row(rr)
        if ev:
            filtered_events.append(ev)

    stats["steps"]["step3"] = {"normalized_events": len(filtered_events)}

    # -------------------------------------------------------------------------
    # Step 4: candidate pair generation
    # -------------------------------------------------------------------------
    out_pairs_candidates = os.path.join(output_dir, "event_pairs_candidates.jsonl")
    pairs_candidates: List[Tuple[str, str, dict]] = []
    if os.path.exists(out_pairs_candidates):
        for pr in read_jsonl(out_pairs_candidates):
            a, b = pr.get("a_event_id"), pr.get("b_event_id")
            if a and b:
                pairs_candidates.append((a, b, pr.get("reason", {})))
    else:
        pairs_candidates = generate_candidate_pairs(
            filtered_events,
            max_bucket_size=args.max_bucket_size,
            max_pairs_total=args.max_pairs_total,
        )
        write_jsonl(
            out_pairs_candidates,
            (
                {"a_event_id": a, "b_event_id": b, "reason": reason}
                for (a, b, reason) in pairs_candidates
            ),
        )
    stats["steps"]["step4"] = {"events": len(filtered_events), "candidate_pairs": len(pairs_candidates)}

    # -------------------------------------------------------------------------
    # Step 5: same-event judge (LLM)
    # -------------------------------------------------------------------------
    out_pairs_same = os.path.join(output_dir, "event_pairs_same_event.jsonl")
    done_pairs: Set[Tuple[str, str]] = set()
    if os.path.exists(out_pairs_same):
        for rr in read_jsonl(out_pairs_same):
            a, b = rr.get("a_event_id"), rr.get("b_event_id")
            if a and b:
                x, y = (a, b) if a < b else (b, a)
                done_pairs.add((x, y))

    by_id = {e.event_id: e for e in filtered_events}
    same_edges: List[dict] = []
    step5_counts = {"candidate_pairs": len(pairs_candidates), "skipped_existing": 0, "llm_called": 0, "llm_failed": 0, "same_event_true": 0, "edges_used": 0}

    for a, b, reason in pairs_candidates:
        x, y = (a, b) if a < b else (b, a)
        if (x, y) in done_pairs:
            step5_counts["skipped_existing"] += 1
            continue
        ea, eb = by_id.get(x), by_id.get(y)
        if not ea or not eb:
            continue

        if not llm_enabled:
            # conservative: do not merge without LLM
            same = {"same_event": False, "confidence": 0.0, "merge_reason": "LLM disabled; no merging.", "canonical_subject": None, "canonical_action": None, "canonical_object": None}
        else:
            try:
                step5_counts["llm_called"] += 1
                prompt = system_prompt + "\n\n" + p_same_event.format(
                    event_a=json.dumps({"tweet": ea.tweet_text, "event": ea.to_dict()}, ensure_ascii=False),
                    event_b=json.dumps({"tweet": eb.tweet_text, "event": eb.to_dict()}, ensure_ascii=False),
                )

                def _call(p: str) -> str:
                    return ollama_generate(cfg=ollama_cfg, prompt=p, stream=False)

                def _on_raw(resp_text: str, attempt: int) -> None:
                    append_jsonl(raw_log, {"ts": now_utc_iso(), "call_id": f"step5:{x}__{y}", "attempt": attempt, "model": ollama_cfg.model, "content": resp_text})

                same = call_llm_json_local(
                    _call,
                    prompt,
                    expected_keys=["same_event", "confidence", "merge_reason", "canonical_subject", "canonical_action", "canonical_object"],
                    validator_fn=validate_step5,
                    retry_cfg=retry_cfg,
                    on_raw_response=_on_raw,
                )
            except Exception as e:
                step5_counts["llm_failed"] += 1
                same = {"same_event": False, "confidence": 0.0, "merge_reason": f"LLM error: {str(e)[:200]}", "canonical_subject": None, "canonical_action": None, "canonical_object": None}

        row = {
            "a_event_id": x,
            "b_event_id": y,
            "reason": reason,
            "decision": same,
        }
        append_jsonl(out_pairs_same, row)

        if bool(same.get("same_event", False)):
            step5_counts["same_event_true"] += 1
            conf = float(same.get("confidence", 0.0) or 0.0)
            if conf >= args.same_event_threshold:
                same_edges.append(
                    {
                        "a_event_id": x,
                        "b_event_id": y,
                        "confidence": conf,
                        "merge_reason": same.get("merge_reason", ""),
                        "canonical_subject": same.get("canonical_subject", None),
                        "canonical_action": same.get("canonical_action", None),
                        "canonical_object": same.get("canonical_object", None),
                    }
                )
                step5_counts["edges_used"] += 1

    # Also load edges_used from existing file (resume case)
    if os.path.exists(out_pairs_same):
        for rr in read_jsonl(out_pairs_same):
            d = rr.get("decision", {}) or {}
            if not d.get("same_event"):
                continue
            conf = float(d.get("confidence", 0.0) or 0.0)
            if conf < args.same_event_threshold:
                continue
            a, b = rr.get("a_event_id"), rr.get("b_event_id")
            if a and b:
                same_edges.append(
                    {
                        "a_event_id": a,
                        "b_event_id": b,
                        "confidence": conf,
                        "merge_reason": d.get("merge_reason", ""),
                        "canonical_subject": d.get("canonical_subject", None),
                        "canonical_action": d.get("canonical_action", None),
                        "canonical_object": d.get("canonical_object", None),
                    }
                )

    stats["steps"]["step5"] = step5_counts

    # -------------------------------------------------------------------------
    # Step 6: clustering/merge execution
    # -------------------------------------------------------------------------
    clusters = build_clusters(filtered_events, same_edges, edges_24h=edges_24h)

    # -------------------------------------------------------------------------
    # Step 7: scoring
    # -------------------------------------------------------------------------
    for c in clusters:
        s, breakdown = score_cluster(c)
        c.score = float(s)
        c.score_breakdown = breakdown

    clusters.sort(key=lambda c: c.score, reverse=True)

    # -------------------------------------------------------------------------
    # Step 9 (optional): apply human edits BEFORE final presentation
    # -------------------------------------------------------------------------
    clusters, applied_edits = apply_human_edits(clusters, edits_path=edits_path)
    # re-score after edits (merge changes sums)
    for c in clusters:
        s, breakdown = score_cluster(c)
        c.score = float(s)
        c.score_breakdown = breakdown
    clusters.sort(key=lambda c: c.score, reverse=True)

    # -------------------------------------------------------------------------
    # Step 8: title & summary for top clusters (LLM)
    # -------------------------------------------------------------------------
    top5 = clusters[:5]
    # pre-build tweet texts for each cluster
    by_event_id = {e.event_id: e for e in filtered_events}

    for c in top5:
        # allow human rename to override
        if c.title_cn and c.summary_bullets_cn and c.why_hot_cn:
            continue

        member_events = [by_event_id[eid] for eid in c.member_event_ids if eid in by_event_id]
        member_events.sort(key=lambda e: (e.engagement_score + 10.0 * e.author_weight), reverse=True)
        top_tweets = [e.tweet_text[:240] for e in member_events[:3]]

        if not llm_enabled:
            c.title_cn = c.title_cn or fallback_title_cn(c)
            c.summary_bullets_cn = [
                f"主体：{(' / '.join(c.canonical_subject) if c.canonical_subject else '未知')}",
                f"动作：{ACTION_CN.get(c.canonical_action or 'other_event', '事件')}",
                f"对象：{(' / '.join(c.canonical_object[:3]) if c.canonical_object else '未知')}",
            ]
            c.why_hot_cn = "LLM 未启用；以下为规则化摘要。"
            continue

        try:
            prompt = system_prompt + "\n\n" + p_title_summary.format(
                subject=json.dumps(c.canonical_subject, ensure_ascii=False),
                action=json.dumps(c.canonical_action, ensure_ascii=False),
                object=json.dumps(c.canonical_object, ensure_ascii=False),
                tweets=json.dumps(top_tweets, ensure_ascii=False),
            )

            def _call(p: str) -> str:
                return ollama_generate(cfg=ollama_cfg, prompt=p, stream=False)

            def _on_raw(resp_text: str, attempt: int) -> None:
                append_jsonl(raw_log, {"ts": now_utc_iso(), "call_id": f"step8:{c.cluster_id}", "attempt": attempt, "model": ollama_cfg.model, "content": resp_text})

            out = call_llm_json_local(
                _call,
                prompt,
                expected_keys=["title_cn", "summary_bullets_cn", "why_hot_cn"],
                validator_fn=validate_step8,
                retry_cfg=retry_cfg,
                on_raw_response=_on_raw,
            )
            c.title_cn = out["title_cn"]
            c.summary_bullets_cn = out["summary_bullets_cn"]
            c.why_hot_cn = out["why_hot_cn"]
        except Exception:
            c.title_cn = c.title_cn or fallback_title_cn(c)
            c.summary_bullets_cn = [
                f"主体：{(' / '.join(c.canonical_subject) if c.canonical_subject else '未知')}",
                f"动作：{ACTION_CN.get(c.canonical_action or 'other_event', '事件')}",
                f"对象：{(' / '.join(c.canonical_object[:3]) if c.canonical_object else '未知')}",
            ]
            c.why_hot_cn = "标题生成失败；已使用兜底模板。"

    # -------------------------------------------------------------------------
    # Write outputs
    # -------------------------------------------------------------------------
    out_clusters = os.path.join(output_dir, "event_clusters.json")
    write_json(out_clusters, {"generated_at": now_utc_iso(), "clusters": [c.to_dict() for c in clusters]})

    out_top5 = os.path.join(output_dir, "hot_events_top5.json")
    write_json(
        out_top5,
        {
            "generated_at": now_utc_iso(),
            "version": "V2.5",
            "top5": [c.to_dict() for c in top5],
        },
    )

    daily_report = {
        "generated_at": now_utc_iso(),
        "version": "V2.5",
        "window": "24h",
        "llm": {"enabled": llm_enabled, "provider": "ollama", "model": ollama_cfg.model, "temperature": ollama_cfg.temperature, "base_url": ollama_cfg.base_url},
        "summary": {
            "total_tweets": len(tweets),
            "events_structured": len(structured),
            "events_filtered": len(filtered_events),
            "clusters": len(clusters),
            "top5": [
                {
                    "rank": i + 1,
                    "cluster_id": c.cluster_id,
                    "title_cn": c.title_cn or fallback_title_cn(c),
                    "score": round(c.score, 3),
                    "tweet_count": c.tweet_count,
                    "author_count": c.author_count,
                }
                for i, c in enumerate(top5)
            ],
        },
        "top5": [
            {
                "rank": i + 1,
                "cluster_id": c.cluster_id,
                "title_cn": c.title_cn or fallback_title_cn(c),
                "summary_bullets_cn": c.summary_bullets_cn or [],
                "why_hot_cn": c.why_hot_cn or "",
                "canonical_subject": c.canonical_subject,
                "canonical_action": c.canonical_action,
                "canonical_object": c.canonical_object,
                "topic_tags": c.topic_tags,
                "metrics": {
                    "tweet_count": c.tweet_count,
                    "author_count": c.author_count,
                    "engagement": c.engagement,
                    "engagement_score": round(c.engagement_score, 2),
                    "kol_weight_sum": round(c.kol_weight_sum, 2),
                    "propagation_count": c.propagation_count,
                },
                "score": round(c.score, 3),
                "score_breakdown": c.score_breakdown,
                "representative_event_id": c.representative_event_id,
                "member_event_ids": c.member_event_ids[:50],
            }
            for i, c in enumerate(top5)
        ],
        "human_edits_applied": applied_edits,
        "stats": stats,
    }
    write_json(os.path.join(output_dir, "daily_report.json"), daily_report)

    readable = {
        "生成时间": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "版本": "V2.5",
        "时间窗口": "24小时",
        "Top5热点事件": [
            {
                "排名": i + 1,
                "标题": c.title_cn or fallback_title_cn(c),
                "要点": c.summary_bullets_cn or [],
                "为何热门": c.why_hot_cn or "",
                "分数": round(c.score, 2),
                "推文数": c.tweet_count,
                "作者数": c.author_count,
                "互动量": c.engagement,
                "KOL权重和": round(c.kol_weight_sum, 2),
                "传播强度": c.propagation_count,
                "主体": c.canonical_subject,
                "动作": c.canonical_action,
                "对象": c.canonical_object,
            }
            for i, c in enumerate(top5)
        ],
    }
    write_json(os.path.join(output_dir, "daily_report_readable.json"), readable)

    write_json(os.path.join(logs_dir, "run_stats.json"), stats)

    print("Pipeline V2.5 complete.")
    print(f"Outputs in: {output_dir}")


if __name__ == "__main__":
    main()

