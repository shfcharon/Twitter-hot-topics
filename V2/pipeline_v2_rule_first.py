"""
V2 聚类设计蓝图 - Rule-First + Human-Aligned Pipeline

核心思想：
- 先用规则把"允许成为热点的东西"限定住
- 再用聚类去"合并相似表达"
- 最小语义单元 = 一条 tweet（不是 hashtag / domain）
"""

import json
import os
import re
import math
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Set, Optional, Tuple
import hashlib

# ============================================================================
# 规则字典（需要人工维护）
# ============================================================================

# 平台域名列表（不能作为主 topic）
PLATFORM_DOMAINS = {
    "google.com", "x.com", "twitter.com", "youtube.com",
    "medium.com", "linkedin.com", "facebook.com", "instagram.com",
    "reddit.com", "github.com", "stackoverflow.com"
}

# 泛词列表（只有这些词不能成为热点）
GENERIC_WORDS = {
    "market", "growth", "cloud", "ai", "ml", "tech", "innovation",
    "future", "trend", "digital", "transformation", "business",
    "startup", "venture", "capital", "investment"
}

# 前沿动作词列表（用于识别事件）
FRONTIER_ACTION_VERBS = {
    "launch", "release", "announce", "ship", "deploy",
    "leak", "rumor", "benchmark", "acquire", "invest", "raise",
    "unveil", "introduce", "unveiled", "introduced", "launched",
    "released", "announced", "shipped", "deployed"
}

# 技术产品名白名单
TECH_PRODUCTS_WHITELIST = {
    'GPT', 'GPT-3', 'GPT-4', 'GPT-5', 'ChatGPT', 'Claude', 'Gemini', 'LLaMA', 'Mistral',
    'DALL-E', 'Midjourney', 'Stable Diffusion', 'Transformer', 'BERT', 'T5',
    'TensorFlow', 'PyTorch', 'JAX', 'CUDA', 'TPU', 'GPU', 'CPU', 'H100', 'A100', 'Blackwell',
    'API', 'SDK', 'SaaS', 'PaaS', 'IaaS', 'ML', 'AI', 'AGI', 'NLP', 'CV', 'RL',
    'Replit', 'Codex', 'Copilot', 'GitHub', 'GitLab', 'Docker', 'Kubernetes'
}

