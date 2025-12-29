"""
V2 事件级聚类方案 - 最终版（New）

核心思想：
- 你不是在做"文本聚类"，你是在做"现实世界事件的自动归纳"
- 人工资产层前置：定义世界，而不是修补结果
- 事件级聚类：聚焦现实世界事件，不是文本相似度
- 传播锚点优先：完全结构化，无语义歧义
- 结构化权重层级：合并条件按优先级排序

方案特点：
1. Step 0: 人工资产层（必须新增）
2. Step 1: 事件候选生成（受限，必须命中白名单）
3. Step 2: 强规则过滤（升级，更完整的黑名单）
4. Step 3: 传播锚点聚类（完全保留，权重最高）
5. Step 4: 增量式事件合并（结构化权重层级）
6. Step 5: 受限语义确认（默认关闭）
7. Step 6: 半人工校正（必须）
"""

import json
import os
import re
import math
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Set, Optional, Tuple

# ============================================================================
# Step 0: 人工资产层（必须新增）
# ============================================================================

# 0.1 Frontier Entity Dictionary（人工维护）

# A. Companies（公司）
FRONTIER_COMPANIES = {
    "OpenAI", "Anthropic", "Google", "DeepMind", "Meta", "Microsoft", "Amazon", "AWS",
    "NVIDIA", "AMD", "Intel", "TSMC", "Apple", "Tesla", "xAI", "Stability AI",
    "Mistral", "Cohere", "HuggingFace", "Perplexity",
    "Alibaba", "Tencent", "Baidu", "ByteDance",
    "Stripe", "PayPal", "Visa", "Mastercard",
    "BlackRock", "Sequoia", "a16z", "SoftBank"
}

# B. Products / Models（产品/模型）
FRONTIER_PRODUCTS = {
    "GPT-4", "GPT-5", "ChatGPT", "Codex", "Sora",
    "Gemini", "Claude", "Llama", "Grok",
    "H100", "H200", "Blackwell", "CUDA",
    "TPU", "ROCm",
    "Copilot", "Devin", "AutoGPT"
}

# C. Infra / Concepts（基础设施/概念）
FRONTIER_CONCEPTS = {
    "LLM", "Multimodal", "MoE", "RLHF", "RLAIF",
    "Inference", "Training", "Fine-tuning",
    "AGI", "Alignment", "Safety",
    "AI Agent", "Robotics", "Autonomous"
}

# 合并所有实体
FRONTIER_ENTITY_DICTIONARY = FRONTIER_COMPANIES | FRONTIER_PRODUCTS | FRONTIER_CONCEPTS

# 0.2 Frontier Action Verbs（人工维护）

# 发布 / 变化类
ACTION_RELEASE = {
    "launch", "release", "announce", "ship", "open-source", "unveil", "introduce",
    "launched", "released", "announced", "shipped", "unveiled", "introduced"
}

# 投融资
ACTION_FUNDING = {
    "raise", "funding", "invest", "acquire", "acquisition", "IPO", "valuation",
    "raised", "invested", "acquired"
}

# 技术进展
ACTION_TECH = {
    "benchmark", "outperform", "replace", "scale", "optimize", "accelerate",
    "benchmarked", "outperformed", "replaced", "scaled", "optimized", "accelerated"
}

# 事件 / 风险
ACTION_EVENT = {
    "leak", "rumor", "incident", "outage", "ban", "regulation", "lawsuit",
    "leaked", "rumored", "banned"
}

# 合并所有动作词
FRONTIER_ACTION_VERBS = ACTION_RELEASE | ACTION_FUNDING | ACTION_TECH | ACTION_EVENT

# 0.3 Hard Stop Words / Platform Blacklist（必须完整）

# 平台 / 域名（强制丢弃）
PLATFORM_DOMAINS = {
    "google.com", "twitter.com", "x.com", "youtube.com",
    "medium.com", "substack.com", "github.com",
    "linkedin.com", "reddit.com", "wikipedia.org"
}

# 泛化词（不得成为 topic）
HARD_STOP_WORDS = {
    "ai", "technology", "tech", "startup", "market", "industry",
    "news", "update", "report", "article", "blog",
    "amazing", "huge", "big", "insane", "crazy"
}