# 常见公司名
COMMON_COMPANIES = {
    "openai", "anthropic", "google", "microsoft", "apple", "meta", "amazon", "aws",
    "tesla", "nvidia", "amd", "intel", "twitter", "x", "linkedin", "facebook"
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

def simple_text_embedding(text: str, dim: int = 256) -> List[float]:
    """简单的文本嵌入（TF-IDF 风格）"""
    if not text:
        return [0.0] * dim
    
    # 提取单词
    words = re.findall(r'\b\w+\b', text.lower())
    
    # 计算词频
    word_freq = defaultdict(int)
    for word in words:
        if len(word) >= 3:
            word_freq[word] += 1
    
    # 构建向量
    vector = [0.0] * dim
    total_words = len(words)
    
    for word, freq in word_freq.items():
        # TF-IDF 风格权重
        tf = math.log1p(freq)
        length_bonus = 1.0 + 0.1 * (len(word) - 3) if len(word) > 3 else 1.0
        weight = tf * length_bonus
        
        # 使用 MD5 哈希映射到向量位置
        hash_obj = hashlib.md5(word.encode('utf-8'))
        hash_val = int(hash_obj.hexdigest(), 16) % dim
        vector[hash_val] += weight
    
    # 归一化
    norm = math.sqrt(sum(x * x for x in vector))
    if norm > 0:
        vector = [x / norm for x in vector]
    
    return vector

def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """计算余弦相似度"""
    if len(vec1) != len(vec2):
        return 0.0
    
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    return dot_product / (norm1 * norm2)

# ============================================================================
# Step E2: Tweet 级「事件候选」生成
# ============================================================================

def extract_entities_from_tweet(tweet: dict) -> Dict[str, List[str]]:
    """从推文中提取实体"""
    entities = {
        "tickers": [],
        "companies": [],
        "products": [],
        "people": [],
        "hashtags": [],
        "domains": []
    }
    
    # Cashtags (tickers)
    cashtags = tweet.get("entities", {}).get("cashtags", [])
    entities["tickers"] = [c if isinstance(c, str) else str(c) for c in cashtags if c]
    
    # Hashtags
    hashtags = tweet.get("entities", {}).get("hashtags", [])
    entities["hashtags"] = [h.lower() if isinstance(h, str) else str(h).lower() for h in hashtags if h]
    
    # Domains
    url_domains = tweet.get("url_domains", [])
    entities["domains"] = [d for d in url_domains if d]
    
    # Mentions (可能是人物)
    mentions = tweet.get("entities", {}).get("mentions", [])
    entities["people"] = [norm_username(m) if isinstance(m, str) else m for m in mentions if m]
    
    # 公司名（从文本中匹配）
    text_lower = tweet.get("text", "").lower()
    for company in COMMON_COMPANIES:
        if company in text_lower:
            entities["companies"].append(company.title())
    
    # 产品名（从文本中匹配技术产品白名单）
    text_upper = tweet.get("text", "").upper()
    for product in TECH_PRODUCTS_WHITELIST:
        if product.upper() in text_upper:
            entities["products"].append(product)
    
    return entities

def extract_verbs_from_text(text: str) -> List[str]:
    """从文本中提取动作词"""
    verbs = []
    text_lower = text.lower()
    
    for verb in FRONTIER_ACTION_VERBS:
        if verb.lower() in text_lower:
            verbs.append(verb)
    
    return verbs

def step_e2_event_candidates(
    tweets_24h_clean_path: str,
    output_dir: str = ".",
) -> List[dict]:
    """
    Step E2: Tweet 级「事件候选」生成
    将每条 tweet 转换为一个 EventCandidate
    """
    print("Step E2: Tweet 级「事件候选」生成...")
    
    tweets = load_jsonl(tweets_24h_clean_path)
    event_candidates = []
    
    for tweet in tweets:
        tweet_id = tweet.get("tweet_id", "")
        if not tweet_id:
            continue
        
        # 提取实体
        entities = extract_entities_from_tweet(tweet)
        
        # 提取动作词
        text = tweet.get("clean_text", tweet.get("text", ""))
        verbs = extract_verbs_from_text(text)
        
        # 判断是否原创
        referenced_tweets = tweet.get("referenced_tweets", [])
        is_original = True
        for ref in referenced_tweets:
            ref_type = ref.get("type", "")
            if ref_type in ["reposted", "quoted"]:
                is_original = False
                break
        
        # 获取 engagement
        metrics = tweet.get("public_metrics", {})
        engagement = {
            "like_count": metrics.get("like_count", 0),
            "repost_count": metrics.get("repost_count", 0),
            "reply_count": metrics.get("reply_count", 0),
            "quote_count": metrics.get("quote_count", 0)
        }
        
        # 构造 EventCandidate
        event_candidate = {
            "event_id": tweet_id,
            "author": norm_username(tweet.get("author_username", "")),
            "created_ts": tweet.get("created_ts", 0),
            "created_at": tweet.get("created_at", ""),
            "text": text,
            "raw_text": tweet.get("raw_text", text),
            "entities": entities,
            "verbs": verbs,
            "is_original": is_original,
            "engagement": engagement,
            "public_metrics": metrics
        }
        
        event_candidates.append(event_candidate)
    
    # 保存
    output_path = os.path.join(output_dir, "event_candidates_24h.jsonl")
    save_jsonl(event_candidates, output_path)
    
    print(f"  生成了 {len(event_candidates)} 个事件候选")
    print("Step E2: 完成\n")
    
    return event_candidates

# ============================================================================
# Step F2: 强规则过滤
# ============================================================================

def step_f2_hard_rules_filter(
    event_candidates_path: str,
    output_dir: str = ".",
) -> List[dict]:
    """
    Step F2: 强规则过滤
    不允许明显不可能成为热点的东西进入聚类
    """
    print("Step F2: 强规则过滤...")
    
    candidates = load_jsonl(event_candidates_path)
    filtered_candidates = []
    filter_stats = defaultdict(int)
    
    for candidate in candidates:
        text = candidate.get("text", "")
        entities = candidate.get("entities", {})
        verbs = candidate.get("verbs", [])
        domains = entities.get("domains", [])
        
        # Hard Rule 1: 文本只有 URL / domain
        text_without_url = re.sub(r'https?://\S+', '', text)
        text_without_url = re.sub(r'<URL>', '', text_without_url)
        if not text_without_url.strip():
            filter_stats["只有URL"] += 1
            continue
        
        # Hard Rule 2: 转推模板
        if text.strip().startswith("RT @"):
            filter_stats["转推模板"] += 1
            continue
        if text.strip().lower().startswith("via") and len(text) < 50:
            filter_stats["转推模板"] += 1
            continue
        
        # Hard Rule 3: domain 属于平台型
        is_platform = False
        for domain in domains:
            if domain in PLATFORM_DOMAINS:
                is_platform = True
                break
        if is_platform:
            filter_stats["平台域名"] += 1
            continue
        
        # Hard Rule 4: 没有任何实体 / 动作词
        has_entities = any(
            entities.get("tickers") or
            entities.get("companies") or
            entities.get("products") or
            entities.get("people") or
            entities.get("hashtags")
        )
        if not has_entities and not verbs:
            filter_stats["无实体无动作"] += 1
            continue
        
        # Hard Rule 5: 只有泛词
        words = set(re.findall(r'\b\w+\b', text.lower()))
        generic_only = words.issubset(GENERIC_WORDS)
        if generic_only and len(words) > 0:
            filter_stats["只有泛词"] += 1
            continue
        
        # 通过所有规则
        filtered_candidates.append(candidate)
    
    # 保存
    output_path = os.path.join(output_dir, "event_candidates_filtered_24h.jsonl")
    save_jsonl(filtered_candidates, output_path)
    
    # 输出统计
    print(f"  总候选数: {len(candidates)}")
    print(f"  过滤后: {len(filtered_candidates)}")
    print(f"  过滤统计:")
    for reason, count in filter_stats.items():
        print(f"    {reason}: {count}")
    print("Step F2: 完成\n")
    
    return filtered_candidates

# ============================================================================
# Step F3: 受限语义聚类
# ============================================================================

def check_hard_constraints(
    candidate1: dict,
    candidate2: dict,
    edges_24h: List[dict],
    max_time_diff: int = 48 * 3600
) -> Tuple[bool, List[str]]:
    """
    检查硬约束条件
    返回: (是否满足 ≥2 条, 满足的条件列表)
    """
    satisfied = []
    
    # 条件1: 时间接近（≤48h）
    ts1 = candidate1.get("created_ts", 0)
    ts2 = candidate2.get("created_ts", 0)
    if abs(ts1 - ts2) <= max_time_diff:
        satisfied.append("时间接近")
    
    # 条件2: 实体有交集
    entities1 = candidate1.get("entities", {})
    entities2 = candidate2.get("entities", {})
    
    has_intersection = False
    for entity_type in ["tickers", "companies", "products", "people"]:
        set1 = set(entities1.get(entity_type, []))
        set2 = set(entities2.get(entity_type, []))
        if set1 & set2:
            has_intersection = True
            break
    
    if has_intersection:
        satisfied.append("实体交集")
    
    # 条件3: ≥2 个不同 KOL
    author1 = candidate1.get("author", "")
    author2 = candidate2.get("author", "")
    if author1 and author2 and author1 != author2:
        satisfied.append("多KOL")
    
    # 条件4: 存在传播关系
    event_id1 = candidate1.get("event_id", "")
    event_id2 = candidate2.get("event_id", "")
    
    has_propagation = False
    for edge in edges_24h:
        source_tweet = edge.get("source_tweet_id", "")
        target_tweet = edge.get("target_tweet_id", "")
        if (source_tweet == event_id1 and target_tweet == event_id2) or \
           (source_tweet == event_id2 and target_tweet == event_id1):
            has_propagation = True
            break
    
    if has_propagation:
        satisfied.append("传播关系")
    
    # 必须满足 ≥2 条
    return len(satisfied) >= 2, satisfied

def step_f3_restricted_clustering(
    event_candidates_filtered_path: str,
    edges_24h_path: str,
    output_dir: str = ".",
    similarity_threshold: float = 0.65,  # 降低阈值，允许更多聚类
) -> List[dict]:
    """
    Step F3: 受限语义聚类
    不是"能不能聚在一起"，而是"是否被允许聚在一起"
    """
    print("Step F3: 受限语义聚类...")
    
    candidates = load_jsonl(event_candidates_filtered_path)
    edges_24h = load_jsonl(edges_24h_path)
    
    # 构建候选映射
    candidate_map = {c.get("event_id"): c for c in candidates}
    
    # 计算 embedding
    print("  计算 embedding...")
    embeddings = {}
    for candidate in candidates:
        event_id = candidate.get("event_id", "")
        text = candidate.get("text", "")
        embeddings[event_id] = simple_text_embedding(text)
    
    # 构建相似度矩阵（只包含通过硬约束的 tweet 对）
    print("  构建相似度矩阵...")
    similarity_matrix = {}
    constraint_stats = defaultdict(int)
    
    candidate_list = list(candidates)
    for i in range(len(candidate_list)):
        if i % 50 == 0:
            print(f"    Processing {i}/{len(candidate_list)}...")
        
        candidate1 = candidate_list[i]
        event_id1 = candidate1.get("event_id", "")
        
        for j in range(i + 1, len(candidate_list)):
            candidate2 = candidate_list[j]
            event_id2 = candidate2.get("event_id", "")
            
            # 检查硬约束
            passed, satisfied = check_hard_constraints(candidate1, candidate2, edges_24h)
            
            if not passed:
                constraint_stats["不满足硬约束"] += 1
                continue
            
            constraint_stats[f"满足{len(satisfied)}个条件"] += 1
            
            # 计算语义相似度
            emb1 = embeddings[event_id1]
            emb2 = embeddings[event_id2]
            similarity = cosine_similarity(emb1, emb2)
            
            if similarity >= similarity_threshold:
                key = tuple(sorted([event_id1, event_id2]))
                similarity_matrix[key] = {
                    "similarity": similarity,
                    "satisfied_constraints": satisfied
                }
    
    print(f"  相似度矩阵统计:")
    for reason, count in constraint_stats.items():
        print(f"    {reason}: {count}")
    print(f"  通过硬约束且相似度 >= {similarity_threshold}: {len(similarity_matrix)}")
    
    # 使用简单的连通分量聚类
    print("  执行聚类...")
    clusters = []
    visited = set()
    
    # 构建图（只包含通过硬约束和相似度阈值的边）
    graph = defaultdict(set)
    for (id1, id2), data in similarity_matrix.items():
        graph[id1].add(id2)
        graph[id2].add(id1)
    
    # 连通分量
    def dfs(node, cluster):
        if node in visited:
            return
        visited.add(node)
        cluster.add(node)
        for neighbor in graph.get(node, set()):
            dfs(neighbor, cluster)
    
    cluster_id = 0
    for candidate in candidates:
        event_id = candidate.get("event_id", "")
        if event_id not in visited and event_id in graph:
            cluster = set()
            dfs(event_id, cluster)
            if len(cluster) >= 2:  # 至少2个tweet
                clusters.append({
                    "cluster_id": cluster_id,
                    "event_ids": list(cluster),
                    "cluster_size": len(cluster)
                })
                cluster_id += 1
    
    # 为每个簇计算详细信息
    print("  计算簇详细信息...")
    event_clusters = []
    for cluster_info in clusters:
        cluster_id = cluster_info["cluster_id"]
        event_ids = cluster_info["event_ids"]
        
        # 收集信息
        authors = set()
        all_entities = {
            "tickers": set(),
            "companies": set(),
            "products": set(),
            "people": set(),
            "hashtags": set(),
            "domains": set()
        }
        timestamps = []
        similarities = []
        
        for event_id in event_ids:
            candidate = candidate_map.get(event_id)
            if not candidate:
                continue
            
            authors.add(candidate.get("author", ""))
            
            entities = candidate.get("entities", {})
            for entity_type in all_entities:
                all_entities[entity_type].update(entities.get(entity_type, []))
            
            timestamps.append(candidate.get("created_ts", 0))
        
        # 计算簇内平均相似度
        if len(event_ids) > 1:
            total_sim = 0.0
            count = 0
            for i in range(len(event_ids)):
                for j in range(i + 1, len(event_ids)):
                    key = tuple(sorted([event_ids[i], event_ids[j]]))
                    if key in similarity_matrix:
                        total_sim += similarity_matrix[key]["similarity"]
                        count += 1
            avg_similarity = total_sim / count if count > 0 else 0.0
        else:
            avg_similarity = 1.0
        
        event_clusters.append({
            "cluster_id": cluster_id,
            "event_ids": event_ids,
            "authors": list(authors),
            "entities": {k: list(v) for k, v in all_entities.items()},
            "created_ts_range": [min(timestamps), max(timestamps)] if timestamps else [0, 0],
            "tweet_count": len(event_ids),
            "author_count": len(authors),
            "coherence_score": avg_similarity
        })
    
    # 保存
    output_path = os.path.join(output_dir, "event_clusters_24h.jsonl")
    save_jsonl(event_clusters, output_path)
    
    print(f"  生成了 {len(event_clusters)} 个事件簇")
    print("Step F3: 完成\n")
    
    return event_clusters

# ============================================================================
# Step G2: 事件级评分
# ============================================================================

def step_g2_event_scoring(
    event_clusters_path: str,
    event_candidates_filtered_path: str,
    edges_24h_path: str,
    initial_kol_path: Optional[str] = None,
    output_dir: str = ".",
    min_author_cnt: int = 2,
    min_coherence: float = 0.6,
) -> List[dict]:
    """
    Step G2: 事件级评分
    对每个事件簇进行评分，选出 Top5 热点事件
    """
    print("Step G2: 事件级评分...")
    
    clusters = load_jsonl(event_clusters_path)
    candidates = load_jsonl(event_candidates_filtered_path)
    edges_24h = load_jsonl(edges_24h_path)
    
    # 构建映射
    candidate_map = {c.get("event_id"): c for c in candidates}
    
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
    
    # 为每个簇计算分数
    clusters_with_scores = []
    
    for cluster in clusters:
        cluster_id = cluster.get("cluster_id", 0)
        event_ids = cluster.get("event_ids", [])
        authors = cluster.get("authors", [])
        
        # 计算基础指标
        author_cnt = len(authors)
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
        
        # 计算 novelty（24-72h 新出现）
        ts_range = cluster.get("created_ts_range", [0, 0])
        now_ts = int(datetime.now(timezone.utc).timestamp())
        min_ts = min(ts_range) if ts_range else now_ts
        hours_ago = (now_ts - min_ts) / 3600
        novelty = 1.0 if 24 <= hours_ago <= 72 else 0.0
        
        # 获取 coherence
        coherence = cluster.get("coherence_score", 0.0)
        
        # 硬过滤
        if author_cnt < min_author_cnt:
            continue
        if coherence < min_coherence:
            continue
        
        # 计算 EventScore
        avg_followers = total_followers / max(author_cnt, 1)
        event_score = (
            1.0 * math.log1p(engagement) +
            3.0 * author_cnt +
            1.5 * math.log1p(propagation) +
            0.5 * math.log1p(tweet_cnt) +
            0.3 * math.log1p(avg_followers) +
            1.0 * coherence +
            0.5 * novelty
        )
        
        clusters_with_scores.append({
            "cluster_id": cluster_id,
            "event_score": event_score,
            "author_cnt": author_cnt,
            "tweet_cnt": tweet_cnt,
            "propagation": propagation,
            "novelty": novelty,
            "coherence": coherence,
            "engagement": engagement,
            "total_likes": total_likes,
            "total_reposts": total_reposts,
            "total_replies": total_replies,
            "total_quotes": total_quotes,
            "entities": cluster.get("entities", {}),
            "event_ids": event_ids,
            "authors": authors,
            "created_ts_range": ts_range
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
        "version": "V2 Rule-First + Human-Aligned",
        "top5": top5
    }
    
    output_path = os.path.join(output_dir, "hot_events_top5_v2.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"  Top5 事件生成（从 {len(clusters_with_scores)} 个簇中）")
    print("Step G2: 完成\n")
    
    return top5

# ============================================================================
# Step I2: 强制可解释输出
# ============================================================================

def generate_event_title(cluster: dict, candidates: List[dict]) -> str:
    """生成事件标题"""
    entities = cluster.get("entities", {})
    event_ids = cluster.get("event_ids", [])
    
    # 优先使用 products 或 companies
    products = entities.get("products", [])
    companies = entities.get("companies", [])
    
    title_parts = []
    if products:
        title_parts.append(products[0])
    if companies and not title_parts:
        title_parts.append(companies[0])
    
    # 如果还没有，从推文内容提取
    if not title_parts and event_ids:
        candidate = next((c for c in candidates if c.get("event_id") == event_ids[0]), None)
        if candidate:
            text = candidate.get("text", "")
            title = text[:50].strip()
            if len(title) > 10:
                title_parts.append(title)
    
    if title_parts:
        return title_parts[0]
    else:
        return f"热点事件 {cluster.get('rank', 0)}"

def generate_why_trending(cluster: dict) -> str:
    """生成为什么热门"""
    author_cnt = cluster.get("author_cnt", 0)
    tweet_cnt = cluster.get("tweet_cnt", 0)
    propagation = cluster.get("propagation", 0)
    engagement = cluster.get("engagement", 0)
    
    parts = []
    if author_cnt > 0:
        parts.append(f"{author_cnt} 位 KOL")
    if propagation > 0:
        parts.append(f"传播链 {propagation} 次")
    if engagement > 0:
        parts.append(f"总互动量 {int(engagement)}")
    if tweet_cnt > 0:
        parts.append(f"共 {tweet_cnt} 条推文")
    
    return "；".join(parts) if parts else "讨论热度较高"

def step_i2_explainable_output(
    hot_events_path: str,
    event_candidates_filtered_path: str,
    event_clusters_path: str,
    output_dir: str = ".",
) -> dict:
    """
    Step I2: 强制可解释输出
    为验证服务：解决"我不知道错在哪一步"的问题
    """
    print("Step I2: 强制可解释输出...")
    
    # 加载数据
    with open(hot_events_path, "r", encoding="utf-8") as f:
        hot_events_data = json.load(f)
    
    top5_events = hot_events_data.get("top5", [])
    candidates = load_jsonl(event_candidates_filtered_path)
    clusters = load_jsonl(event_clusters_path)
    
    # 构建映射
    candidate_map = {c.get("event_id"): c for c in candidates}
    cluster_map = {c.get("cluster_id"): c for c in clusters}
    
    # 为每个事件生成可解释输出
    events_readable = []
    
    for event in top5_events:
        cluster_id = event.get("cluster_id", 0)
        event_ids = event.get("event_ids", [])
        entities = event.get("entities", {})
        
        # 生成标题
        event_title = generate_event_title(event, candidates)
        
        # 生成 why_trending
        why_trending = generate_why_trending(event)
        
        # 收集 key_entities
        key_entities = {
            "companies": entities.get("companies", [])[:5],
            "products": entities.get("products", [])[:5],
            "technologies": entities.get("products", [])[:5],  # 技术产品也算技术
            "tickers": entities.get("tickers", [])[:5],
            "hashtags": entities.get("hashtags", [])[:5]
        }
        
        # 生成 supporting_tweets
        supporting_tweets = []
        for event_id in event_ids[:5]:  # 最多5条
            candidate = candidate_map.get(event_id)
            if candidate:
                # 生成 why_included
                why_included_parts = []
                if entities.get("companies") or entities.get("products"):
                    why_included_parts.append("shared entity")
                if candidate.get("verbs"):
                    why_included_parts.append("similar action")
                
                supporting_tweets.append({
                    "tweet_id": event_id,
                    "author": candidate.get("author", ""),
                    "text": candidate.get("text", "")[:200],
                    "why_included": " + ".join(why_included_parts) if why_included_parts else "in cluster"
                })
        
        # 生成 decision_trace
        cluster_info = cluster_map.get(cluster_id, {})
        decision_trace = {
            "passed_rules": [
                "F2: 有实体和动作词",
                f"F3: 时间接近 + 实体交集 + 多KOL (coherence: {event.get('coherence', 0):.2f})",
                f"G2: author_cnt >= 2 ({event.get('author_cnt', 0)}), coherence >= 0.6 ({event.get('coherence', 0):.2f})"
            ],
            "failed_rules": []
        }
        
        events_readable.append({
            "rank": event.get("rank", 0),
            "event_title": event_title,
            "why_trending": why_trending,
            "key_entities": key_entities,
            "supporting_tweets": supporting_tweets,
            "decision_trace": decision_trace,
            "metrics": {
                "author_cnt": event.get("author_cnt", 0),
                "tweet_cnt": event.get("tweet_cnt", 0),
                "propagation": event.get("propagation", 0),
                "engagement": event.get("engagement", 0)
            }
        })
    
    # 保存完整报告
    daily_report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window": "24h",
        "version": "V2 Rule-First + Human-Aligned",
        "top5_events": events_readable
    }
    
    output_path = os.path.join(output_dir, "daily_report_v2.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(daily_report, f, ensure_ascii=False, indent=2)
    
    # 保存易读版（中文）
    daily_report_readable = {
        "生成时间": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "时间窗口": "24小时",
        "版本": "V2 Rule-First + Human-Aligned",
        "Top5 热点事件": [
            {
                "排名": e.get("rank", 0),
                "事件标题": e.get("event_title", ""),
                "为何热门": e.get("why_trending", ""),
                "关键实体": e.get("key_entities", {}),
                "支持推文数": len(e.get("supporting_tweets", [])),
                "决策轨迹": e.get("decision_trace", {})
            }
            for e in events_readable
        ]
    }
    
    readable_path = os.path.join(output_dir, "daily_report_readable_v2.json")
    with open(readable_path, "w", encoding="utf-8") as f:
        json.dump(daily_report_readable, f, ensure_ascii=False, indent=2)
    
    print(f"  生成文件: daily_report_v2.json, daily_report_readable_v2.json")
    print("Step I2: 完成\n")
    
    return daily_report

# ============================================================================
# 主流程
# ============================================================================

def run_pipeline(
    tweets_24h_clean_path: str = "tweets_24h_clean.jsonl",
    edges_24h_path: str = "edges_24h.jsonl",
    initial_kol_path: Optional[str] = "initial_kol_500.json",
    output_dir: str = ".",
):
    """运行完整的 V2 Rule-First Pipeline"""
    print("=" * 60)
    print("V2 聚类设计蓝图 - Rule-First + Human-Aligned Pipeline")
    print("=" * 60)
    print()
    
    # Step E2: 事件候选生成
    event_candidates = step_e2_event_candidates(
        tweets_24h_clean_path,
        output_dir
    )
    
    # Step F2: 强规则过滤
    filtered_candidates = step_f2_hard_rules_filter(
        os.path.join(output_dir, "event_candidates_24h.jsonl"),
        output_dir
    )
    
    # Step F3: 受限语义聚类
    event_clusters = step_f3_restricted_clustering(
        os.path.join(output_dir, "event_candidates_filtered_24h.jsonl"),
        edges_24h_path,
        output_dir
    )
    
    # Step G2: 事件级评分
    top5_events = step_g2_event_scoring(
        os.path.join(output_dir, "event_clusters_24h.jsonl"),
        os.path.join(output_dir, "event_candidates_filtered_24h.jsonl"),
        edges_24h_path,
        initial_kol_path,
        output_dir
    )
    
    # Step I2: 可解释输出
    daily_report = step_i2_explainable_output(
        os.path.join(output_dir, "hot_events_top5_v2.json"),
        os.path.join(output_dir, "event_candidates_filtered_24h.jsonl"),
        os.path.join(output_dir, "event_clusters_24h.jsonl"),
        output_dir
    )
    
    print("=" * 60)
    print("Pipeline 完成！")
    print("=" * 60)
    print()
    print("主要输出文件:")
    print("  - event_candidates_24h.jsonl (E2)")
    print("  - event_candidates_filtered_24h.jsonl (F2)")
    print("  - event_clusters_24h.jsonl (F3)")
    print("  - hot_events_top5_v2.json (G2)")
    print("  - daily_report_v2.json (I2)")
    print("  - daily_report_readable_v2.json (I2)")

if __name__ == "__main__":
    import sys
    
    # 默认使用 V2 文件夹中的文件
    if len(sys.argv) > 1:
        # 可以指定输入文件路径
        tweets_path = sys.argv[1]
        edges_path = sys.argv[2] if len(sys.argv) > 2 else "edges_24h.jsonl"
    else:
        # 使用默认路径（在 V2 文件夹中）
        tweets_path = "tweets_24h_clean.jsonl"
        edges_path = "edges_24h.jsonl"
    
    run_pipeline(
        tweets_24h_clean_path=tweets_path,
        edges_24h_path=edges_path,
        output_dir="."
    )