# ============================================================================
# 工具函数
# ============================================================================

def load_jsonl(file_path: str) -> List[dict]:
    """加载 JSONL 文件"""
    data = []
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    data.append(json.loads(line))
    return data

def save_jsonl(data: List[dict], file_path: str):
    """保存 JSONL 文件"""
    os.makedirs(os.path.dirname(file_path) if os.path.dirname(file_path) else ".", exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

def norm_username(username: str) -> str:
    """标准化用户名"""
    if not username:
        return ""
    return username.lower().replace("@", "").strip()

def extract_domain(url: str) -> Optional[str]:
    """从 URL 中提取域名"""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path
        domain = domain.replace("www.", "").lower()
        return domain if domain else None
    except:
        return None

# ============================================================================
# Step 1: 事件候选生成（受限）
# ============================================================================

def extract_entities_from_tweet_restricted(tweet: dict) -> Tuple[List[str], bool]:
    """
    从推文中提取实体（受限，必须命中 Entity Dictionary）
    返回: (实体列表, 是否有效)
    """
    entities = []
    text_upper = tweet.get("text", "").upper()
    text_lower = tweet.get("text", "").lower()
    
    # 检查是否命中 Entity Dictionary
    for entity in FRONTIER_ENTITY_DICTIONARY:
        if entity.upper() in text_upper or entity.lower() in text_lower:
            entities.append(entity)
    
    # 必须至少命中一个实体
    entity_valid = len(entities) > 0
    
    return entities, entity_valid

def extract_action_from_text_restricted(text: str) -> Tuple[Optional[str], bool]:
    """
    从文本中提取动作词（受限，必须命中 Action Verbs）
    返回: (动作词, 是否有效)
    """
    text_lower = text.lower()
    
    for verb in FRONTIER_ACTION_VERBS:
        if verb.lower() in text_lower:
            return verb, True
    
    return None, False

def step1_event_candidates_restricted(
    tweets_24h_clean_path: str,
    edges_24h_path: str,
    output_dir: str = ".",
) -> Tuple[List[dict], Dict[str, int]]:
    """
    Step 1: 事件候选生成（受限）
    规则：
    - 一条 tweet = 一个 EventCandidate
    - entity ∈ Entity Dictionary（必须命中）
    - action ∈ Action Verbs（必须命中）
    - 否则直接丢弃
    """
    print("Step 1: 事件候选生成（受限）...")
    
    tweets = load_jsonl(tweets_24h_clean_path)
    edges_24h = load_jsonl(edges_24h_path)
    
    # 统计每个 tweet 被引用的次数
    reference_count = defaultdict(int)
    for edge in edges_24h:
        target_tweet_id = edge.get("target_tweet_id", "")
        if target_tweet_id:
            reference_count[target_tweet_id] += 1
    
    event_candidates = []
    dropped_stats = defaultdict(int)
    
    for tweet in tweets:
        tweet_id = tweet.get("tweet_id", "")
        if not tweet_id:
            continue
        
        # 提取实体（受限）
        entities, entity_valid = extract_entities_from_tweet_restricted(tweet)
        if not entity_valid:
            dropped_stats["无有效实体"] += 1
            continue
        
        # 提取动作（受限）
        text = tweet.get("clean_text", tweet.get("text", ""))
        action, action_valid = extract_action_from_text_restricted(text)
        if not action_valid:
            dropped_stats["无有效动作"] += 1
            continue
        
        # 判断是否是传播锚点
        ref_count = reference_count.get(tweet_id, 0)
        is_anchor = ref_count >= 1  # 可调整
        
        # 获取引用的 tweet（如果有）
        referenced_tweets = tweet.get("referenced_tweets", [])
        referenced_tweet_id = None
        anchor_id = None
        for ref in referenced_tweets:
            if ref.get("type") in ["reposted", "quoted"]:
                referenced_tweet_id = ref.get("id", "")
                anchor_id = referenced_tweet_id
                break
        
        # 构造 EventCandidate
        event_candidate = {
            "event_id": tweet_id,
            "entity": entities,
            "action": action,
            "time": tweet.get("created_ts", 0),
            "text": text,
            "author": norm_username(tweet.get("author_username", "")),
            "is_anchor": is_anchor,
            "reference_count": ref_count,
            "referenced_tweet_id": referenced_tweet_id,
            "anchor_id": anchor_id,
            "engagement": tweet.get("public_metrics", {})
        }
        
        event_candidates.append(event_candidate)
    
    # 保存
    output_path = os.path.join(output_dir, "event_candidates_v2_new.jsonl")
    save_jsonl(event_candidates, output_path)
    
    print(f"  总推文数: {len(tweets)}")
    print(f"  生成了 {len(event_candidates)} 个事件候选")
    print(f"  丢弃统计:")
    for reason, count in dropped_stats.items():
        print(f"    {reason}: {count}")
    print(f"  其中 {sum(1 for c in event_candidates if c['is_anchor'])} 个是传播锚点")
    print("Step 1: 完成\n")
    
    return event_candidates, reference_count

# ============================================================================
# Step 2: 强规则过滤（升级）
# ============================================================================

def step2_hard_rules_filter_upgraded(
    event_candidates: List[dict],
    output_dir: str = ".",
) -> List[dict]:
    """
    Step 2: 强规则过滤（升级）
    Hard Drop Rules（命中即丢）：
    1. entity_valid = false（已在 Step 1 处理）
    2. action_valid = false（已在 Step 1 处理）
    3. 命中 platform domain
    4. 只有 URL
    5. 只有泛词
    """
    print("Step 2: 强规则过滤（升级）...")
    
    filtered_candidates = []
    filter_stats = defaultdict(int)
    
    for candidate in event_candidates:
        text = candidate.get("text", "")
        entities = candidate.get("entity", [])
        
        # Hard Rule 1: 命中 platform domain
        # 检查 URL domains
        url_domains = []
        # 从文本中提取 URL
        urls = re.findall(r'https?://([^\s/]+)', text)
        for url in urls:
            domain = extract_domain(url)
            if domain:
                url_domains.append(domain)
        
        is_platform = False
        for domain in url_domains:
            if domain in PLATFORM_DOMAINS:
                is_platform = True
                break
        
        if is_platform:
            filter_stats["平台域名"] += 1
            continue
        
        # Hard Rule 2: 文本只有 URL / domain
        text_without_url = re.sub(r'https?://\S+', '', text)
        text_without_url = re.sub(r'<URL>', '', text_without_url)
        if not text_without_url.strip():
            filter_stats["只有URL"] += 1
            continue
        
        # Hard Rule 3: 只有泛词
        words = set(re.findall(r'\b\w+\b', text.lower()))
        generic_only = words.issubset(HARD_STOP_WORDS)
        if generic_only and len(words) > 0:
            filter_stats["只有泛词"] += 1
            continue
        
        # 通过所有规则
        filtered_candidates.append(candidate)
    
    # 保存
    output_path = os.path.join(output_dir, "event_candidates_filtered_v2_new.jsonl")
    save_jsonl(filtered_candidates, output_path)
    
    # 输出统计
    print(f"  总候选数: {len(event_candidates)}")
    print(f"  过滤后: {len(filtered_candidates)}")
    print(f"  过滤统计:")
    for reason, count in filter_stats.items():
        print(f"    {reason}: {count}")
    print("Step 2: 完成\n")
    
    return filtered_candidates

# ============================================================================
# Step 3: 传播锚点聚类（完全保留，权重最高）
# ============================================================================

def step3_anchor_clustering(
    filtered_candidates: List[dict],
    edges_24h: List[dict],
    reference_count: Dict[str, int],
    output_dir: str = ".",
) -> Tuple[List[dict], Set[str]]:
    """
    Step 3: 传播锚点聚类
    被 ≥1 KOL 引用的 tweet → anchor
    所有指向它的 tweet → 同一 cluster
    anchor cluster 权重最高
    """
    print("Step 3: 传播锚点聚类（权重最高）...")
    
    # 构建候选映射
    candidate_map = {c.get("event_id"): c for c in filtered_candidates}
    
    # 识别传播锚点
    anchors = [c for c in filtered_candidates if c.get("is_anchor", False)]
    
    print(f"  找到 {len(anchors)} 个传播锚点")
    
    # 为每个锚点创建事件簇
    event_clusters = []
    clustered_event_ids = set()
    
    for anchor in anchors:
        anchor_id = anchor.get("event_id", "")
        if anchor_id in clustered_event_ids:
            continue
        
        # 创建事件簇
        cluster = {
            "cluster_id": f"anchor_{anchor_id}",
            "cluster_type": "anchor",
            "weight": 10.0,  # anchor cluster 权重最高
            "anchor_tweet": anchor,
            "event_ids": [anchor_id],
            "authors": [anchor.get("author", "")],
            "entities": set(anchor.get("entity", [])),
            "action": anchor.get("action"),
            "created_ts_range": [anchor.get("time", 0), anchor.get("time", 0)]
        }
        
        clustered_event_ids.add(anchor_id)
        
        # 找到所有指向这个锚点的 tweet
        for edge in edges_24h:
            target_tweet_id = edge.get("target_tweet_id", "")
            source_tweet_id = edge.get("source_tweet_id", "")
            
            if target_tweet_id == anchor_id:
                source_candidate = candidate_map.get(source_tweet_id)
                if source_candidate and source_tweet_id not in clustered_event_ids:
                    cluster["event_ids"].append(source_tweet_id)
                    cluster["authors"].append(source_candidate.get("author", ""))
                    cluster["entities"].update(source_candidate.get("entity", []))
                    cluster["created_ts_range"][0] = min(cluster["created_ts_range"][0], source_candidate.get("time", 0))
                    cluster["created_ts_range"][1] = max(cluster["created_ts_range"][1], source_candidate.get("time", 0))
                    clustered_event_ids.add(source_tweet_id)
        
        # 转换 entities 为列表
        cluster["entities"] = list(cluster["entities"])
        cluster["tweet_count"] = len(cluster["event_ids"])
        cluster["author_count"] = len(set(cluster["authors"]))
        
        event_clusters.append(cluster)
    
    # 保存
    output_path = os.path.join(output_dir, "event_clusters_anchor_v2_new.jsonl")
    save_jsonl(event_clusters, output_path)
    
    print(f"  生成了 {len(event_clusters)} 个传播锚点事件簇")
    print(f"  覆盖了 {len(clustered_event_ids)} 个事件候选")
    print("Step 3: 完成\n")
    
    return event_clusters, clustered_event_ids

# ============================================================================
# Step 4: 增量式事件合并（结构化权重层级）
# ============================================================================

def check_merge_conditions_weighted(
    tweet1: dict,
    tweet2: dict,
    edges_24h: List[dict],
    max_time_diff: int = 48 * 3600
) -> Tuple[bool, float, str]:
    """
    检查是否可以合并（结构化权重层级）
    返回: (是否可以合并, 权重, 条件描述)
    """
    weight = 0.0
    condition = None
    
    # 条件1: 同一 anchor（最强，权重 10.0）
    anchor_id1 = tweet1.get("anchor_id")
    anchor_id2 = tweet2.get("anchor_id")
    if anchor_id1 and anchor_id2 and anchor_id1 == anchor_id2:
        weight = 10.0
        condition = "同一anchor"
        return True, weight, condition
    
    # 条件2: 同一 entity + 同一 action（权重 8.0）
    entities1 = set(tweet1.get("entity", []))
    entities2 = set(tweet2.get("entity", []))
    action1 = tweet1.get("action")
    action2 = tweet2.get("action")
    
    if entities1 & entities2 and action1 and action2 and action1 == action2:
        weight = 8.0
        condition = "同一entity+action"
        return True, weight, condition
    
    # 条件3: 同一 entity + 时间接近（权重 6.0）
    if entities1 & entities2:
        time1 = tweet1.get("time", 0)
        time2 = tweet2.get("time", 0)
        if abs(time1 - time2) <= max_time_diff:
            weight = 6.0
            condition = "同一entity+时间接近"
            return True, weight, condition
    
    # 条件4: 不同 KOL + 时间接近 + action 相同（权重 4.0）
    author1 = tweet1.get("author", "")
    author2 = tweet2.get("author", "")
    time1 = tweet1.get("time", 0)
    time2 = tweet2.get("time", 0)
    
    if (author1 and author2 and author1 != author2 and
        abs(time1 - time2) <= max_time_diff and
        action1 and action2 and action1 == action2):
        weight = 4.0
        condition = "不同KOL+时间接近+action相同"
        return True, weight, condition
    
    return False, 0.0, None

def step4_incremental_merge_weighted(
    remaining_candidates: List[dict],
    edges_24h: List[dict],
    output_dir: str = ".",
    min_merge_weight: float = 4.0,
) -> List[dict]:
    """
    Step 4: 增量式事件合并（结构化权重层级）
    合并条件按优先级排序，不是所有条件等权
    """
    print("Step 4: 增量式事件合并（结构化权重层级）...")
    
    topics = []  # 已有主题列表
    
    for tweet in remaining_candidates:
        merged = False
        best_match = None
        best_weight = 0.0
        
        for topic in topics:
            # 检查合并条件（按优先级）
            can_merge, weight, condition = check_merge_conditions_weighted(
                tweet, topic.get("representative", tweet), edges_24h
            )
            
            if can_merge and weight > best_weight:
                best_weight = weight
                best_match = (topic, condition)
        
        # 如果找到匹配且权重足够，合并
        if best_match and best_weight >= min_merge_weight:
            topic, condition = best_match
            topic["event_ids"].append(tweet.get("event_id", ""))
            topic["authors"].append(tweet.get("author", ""))
            topic["entities"].update(tweet.get("entity", []))
            
            # 更新时间范围
            tweet_time = tweet.get("time", 0)
            topic["created_ts_range"][0] = min(topic["created_ts_range"][0], tweet_time)
            topic["created_ts_range"][1] = max(topic["created_ts_range"][1], tweet_time)
            
            # 更新统计
            topic["tweet_count"] = len(topic["event_ids"])
            topic["author_count"] = len(set(topic["authors"]))
            topic["merge_conditions"].append(condition)
            topic["weight"] = max(topic.get("weight", 0.0), best_weight)
            
            merged = True
        
        # 如果没有合并，创建新主题
        if not merged:
            new_topic = {
                "cluster_id": f"topic_{len(topics)}",
                "cluster_type": "incremental",
                "weight": 0.0,
                "event_ids": [tweet.get("event_id", "")],
                "authors": [tweet.get("author", "")],
                "entities": set(tweet.get("entity", [])),
                "action": tweet.get("action"),
                "created_ts_range": [tweet.get("time", 0), tweet.get("time", 0)],
                "representative": tweet,
                "tweet_count": 1,
                "author_count": 1,
                "merge_conditions": []
            }
            topics.append(new_topic)
    
    # 转换 entities 为列表
    for topic in topics:
        topic["entities"] = list(topic["entities"])
    
    # 过滤：只保留 ≥2 条 tweet 的主题
    topics = [t for t in topics if t["tweet_count"] >= 2]
    
    # 保存
    output_path = os.path.join(output_dir, "event_clusters_incremental_v2_new.jsonl")
    save_jsonl(topics, output_path)
    
    print(f"  生成了 {len(topics)} 个增量式主题")
    print(f"  覆盖了 {sum(t['tweet_count'] for t in topics)} 个事件候选")
    print("Step 4: 完成\n")
    
    return topics

# ============================================================================
# Step 5: 受限语义确认（默认关闭）
# ============================================================================

def step5_semantic_confirmation(
    clusters: List[dict],
    use_semantic: bool = False,
    output_dir: str = ".",
) -> List[dict]:
    """
    Step 5: 受限语义确认（默认关闭）
    仅用于人工标记"可能重复"的 topic
    不作为自动合并依据
    """
    if not use_semantic:
        print("Step 5: 受限语义确认（默认关闭，跳过）\n")
        return clusters
    
    print("Step 5: 受限语义确认（仅用于人工标记）...")
    # 这里可以实现语义相似度确认逻辑
    # 但默认关闭，不作为自动合并依据
    print("Step 5: 完成\n")
    
    return clusters

# ============================================================================
# Step 6: 合并所有事件簇并评分
# ============================================================================

def step6_merge_and_score(
    anchor_clusters: List[dict],
    incremental_clusters: List[dict],
    event_candidates_filtered: List[dict],
    edges_24h: List[dict],
    initial_kol_path: Optional[str] = None,
    output_dir: str = ".",
) -> List[dict]:
    """
    Step 6: 合并所有事件簇并评分
    anchor cluster 权重最高
    """
    print("Step 6: 合并所有事件簇并评分...")
    
    # 合并所有簇
    all_clusters = anchor_clusters + incremental_clusters
    
    # 加载 KOL 信息（可选）
    kol_influence_map = {}
    if initial_kol_path and os.path.exists(initial_kol_path):
        try:
            with open(initial_kol_path, "r", encoding="utf-8") as f:
                kol_data = json.load(f)
                for kol in kol_data.get("all", []):
                    username = norm_username(kol.get("username", ""))
                    followers_count = kol.get("followers_count", 0) or 0
                    if username:
                        kol_influence_map[username] = followers_count
        except Exception as e:
            print(f"  Warning: Could not load KOL influence data: {e}")
    
    # 构建候选映射
    candidate_map = {c.get("event_id"): c for c in event_candidates_filtered}
    
    # 为每个簇计算分数
    clusters_with_scores = []
    
    for cluster in all_clusters:
        event_ids = cluster.get("event_ids", [])
        authors = cluster.get("authors", [])
        cluster_weight = cluster.get("weight", 0.0)
        
        # 计算基础指标
        author_cnt = len(set(authors))
        tweet_cnt = len(event_ids)
        
        # 计算 engagement
        total_likes = 0
        total_reposts = 0
        total_replies = 0
        total_quotes = 0
        total_followers = 0
        
        for event_id in event_ids:
            candidate = candidate_map.get(event_id)
            if candidate:
                engagement = candidate.get("engagement", {})
                total_likes += engagement.get("like_count", 0)
                total_reposts += engagement.get("repost_count", 0)
                total_replies += engagement.get("reply_count", 0)
                total_quotes += engagement.get("quote_count", 0)
                
                author = candidate.get("author", "")
                if author in kol_influence_map:
                    total_followers += kol_influence_map[author]
        
        engagement = total_likes + total_reposts * 2 + total_replies * 0.5 + total_quotes * 1.5
        
        # 计算传播强度
        propagation = 0
        for edge in edges_24h:
            source_tweet = edge.get("source_tweet_id", "")
            target_tweet = edge.get("target_tweet_id", "")
            if source_tweet in event_ids and target_tweet in event_ids:
                propagation += 1
        
        # 硬过滤
        if author_cnt < 2:
            continue
        
        # 计算 EventScore（考虑 cluster_weight）
        avg_followers = total_followers / max(author_cnt, 1)
        event_score = (
            1.0 * math.log1p(engagement) +
            3.0 * author_cnt +
            1.5 * math.log1p(propagation) +
            0.5 * math.log1p(tweet_cnt) +
            0.3 * math.log1p(avg_followers) +
            cluster_weight * 0.5  # anchor cluster 权重加成
        )
        
        clusters_with_scores.append({
            "cluster_id": cluster.get("cluster_id", ""),
            "cluster_type": cluster.get("cluster_type", ""),
            "cluster_weight": cluster_weight,
            "event_score": event_score,
            "author_cnt": author_cnt,
            "tweet_cnt": tweet_cnt,
            "propagation": propagation,
            "engagement": engagement,
            "entities": cluster.get("entities", []),
            "action": cluster.get("action"),
            "event_ids": event_ids,
            "authors": list(set(authors)),
            "created_ts_range": cluster.get("created_ts_range", [0, 0])
        })
    
    # 按分数排序
    clusters_with_scores.sort(key=lambda x: x.get("event_score", 0), reverse=True)
    
    # 取 Top5
    top5 = clusters_with_scores[:5]
    
    # 添加排名
    for i, cluster in enumerate(top5, 1):
        cluster["rank"] = i
    
    # 保存
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window": "24h",
        "version": "V2 New (Event-Centric with Human Assets)",
        "top5": top5
    }
    
    output_path = os.path.join(output_dir, "hot_events_top5_v2_new.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"  Top5 事件生成（从 {len(clusters_with_scores)} 个簇中）")
    print("Step 6: 完成\n")
    
    return top5

# ============================================================================
# Step 7: 可解释输出
# ============================================================================

def step7_explainable_output(
    top5_events: List[dict],
    event_candidates_filtered: List[dict],
    output_dir: str = ".",
) -> dict:
    """
    Step 7: 可解释输出
    为每个事件生成可解释的信息
    """
    print("Step 7: 可解释输出...")
    
    candidate_map = {c.get("event_id"): c for c in event_candidates_filtered}
    
    events_readable = []
    
    for event in top5_events:
        cluster_type = event.get("cluster_type", "")
        cluster_weight = event.get("cluster_weight", 0.0)
        entities = event.get("entities", [])
        action = event.get("action", "")
        event_ids = event.get("event_ids", [])
        
        # 生成标题
        if entities:
            title = entities[0]
            if action:
                title = f"{title} {action}"
        else:
            title = f"热点事件 {event.get('rank', 0)}"
        
        # 生成 why_trending
        author_cnt = event.get("author_cnt", 0)
        tweet_cnt = event.get("tweet_cnt", 0)
        propagation = event.get("propagation", 0)
        engagement = event.get("engagement", 0)
        
        why_parts = []
        if author_cnt > 0:
            why_parts.append(f"{author_cnt} 位 KOL")
        if propagation > 0:
            why_parts.append(f"传播链 {propagation} 次")
        if engagement > 0:
            why_parts.append(f"总互动量 {int(engagement)}")
        if tweet_cnt > 0:
            why_parts.append(f"共 {tweet_cnt} 条推文")
        if cluster_weight >= 10.0:
            why_parts.append("传播锚点事件")
        
        why_trending = "；".join(why_parts) if why_parts else "讨论热度较高"
        
        # 生成决策轨迹
        if cluster_type == "anchor":
            decision_trace = {
                "聚类方法": "传播锚点聚类",
                "判断依据": "被多个 KOL 转发/引用的 tweet = 事件锚点，所有指向它的 tweet 自动属于同一事件",
                "权重": f"{cluster_weight:.1f}（最高）",
                "优势": "完全结构化，无语义歧义，天然符合热点定义"
            }
        else:
            decision_trace = {
                "聚类方法": "增量式事件合并（结构化权重层级）",
                "判断依据": "合并条件按优先级排序：同一anchor(10.0) > 同一entity+action(8.0) > 同一entity+时间接近(6.0) > 不同KOL+时间接近+action相同(4.0)",
                "权重": f"{cluster_weight:.1f}",
                "优势": "符合人类认知流程，不依赖 embedding"
            }
        
        # 收集支持推文
        supporting_tweets = []
        for event_id in event_ids[:5]:
            candidate = candidate_map.get(event_id)
            if candidate:
                supporting_tweets.append({
                    "tweet_id": event_id,
                    "author": candidate.get("author", ""),
                    "text": candidate.get("text", "")[:200],
                    "entity": candidate.get("entity", []),
                    "action": candidate.get("action")
                })
        
        events_readable.append({
            "rank": event.get("rank", 0),
            "event_title": title,
            "why_trending": why_trending,
            "key_entities": entities[:5],
            "action": action,
            "supporting_tweets": supporting_tweets,
            "decision_trace": decision_trace,
            "metrics": {
                "author_cnt": author_cnt,
                "tweet_cnt": tweet_cnt,
                "propagation": propagation,
                "engagement": engagement,
                "cluster_weight": cluster_weight
            }
        })
    
    # 保存完整报告
    daily_report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window": "24h",
        "version": "V2 New (Event-Centric with Human Assets)",
        "top5_events": events_readable
    }
    
    output_path = os.path.join(output_dir, "daily_report_v2_new.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(daily_report, f, ensure_ascii=False, indent=2)
    
    # 保存易读版（中文）
    daily_report_readable = {
        "生成时间": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "时间窗口": "24小时",
        "版本": "V2 New (Event-Centric with Human Assets)",
        "Top5 热点事件": [
            {
                "排名": e.get("rank", 0),
                "事件标题": e.get("event_title", ""),
                "为何热门": e.get("why_trending", ""),
                "关键实体": e.get("key_entities", []),
                "动作类型": e.get("action", ""),
                "支持推文数": len(e.get("supporting_tweets", [])),
                "决策轨迹": e.get("decision_trace", {})
            }
            for e in events_readable
        ]
    }
    
    readable_path = os.path.join(output_dir, "daily_report_readable_v2_new.json")
    with open(readable_path, "w", encoding="utf-8") as f:
        json.dump(daily_report_readable, f, ensure_ascii=False, indent=2)
    
    print(f"  生成文件: daily_report_v2_new.json, daily_report_readable_v2_new.json")
    print("Step 7: 完成\n")
    
    return daily_report

# ============================================================================
# 主流程
# ============================================================================

def run_pipeline(
    tweets_24h_clean_path: str = "tweets_24h_clean.jsonl",
    edges_24h_path: str = "edges_24h.jsonl",
    initial_kol_path: Optional[str] = "initial_kol_500.json",
    output_dir: str = ".",
    use_semantic: bool = False,
):
    """运行完整的 V2 New Pipeline"""
    print("=" * 60)
    print("V2 事件级聚类方案 - 最终版（New）")
    print("Event-Centric Clustering with Human Assets")
    print("=" * 60)
    print()
    
    # Step 1: 事件候选生成（受限）
    event_candidates, reference_count = step1_event_candidates_restricted(
        tweets_24h_clean_path,
        edges_24h_path,
        output_dir
    )
    
    # Step 2: 强规则过滤（升级）
    filtered_candidates = step2_hard_rules_filter_upgraded(
        event_candidates,
        output_dir
    )
    
    # Step 3: 传播锚点聚类（权重最高）
    edges_24h = load_jsonl(edges_24h_path)
    anchor_clusters, clustered_event_ids = step3_anchor_clustering(
        filtered_candidates,
        edges_24h,
        reference_count,
        output_dir
    )
    
    # Step 4: 增量式事件合并（结构化权重层级）
    remaining_candidates = [c for c in filtered_candidates if c.get("event_id") not in clustered_event_ids]
    incremental_clusters = step4_incremental_merge_weighted(
        remaining_candidates,
        edges_24h,
        output_dir
    )
    
    # Step 5: 受限语义确认（默认关闭）
    all_clusters = anchor_clusters + incremental_clusters
    confirmed_clusters = step5_semantic_confirmation(
        all_clusters,
        use_semantic=use_semantic,
        output_dir=output_dir
    )
    
    # Step 6: 合并所有事件簇并评分
    top5_events = step6_merge_and_score(
        anchor_clusters,
        incremental_clusters,
        filtered_candidates,
        edges_24h,
        initial_kol_path,
        output_dir
    )
    
    # Step 7: 可解释输出
    daily_report = step7_explainable_output(
        top5_events,
        filtered_candidates,
        output_dir
    )
    
    print("=" * 60)
    print("Pipeline 完成！")
    print("=" * 60)
    print()
    print("主要输出文件:")
    print("  - event_candidates_v2_new.jsonl (Step 1)")
    print("  - event_candidates_filtered_v2_new.jsonl (Step 2)")
    print("  - event_clusters_anchor_v2_new.jsonl (Step 3)")
    print("  - event_clusters_incremental_v2_new.jsonl (Step 4)")
    print("  - hot_events_top5_v2_new.json (Step 6)")
    print("  - daily_report_v2_new.json (Step 7)")
    print("  - daily_report_readable_v2_new.json (Step 7)")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        tweets_path = sys.argv[1]
        edges_path = sys.argv[2] if len(sys.argv) > 2 else "edges_24h.jsonl"
    else:
        tweets_path = "tweets_24h_clean.jsonl"
        edges_path = "edges_24h.jsonl"
    
    run_pipeline(
        tweets_24h_clean_path=tweets_path,
        edges_24h_path=edges_path,
        output_dir="."
    )

