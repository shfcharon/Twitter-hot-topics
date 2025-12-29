"""
资本科技热点 Pipeline（Step C - Step I）
从清洗爬虫数据到生成 Daily Report
"""

import json
import re
import math
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Set, Any, Optional
from urllib.parse import urlparse
import os

# ============================================================================
# 资本科技主题关键词（用于主题过滤）
# ============================================================================
CAPITAL_TECH_KEYWORDS = [
    # AI/ML 相关
    "AI", "LLM", "GPT", "AGI", "machine learning", "deep learning", "neural network",
    "transformer", "diffusion", "generative AI", "chatbot", "NLP",
    # 资本/投资相关
    "startup", "VC", "venture capital", "funding", "IPO", "investment", "investor",
    "seed", "series A", "series B", "unicorn", "valuation", "exit",
    # 科技公司/产品
    "OpenAI", "Anthropic", "Google", "Microsoft", "Apple", "Meta", "Amazon",
    "Tesla", "NVIDIA", "AMD", "Intel", "chip", "semiconductor",
    # 加密货币/区块链
    "crypto", "cryptocurrency", "blockchain", "bitcoin", "ethereum", "DeFi",
    "NFT", "Web3", "token", "DAO",
    # 科技趋势
    "innovation", "tech", "technology", "disrupt", "platform", "SaaS",
    "cloud", "edge computing", "quantum", "robotics", "autonomous",
    # 商业/市场
    "market", "ecosystem", "product", "launch", "announcement", "partnership",
    "acquisition", "merger", "revenue", "growth",
]

# 将关键词转为小写用于匹配
CAPITAL_TECH_KEYWORDS_LOWER = [kw.lower() for kw in CAPITAL_TECH_KEYWORDS]


# ============================================================================
# Step C - ETL 清洗与标准化
# ============================================================================

def load_jsonl(path: str) -> List[dict]:
    """加载 JSONL 文件"""
    items = []
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


def save_jsonl(data: List[dict], path: str):
    """保存 JSONL 文件"""
    with open(path, "w", encoding="utf-8") as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def norm_username(username: str) -> str:
    """标准化用户名"""
    if username is None:
        return ""
    return username.lower().lstrip("@").strip()


def is_capital_tech_related(text: str, hashtags: List[str] = None, cashtags: List[str] = None) -> bool:
    """
    判断内容是否与资本科技主题相关
    """
    if not text:
        text = ""
    text_lower = text.lower()
    
    # 检查文本中是否包含关键词
    for keyword in CAPITAL_TECH_KEYWORDS_LOWER:
        if keyword in text_lower:
            return True
    
    # 检查 hashtags
    if hashtags:
        for tag in hashtags:
            tag_lower = tag.lower() if isinstance(tag, str) else str(tag).lower()
            for keyword in CAPITAL_TECH_KEYWORDS_LOWER:
                if keyword in tag_lower or tag_lower in keyword:
                    return True
    
    # cashtags 通常都是资本相关
    if cashtags and len(cashtags) > 0:
        return True
    
    return False


def step_c1_account_validation(
    initial_kol_path: str,
    tweets_14d_path: str,
    tweets_24h_path: str,
    output_dir: str = ".",
) -> tuple[List[dict], List[dict]]:
    """
    C.1 账号全集校验
    只保留 initial_kol_500.all 中的账号推文
    """
    # 加载 KOL 账号列表
    with open(initial_kol_path, "r", encoding="utf-8") as f:
        kol_data = json.load(f)
    
    kol_set = {norm_username(acc.get("username", "")) for acc in kol_data.get("all", [])}
    
    # 保存 KOL 列表（可选）
    kol_list = [{"username": norm_username(acc.get("username", ""))} for acc in kol_data.get("all", [])]
    save_jsonl(kol_list, os.path.join(output_dir, "kol_all_500.jsonl"))
    
    # 过滤 tweets_14d
    tweets_14d = load_jsonl(tweets_14d_path)
    tweets_14d_kol = [
        t for t in tweets_14d
        if norm_username(t.get("author_username", "")) in kol_set
    ]
    save_jsonl(tweets_14d_kol, os.path.join(output_dir, "tweets_14d_kol.jsonl"))
    
    # 过滤 tweets_24h
    tweets_24h = load_jsonl(tweets_24h_path)
    tweets_24h_kol = [
        t for t in tweets_24h
        if norm_username(t.get("author_username", "")) in kol_set
    ]
    save_jsonl(tweets_24h_kol, os.path.join(output_dir, "tweets_24h_kol.jsonl"))
    
    return tweets_14d_kol, tweets_24h_kol


def step_c2_time_standardization(tweets: List[dict], timezone_offset: int = 8) -> List[dict]:
    """
    C.2 时间字段标准化
    添加 created_ts, created_at_local, local_date
    """
    result = []
    tz = timezone(timedelta(hours=timezone_offset))
    
    for tweet in tweets:
        tweet = dict(tweet)  # 复制，不修改原对象
        created_at_str = tweet.get("created_at", "")
        
        try:
            # 解析 ISO-8601 时间
            if created_at_str.endswith("Z"):
                created_at_str = created_at_str[:-1] + "+00:00"
            dt_utc = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            if dt_utc.tzinfo is None:
                dt_utc = dt_utc.replace(tzinfo=timezone.utc)
            
            # created_ts (时间戳)
            tweet["created_ts"] = int(dt_utc.timestamp())
            
            # created_at_local (本地时间 ISO-8601)
            dt_local = dt_utc.astimezone(tz)
            tweet["created_at_local"] = dt_local.isoformat()
            
            # local_date (YYYY-MM-DD)
            tweet["local_date"] = dt_local.strftime("%Y-%m-%d")
            
        except (ValueError, AttributeError) as e:
            # 如果解析失败，设置默认值
            tweet["created_ts"] = 0
            tweet["created_at_local"] = created_at_str
            tweet["local_date"] = ""
        
        result.append(tweet)
    
    return result


def step_c3_text_standardization(tweets: List[dict]) -> List[dict]:
    """
    C.3 文本字段标准化
    添加 raw_text, clean_text
    """
    result = []
    
    for tweet in tweets:
        tweet = dict(tweet)  # 复制
        text = tweet.get("text", "")
        
        # raw_text (保留原文本)
        tweet["raw_text"] = text
        
        # clean_text (标准化处理)
        clean_text = text
        
        # 替换 URLs 为 <URL>
        entities = tweet.get("entities", {})
        urls = entities.get("urls", [])
        for url in urls:
            if isinstance(url, str):
                clean_text = clean_text.replace(url, "<URL>")
            elif isinstance(url, dict) and "url" in url:
                clean_text = clean_text.replace(url["url"], "<URL>")
        
        # 去掉多余空格（连续空格→一个空格）
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        
        tweet["clean_text"] = clean_text
        result.append(tweet)
    
    return result


def extract_domain(url: str) -> Optional[str]:
    """从 URL 中提取域名"""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc
        if domain:
            # 去掉 www. 前缀
            if domain.startswith("www."):
                domain = domain[4:]
            return domain
    except:
        pass
    return None


def step_c4_entities_standardization(tweets: List[dict]) -> List[dict]:
    """
    C.4 entities 标准化
    hashtags 转小写，cashtags 保持，urls 解析 domain，mentions 转小写
    """
    result = []
    
    for tweet in tweets:
        tweet = dict(tweet)  # 复制
        entities = tweet.get("entities", {})
        entities = dict(entities)  # 复制 entities
        
        # hashtags: 全部转小写
        hashtags = entities.get("hashtags", [])
        if isinstance(hashtags, list):
            entities["hashtags"] = [
                tag.lower() if isinstance(tag, str) else tag
                for tag in hashtags
            ]
        
        # cashtags: 保持原样
        # (不需要修改)
        
        # urls: 解析 domain
        urls = entities.get("urls", [])
        url_domains = []
        for url in urls:
            if isinstance(url, str):
                domain = extract_domain(url)
                if domain:
                    url_domains.append(domain)
            elif isinstance(url, dict):
                url_str = url.get("url", "") or url.get("expanded_url", "")
                if url_str:
                    domain = extract_domain(url_str)
                    if domain:
                        url_domains.append(domain)
        
        tweet["url_domains"] = list(set(url_domains))  # 去重
        
        # mentions: 统一小写（不带 @）
        mentions = entities.get("mentions", [])
        if isinstance(mentions, list):
            entities["mentions"] = [
                norm_username(mention) if isinstance(mention, str) else mention
                for mention in mentions
            ]
        
        tweet["entities"] = entities
        result.append(tweet)
    
    return result


def step_c5_deduplication(tweets: List[dict]) -> List[dict]:
    """
    C.5 结构化去重
    按 tweet_id 去重，保留 created_at 更晚或字段更完整的
    """
    tweet_dict: Dict[str, dict] = {}
    
    for tweet in tweets:
        tweet_id = tweet.get("tweet_id", "")
        if not tweet_id:
            continue
        
        if tweet_id not in tweet_dict:
            tweet_dict[tweet_id] = tweet
        else:
            # 比较 created_at，保留更晚的
            existing = tweet_dict[tweet_id]
            try:
                existing_ts = existing.get("created_ts", 0)
                new_ts = tweet.get("created_ts", 0)
                if new_ts > existing_ts:
                    tweet_dict[tweet_id] = tweet
                elif new_ts == existing_ts:
                    # 如果时间相同，保留字段更完整的
                    if len(str(tweet)) > len(str(existing)):
                        tweet_dict[tweet_id] = tweet
            except:
                # 如果比较失败，保留现有的
                pass
    
    return list(tweet_dict.values())


def step_c_etl(
    initial_kol_path: str,
    tweets_14d_path: str,
    tweets_24h_path: str,
    output_dir: str = ".",
    timezone_offset: int = 8,
) -> tuple[List[dict], List[dict]]:
    """
    Step C 完整流程：ETL 清洗与标准化
    """
    print("Step C: ETL 清洗与标准化...")
    
    # C.1 账号全集校验
    print("  C.1 账号全集校验...")
    tweets_14d_kol, tweets_24h_kol = step_c1_account_validation(
        initial_kol_path, tweets_14d_path, tweets_24h_path, output_dir
    )
    print(f"    14d: {len(tweets_14d_kol)} tweets after filtering")
    print(f"    24h: {len(tweets_24h_kol)} tweets after filtering")
    
    # C.2 时间字段标准化
    print("  C.2 时间字段标准化...")
    tweets_14d_kol = step_c2_time_standardization(tweets_14d_kol, timezone_offset)
    tweets_24h_kol = step_c2_time_standardization(tweets_24h_kol, timezone_offset)
    
    # C.3 文本字段标准化
    print("  C.3 文本字段标准化...")
    tweets_14d_kol = step_c3_text_standardization(tweets_14d_kol)
    tweets_24h_kol = step_c3_text_standardization(tweets_24h_kol)
    
    # C.4 entities 标准化
    print("  C.4 entities 标准化...")
    tweets_14d_kol = step_c4_entities_standardization(tweets_14d_kol)
    tweets_24h_kol = step_c4_entities_standardization(tweets_24h_kol)
    
    # C.5 结构化去重
    print("  C.5 结构化去重...")
    tweets_14d_clean = step_c5_deduplication(tweets_14d_kol)
    tweets_24h_clean = step_c5_deduplication(tweets_24h_kol)
    print(f"    14d: {len(tweets_14d_clean)} tweets after deduplication")
    print(f"    24h: {len(tweets_24h_clean)} tweets after deduplication")
    
    # 保存清洗后的数据
    save_jsonl(tweets_14d_clean, os.path.join(output_dir, "tweets_14d_clean.jsonl"))
    save_jsonl(tweets_24h_clean, os.path.join(output_dir, "tweets_24h_clean.jsonl"))
    
    print("Step C: 完成\n")
    return tweets_14d_clean, tweets_24h_clean


# ============================================================================
# Step D - 传播关系派生
# ============================================================================

def step_d_propagation_edges(
    tweets_14d_clean: List[dict],
    tweets_24h_clean: List[dict],
    output_dir: str = ".",
) -> tuple[List[dict], List[dict]]:
    """
    Step D: 构建传播边 edges
    """
    print("Step D: 传播关系派生...")
    
    def build_edges(tweets: List[dict]) -> List[dict]:
        edges = []
        for tweet in tweets:
            tweet_id = tweet.get("tweet_id", "")
            author_username = norm_username(tweet.get("author_username", ""))
            created_at = tweet.get("created_at", "")
            local_date = tweet.get("local_date", "")
            referenced_tweets = tweet.get("referenced_tweets", [])
            
            if not referenced_tweets:
                continue
            
            for ref in referenced_tweets:
                if not isinstance(ref, dict):
                    continue
                
                ref_type = ref.get("type", "")
                target_tweet_id = ref.get("id", "")
                
                # 只考虑 reposted 和 quoted
                if ref_type in ["reposted", "quoted"] and target_tweet_id:
                    edge = {
                        "source_tweet_id": tweet_id,
                        "source_author_username": author_username,
                        "target_tweet_id": target_tweet_id,
                        "edge_type": ref_type,
                        "created_at": created_at,
                        "local_date": local_date,
                    }
                    edges.append(edge)
        
        return edges
    
    edges_14d = build_edges(tweets_14d_clean)
    edges_24h = build_edges(tweets_24h_clean)
    
    save_jsonl(edges_14d, os.path.join(output_dir, "edges_14d.jsonl"))
    save_jsonl(edges_24h, os.path.join(output_dir, "edges_24h.jsonl"))
    
    print(f"  14d edges: {len(edges_14d)}")
    print(f"  24h edges: {len(edges_24h)}")
    print("Step D: 完成\n")
    
    return edges_14d, edges_24h


# ============================================================================
# Step E - 候选主题生成
# ============================================================================

def step_e_topic_candidates(
    tweets_24h_clean: List[dict],
    edges_24h: List[dict],
    output_dir: str = ".",
    filter_capital_tech: bool = True,
) -> List[dict]:
    """
    Step E: 候选主题生成
    添加资本科技主题过滤
    """
    print("Step E: 候选主题生成...")
    
    candidates = []
    filtered_count = 0
    
    # E.1 Hashtag Topic
    for tweet in tweets_24h_clean:
        hashtags = tweet.get("entities", {}).get("hashtags", [])
        text = tweet.get("text", "")
        for hashtag in hashtags:
            if hashtag:
                # 资本科技主题过滤
                if filter_capital_tech:
                    if not is_capital_tech_related(text, hashtags=[hashtag]):
                        filtered_count += 1
                        continue
                
                candidates.append({
                    "topic_type": "hashtag",
                    "topic_key": hashtag.lower() if isinstance(hashtag, str) else str(hashtag).lower(),
                    "tweet_id": tweet.get("tweet_id", ""),
                    "author_username": norm_username(tweet.get("author_username", "")),
                    "created_at": tweet.get("created_at", ""),
                    "local_date": tweet.get("local_date", ""),
                })
    
    # E.2 Cashtag Topic（cashtag 通常都是资本相关，不过滤）
    for tweet in tweets_24h_clean:
        cashtags = tweet.get("entities", {}).get("cashtags", [])
        for cashtag in cashtags:
            if cashtag:
                candidates.append({
                    "topic_type": "cashtag",
                    "topic_key": cashtag if isinstance(cashtag, str) else str(cashtag),
                    "tweet_id": tweet.get("tweet_id", ""),
                    "author_username": norm_username(tweet.get("author_username", "")),
                    "created_at": tweet.get("created_at", ""),
                    "local_date": tweet.get("local_date", ""),
                })
    
    # E.3 Domain Topic
    for tweet in tweets_24h_clean:
        url_domains = tweet.get("url_domains", [])
        text = tweet.get("text", "")
        for domain in url_domains:
            if domain:
                # 资本科技主题过滤
                if filter_capital_tech:
                    if not is_capital_tech_related(text):
                        filtered_count += 1
                        continue
                
                candidates.append({
                    "topic_type": "domain",
                    "topic_key": domain,
                    "tweet_id": tweet.get("tweet_id", ""),
                    "author_username": norm_username(tweet.get("author_username", "")),
                    "created_at": tweet.get("created_at", ""),
                    "local_date": tweet.get("local_date", ""),
                })
    
    # E.4 Center Tweet Topic
    # 统计被引用最多的 target tweet
    target_count = defaultdict(int)
    tweet_map = {t.get("tweet_id", ""): t for t in tweets_24h_clean}
    
    for edge in edges_24h:
        target_tweet_id = edge.get("target_tweet_id", "")
        if target_tweet_id:
            target_count[target_tweet_id] += 1
    
    # 为每个被引用的 tweet 创建候选（需要检查主题相关性）
    for target_tweet_id, count in target_count.items():
        if count > 0:
            # 检查推文内容是否与资本科技相关
            tweet = tweet_map.get(target_tweet_id)
            if filter_capital_tech and tweet:
                text = tweet.get("text", "")
                hashtags = tweet.get("entities", {}).get("hashtags", [])
                cashtags = tweet.get("entities", {}).get("cashtags", [])
                if not is_capital_tech_related(text, hashtags, cashtags):
                    filtered_count += 1
                    continue
            
            candidates.append({
                "topic_type": "center_tweet",
                "topic_key": target_tweet_id,
                "tweet_id": target_tweet_id,
                "author_username": norm_username(tweet.get("author_username", "")) if tweet else "",
                "created_at": tweet.get("created_at", "") if tweet else "",
                "local_date": tweet.get("local_date", "") if tweet else "",
            })
    
    save_jsonl(candidates, os.path.join(output_dir, "topic_candidates_24h.jsonl"))
    print(f"  Total candidates: {len(candidates)}")
    if filter_capital_tech:
        print(f"  Filtered out (non-capital-tech): {filtered_count}")
    print("Step E: 完成\n")
    
    return candidates


# ============================================================================
# Step F - Topic 聚合
# ============================================================================

def step_f_topic_aggregation(
    topic_candidates: List[dict],
    tweets_24h_clean: List[dict],
    edges_24h: List[dict],
    output_dir: str = ".",
) -> List[dict]:
    """
    Step F: Topic 聚合
    修复：center_tweet 的 unique_author_cnt 应该统计转发/引用这条推文的不同 KOL 数量
    """
    print("Step F: Topic 聚合...")
    
    # 构建 tweet_id -> tweet 映射
    tweet_map = {t.get("tweet_id", ""): t for t in tweets_24h_clean}
    
    # 构建 target_tweet_id -> count 映射（用于 ref_cnt）
    target_ref_count = defaultdict(int)
    # 构建 target_tweet_id -> 转发/引用的不同 KOL 集合（用于 center_tweet 的 unique_author_cnt）
    target_ref_authors = defaultdict(set)
    for edge in edges_24h:
        target_tweet_id = edge.get("target_tweet_id", "")
        source_author = norm_username(edge.get("source_author_username", ""))
        if target_tweet_id:
            target_ref_count[target_tweet_id] += 1
            if source_author:
                target_ref_authors[target_tweet_id].add(source_author)
    
    # 按 (topic_type, topic_key) 分组
    topic_groups = defaultdict(lambda: {
        "tweet_ids": set(),
        "author_usernames": set(),
        "sum_like_cnt": 0,
        "sum_repost_cnt": 0,
        "sum_reply_cnt": 0,
        "sum_quote_cnt": 0,
    })
    
    for candidate in topic_candidates:
        topic_type = candidate.get("topic_type", "")
        topic_key = candidate.get("topic_key", "")
        tweet_id = candidate.get("tweet_id", "")
        
        if not topic_type or not topic_key or not tweet_id:
            continue
        
        key = (topic_type, topic_key)
        group = topic_groups[key]
        
        group["tweet_ids"].add(tweet_id)
        author = candidate.get("author_username", "")
        if author:
            group["author_usernames"].add(norm_username(author))
        
        # 从 tweet 中获取 metrics
        tweet = tweet_map.get(tweet_id)
        if tweet:
            metrics = tweet.get("public_metrics", {})
            group["sum_like_cnt"] += metrics.get("like_count", 0)
            group["sum_repost_cnt"] += metrics.get("repost_count", 0)
            group["sum_reply_cnt"] += metrics.get("reply_count", 0)
            group["sum_quote_cnt"] += metrics.get("quote_count", 0)
    
    # 生成聚合结果
    topics = []
    for (topic_type, topic_key), group in topic_groups.items():
        # 计算 ref_cnt（对于 center_tweet，从 edges 统计）
        ref_cnt = 0
        unique_author_cnt = len(group["author_usernames"])
        
        if topic_type == "center_tweet":
            ref_cnt = target_ref_count.get(topic_key, 0)
            # 修复：center_tweet 的 unique_author_cnt 应该是转发/引用这条推文的不同 KOL 数量
            unique_author_cnt = len(target_ref_authors.get(topic_key, set()))
        else:
            # 对于其他类型，统计包含该 topic 的 tweets 被引用的次数
            for tweet_id in group["tweet_ids"]:
                ref_cnt += target_ref_count.get(tweet_id, 0)
        
        topic = {
            "topic_type": topic_type,
            "topic_key": topic_key,
            "window": "24h",
            "tweet_cnt": len(group["tweet_ids"]),
            "unique_author_cnt": unique_author_cnt,
            "sum_like_cnt": group["sum_like_cnt"],
            "sum_repost_cnt": group["sum_repost_cnt"],
            "sum_reply_cnt": group["sum_reply_cnt"],
            "sum_quote_cnt": group["sum_quote_cnt"],
            "ref_cnt": ref_cnt,
        }
        topics.append(topic)
    
    save_jsonl(topics, os.path.join(output_dir, "topics_24h.jsonl"))
    print(f"  Total topics: {len(topics)}")
    print("Step F: 完成\n")
    
    return topics


# ============================================================================
# Step G - 热度评分与 Top5
# ============================================================================

def step_g_hot_score_top5(
    topics: List[dict],
    tweets_24h_clean: List[dict],
    topic_candidates: List[dict],
    initial_kol_path: str = "initial_kol_500.json",
    output_dir: str = ".",
) -> List[dict]:
    """
    Step G: 热度评分与 Top5
    优化后的 HotScore 公式：
    HotScore = 1.0 * log1p(ref_cnt) + 1.0 * log1p(sum_repost_cnt + sum_quote_cnt) 
             + 2.0 * unique_author_cnt + 0.5 * log1p(avg_like_count) 
             + 0.3 * log1p(avg_author_followers)
    添加可读的热点话题标题和描述
    """
    print("Step G: 热度评分与 Top5...")
    
    # 加载 KOL 影响力数据
    kol_influence_map = {}
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
    
    # 构建 tweet_id -> tweet 映射
    tweet_map = {t.get("tweet_id", ""): t for t in tweets_24h_clean}
    
    # 构建 (topic_type, topic_key) -> 相关推文列表的映射
    topic_tweets_map = defaultdict(list)
    for candidate in topic_candidates:
        topic_type = candidate.get("topic_type", "")
        topic_key = candidate.get("topic_key", "")
        tweet_id = candidate.get("tweet_id", "")
        if topic_type and topic_key and tweet_id:
            topic_tweets_map[(topic_type, topic_key)].append(tweet_id)
    
    # 计算 HotScore（优化后的公式，强调多KOL讨论和多推文聚合）
    for topic in topics:
        ref_cnt = topic.get("ref_cnt", 0)
        sum_repost_cnt = topic.get("sum_repost_cnt", 0)
        sum_quote_cnt = topic.get("sum_quote_cnt", 0)
        unique_author_cnt = topic.get("unique_author_cnt", 0)
        tweet_cnt = topic.get("tweet_cnt", 0)
        sum_like_cnt = topic.get("sum_like_cnt", 0)
        topic_type = topic.get("topic_type", "")
        
        # 计算平均点赞数
        avg_like_count = sum_like_cnt / tweet_cnt if tweet_cnt > 0 else 0
        
        # 计算平均 KOL 影响力（followers_count）
        topic_key = topic.get("topic_key", "")
        related_tweet_ids = topic_tweets_map.get((topic_type, topic_key), [])
        
        total_followers = 0
        author_count = 0
        for tweet_id in related_tweet_ids:
            tweet = tweet_map.get(tweet_id)
            if tweet:
                author_username = norm_username(tweet.get("author_username", ""))
                if author_username in kol_influence_map:
                    total_followers += kol_influence_map[author_username]
                    author_count += 1
        
        avg_author_followers = total_followers / author_count if author_count > 0 else 0
        
        # 优化后的 HotScore 公式（强调多KOL讨论和多推文聚合）
        # 对于 center_tweet，大幅降低权重（因为它是单个推文，不是聚合话题）
        if topic_type == "center_tweet":
            # center_tweet 的权重降低，除非有多个 KOL 参与
            center_tweet_penalty = 0.3 if unique_author_cnt < 2 else 0.6
            hot_score = (
                0.5 * math.log1p(ref_cnt) * center_tweet_penalty +
                0.5 * math.log1p(sum_repost_cnt + sum_quote_cnt) * center_tweet_penalty +
                1.5 * unique_author_cnt +  # 仍然重视多KOL参与
                0.3 * math.log1p(avg_like_count) * center_tweet_penalty +
                0.2 * math.log1p(avg_author_followers) * center_tweet_penalty
            )
        else:
            # 对于 hashtag/cashtag/domain，更强调多推文和多KOL
            # 多推文奖励
            multi_tweet_bonus = 1.0 + 0.2 * math.log1p(tweet_cnt - 1) if tweet_cnt > 1 else 1.0
            # 多KOL奖励
            multi_author_bonus = 1.0 + 0.3 * math.log1p(unique_author_cnt - 1) if unique_author_cnt > 1 else 1.0
            
            hot_score = (
                1.0 * math.log1p(ref_cnt) * multi_tweet_bonus +
                1.0 * math.log1p(sum_repost_cnt + sum_quote_cnt) * multi_tweet_bonus +
                3.0 * unique_author_cnt * multi_author_bonus +  # 大幅提高作者多样性权重
                0.5 * math.log1p(avg_like_count) * multi_tweet_bonus +
                0.3 * math.log1p(avg_author_followers) * multi_author_bonus +
                0.5 * math.log1p(tweet_cnt)  # 直接奖励多推文
            )
        
        topic["hot_score"] = hot_score
    
    # 按 HotScore 降序排序
    topics_sorted = sorted(topics, key=lambda x: x.get("hot_score", 0), reverse=True)
    
    # 优先选择多KOL讨论和多推文聚合的话题
    # 过滤条件：至少2个KOL参与 或 至少2条推文（排除单个推文的 center_tweet）
    filtered_topics = []
    for topic in topics_sorted:
        topic_type = topic.get("topic_type", "")
        unique_author_cnt = topic.get("unique_author_cnt", 0)
        tweet_cnt = topic.get("tweet_cnt", 0)
        
        # 优先选择：非 center_tweet 类型，或者 center_tweet 但有多个 KOL 参与
        if topic_type != "center_tweet":
            # hashtag/cashtag/domain 类型，要求至少2个KOL或2条推文
            if unique_author_cnt >= 2 or tweet_cnt >= 2:
                filtered_topics.append(topic)
        else:
            # center_tweet 类型，要求至少2个KOL参与（多个KOL转发/引用）
            if unique_author_cnt >= 2:
                filtered_topics.append(topic)
    
    # 如果过滤后不足5个，补充其他高质量话题
    if len(filtered_topics) < 5:
        remaining = [t for t in topics_sorted if t not in filtered_topics]
        # 优先补充非 center_tweet 类型
        for topic in remaining:
            if topic.get("topic_type") != "center_tweet":
                filtered_topics.append(topic)
                if len(filtered_topics) >= 5:
                    break
        # 如果还不够，补充其他
        if len(filtered_topics) < 5:
            for topic in remaining:
                if topic not in filtered_topics:
                    filtered_topics.append(topic)
                    if len(filtered_topics) >= 5:
                        break
    
    # 取 Top5
    top5 = filtered_topics[:5]
    
    # 为每个 topic 添加可读的标题和描述
    for i, topic in enumerate(top5, 1):
        topic["rank"] = i
        topic_type = topic.get("topic_type", "")
        topic_key = topic.get("topic_key", "")
        
        # 生成可读的标题和描述（强调多KOL讨论和多推文聚合）
        unique_author_cnt = topic.get("unique_author_cnt", 0)
        tweet_cnt = topic.get("tweet_cnt", 0)
        
        if topic_type == "hashtag":
            topic["title"] = f"#{topic_key}"
            if unique_author_cnt >= 2 and tweet_cnt >= 2:
                topic["description"] = f"话题标签 #{topic_key}：{unique_author_cnt} 位 KOL 参与讨论，共 {tweet_cnt} 条推文"
            elif unique_author_cnt >= 2:
                topic["description"] = f"话题标签 #{topic_key}：{unique_author_cnt} 位 KOL 参与讨论"
            elif tweet_cnt >= 2:
                topic["description"] = f"话题标签 #{topic_key}：共 {tweet_cnt} 条推文"
            else:
                topic["description"] = f"话题标签 #{topic_key} 在 KOL 中引发热议"
        elif topic_type == "cashtag":
            # 确保 cashtag 有 $ 符号
            display_key = topic_key if topic_key.startswith("$") else f"${topic_key}"
            topic["title"] = display_key
            if unique_author_cnt >= 2 and tweet_cnt >= 2:
                topic["description"] = f"股票代码 {display_key}：{unique_author_cnt} 位 KOL 参与讨论，共 {tweet_cnt} 条推文"
            elif unique_author_cnt >= 2:
                topic["description"] = f"股票代码 {display_key}：{unique_author_cnt} 位 KOL 关注"
            elif tweet_cnt >= 2:
                topic["description"] = f"股票代码 {display_key}：共 {tweet_cnt} 条推文"
            else:
                topic["description"] = f"股票代码 {display_key} 受到 KOL 关注"
        elif topic_type == "domain":
            topic["title"] = topic_key
            if unique_author_cnt >= 2 and tweet_cnt >= 2:
                topic["description"] = f"域名 {topic_key}：{unique_author_cnt} 位 KOL 分享，共 {tweet_cnt} 条推文"
            elif unique_author_cnt >= 2:
                topic["description"] = f"域名 {topic_key}：{unique_author_cnt} 位 KOL 分享"
            elif tweet_cnt >= 2:
                topic["description"] = f"域名 {topic_key}：共 {tweet_cnt} 条推文被分享"
            else:
                topic["description"] = f"域名 {topic_key} 在 KOL 推文中被频繁分享"
        elif topic_type == "center_tweet":
            # 查找推文信息
            tweet = tweet_map.get(topic_key)
            if tweet:
                author_username = tweet.get("author_username", "")
                text = tweet.get("text", "")
                # 截取前150个字符作为预览
                text_preview = text[:150] + "..." if len(text) > 150 else text
                if unique_author_cnt >= 2:
                    topic["title"] = f"热门推文 (@{author_username}) - {unique_author_cnt} 位 KOL 转发/引用"
                    topic["description"] = f"{text_preview}（被 {unique_author_cnt} 位 KOL 转发/引用）"
                else:
                    topic["title"] = f"热门推文 (@{author_username})"
                    topic["description"] = text_preview
                topic["tweet_author"] = author_username
                topic["tweet_text"] = text
                topic["tweet_url"] = f"https://x.com/{author_username}/status/{topic_key}"
            else:
                if unique_author_cnt >= 2:
                    topic["title"] = f"热门推文 - {unique_author_cnt} 位 KOL 转发/引用"
                    topic["description"] = f"推文 ID: {topic_key[:20]}... 被 {unique_author_cnt} 位 KOL 转发/引用"
                else:
                    topic["title"] = f"热门推文"
                    topic["description"] = f"推文 ID: {topic_key[:20]}... 被大量转发/引用"
        else:
            topic["title"] = topic_key
            topic["description"] = f"{topic_type}: {topic_key}"
        
        # 添加示例推文（取热度最高的几条，展示多推文聚合效果）
        related_tweet_ids = topic_tweets_map.get((topic_type, topic_key), [])
        example_tweets = []
        
        # 按点赞数排序，取前5条（展示多推文聚合）
        tweet_with_metrics = []
        for tweet_id in related_tweet_ids:
            tweet = tweet_map.get(tweet_id)
            if tweet:
                like_count = tweet.get("public_metrics", {}).get("like_count", 0)
                tweet_with_metrics.append((like_count, tweet))
        
        # 按点赞数降序排序
        tweet_with_metrics.sort(key=lambda x: x[0], reverse=True)
        
        # 取前5条作为示例（展示多推文聚合）
        for like_count, tweet in tweet_with_metrics[:5]:
            example_tweets.append({
                "tweet_id": tweet.get("tweet_id", ""),
                "author": tweet.get("author_username", ""),
                "text": tweet.get("text", "")[:200],  # 截取前200字符
                "like_count": like_count,
                "created_at": tweet.get("created_at", ""),
            })
        
        topic["example_tweets"] = example_tweets
        topic["total_related_tweets"] = len(related_tweet_ids)  # 添加总推文数
    
    # 输出 hot_topics_top5.json
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window": "24h",
        "top5": top5,
    }
    
    output_path = os.path.join(output_dir, "hot_topics_top5.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"  Top5 topics generated with readable titles")
    print("Step G: 完成\n")
    
    return top5


# ============================================================================
# Step H - 趋势判断
# ============================================================================

def step_h_trend_analysis(
    tweets_14d_clean: List[dict],
    edges_14d: List[dict],
    topics_24h: List[dict],
    output_dir: str = ".",
) -> List[dict]:
    """
    Step H: 趋势判断（7/14天）
    """
    print("Step H: 趋势判断...")
    
    # H.1 构建 daily time series
    # 按 (topic_type, topic_key, local_date) 分组统计
    daily_stats = defaultdict(lambda: {
        "tweet_cnt": 0,
        "unique_author_cnt": set(),
        "sum_repost_cnt": 0,
        "ref_cnt": 0,
    })
    
    # 构建 target_tweet_id -> count per day 映射
    target_ref_count_daily = defaultdict(lambda: defaultdict(int))
    for edge in edges_14d:
        target_tweet_id = edge.get("target_tweet_id", "")
        local_date = edge.get("local_date", "")
        if target_tweet_id and local_date:
            target_ref_count_daily[target_tweet_id][local_date] += 1
    
    # 从 tweets_14d_clean 中提取 topic 信息
    tweet_map = {t.get("tweet_id", ""): t for t in tweets_14d_clean}
    
    # 处理 hashtags, cashtags, domains
    for tweet in tweets_14d_clean:
        local_date = tweet.get("local_date", "")
        if not local_date:
            continue
        
        author_username = norm_username(tweet.get("author_username", ""))
        tweet_id = tweet.get("tweet_id", "")
        metrics = tweet.get("public_metrics", {})
        
        # Hashtags
        hashtags = tweet.get("entities", {}).get("hashtags", [])
        for hashtag in hashtags:
            if hashtag:
                key = ("hashtag", hashtag.lower() if isinstance(hashtag, str) else str(hashtag).lower(), local_date)
                daily_stats[key]["tweet_cnt"] += 1
                daily_stats[key]["unique_author_cnt"].add(author_username)
                daily_stats[key]["sum_repost_cnt"] += metrics.get("repost_count", 0)
                daily_stats[key]["ref_cnt"] += target_ref_count_daily.get(tweet_id, {}).get(local_date, 0)
        
        # Cashtags
        cashtags = tweet.get("entities", {}).get("cashtags", [])
        for cashtag in cashtags:
            if cashtag:
                key = ("cashtag", cashtag if isinstance(cashtag, str) else str(cashtag), local_date)
                daily_stats[key]["tweet_cnt"] += 1
                daily_stats[key]["unique_author_cnt"].add(author_username)
                daily_stats[key]["sum_repost_cnt"] += metrics.get("repost_count", 0)
                daily_stats[key]["ref_cnt"] += target_ref_count_daily.get(tweet_id, {}).get(local_date, 0)
        
        # Domains
        url_domains = tweet.get("url_domains", [])
        for domain in url_domains:
            if domain:
                key = ("domain", domain, local_date)
                daily_stats[key]["tweet_cnt"] += 1
                daily_stats[key]["unique_author_cnt"].add(author_username)
                daily_stats[key]["sum_repost_cnt"] += metrics.get("repost_count", 0)
                daily_stats[key]["ref_cnt"] += target_ref_count_daily.get(tweet_id, {}).get(local_date, 0)
    
    # 处理 center_tweet
    for edge in edges_14d:
        target_tweet_id = edge.get("target_tweet_id", "")
        local_date = edge.get("local_date", "")
        if target_tweet_id and local_date:
            key = ("center_tweet", target_tweet_id, local_date)
            daily_stats[key]["ref_cnt"] += 1
    
    # 转换为按 topic 聚合的 daily time series
    topic_daily = defaultdict(lambda: defaultdict(lambda: {
        "tweet_cnt": 0,
        "unique_author_cnt": 0,
        "sum_repost_cnt": 0,
        "ref_cnt": 0,
    }))
    
    for (topic_type, topic_key, local_date), stats in daily_stats.items():
        topic_daily[(topic_type, topic_key)][local_date] = {
            "tweet_cnt": stats["tweet_cnt"],
            "unique_author_cnt": len(stats["unique_author_cnt"]),
            "sum_repost_cnt": stats["sum_repost_cnt"],
            "ref_cnt": stats["ref_cnt"],
        }
    
    # H.2 趋势标签
    trends = []
    
    # 获取所有日期并排序
    all_dates = set()
    for stats_dict in topic_daily.values():
        all_dates.update(stats_dict.keys())
    all_dates = sorted(all_dates)
    
    if len(all_dates) < 2:
        print("  Not enough dates for trend analysis")
        print("Step H: 完成\n")
        return []
    
    # 最近一天
    today = all_dates[-1]
    # 前7天（不包括今天）
    date_7d_ago = all_dates[-8] if len(all_dates) >= 8 else all_dates[0]
    
    # 只分析 topics_24h 中的 topic
    topics_24h_keys = {(t.get("topic_type", ""), t.get("topic_key", "")) for t in topics_24h}
    
    for (topic_type, topic_key) in topics_24h_keys:
        daily_data = topic_daily.get((topic_type, topic_key), {})
        
        # 计算 today 的值
        today_data = daily_data.get(today, {})
        today_value = today_data.get("unique_author_cnt", 0)  # 使用 unique_author_cnt 作为主要指标
        
        # 计算前7天均值
        avg_7d = 0.0
        count_7d = 0
        for date in all_dates:
            if date < today and date >= date_7d_ago:
                count_7d += 1
                avg_7d += daily_data.get(date, {}).get("unique_author_cnt", 0)
        if count_7d > 0:
            avg_7d = avg_7d / count_7d
        
        # 应用趋势规则（优化：降低阈值，使用多个指标）
        trend_label = None
        tweet_cnt_today = today_data.get("tweet_cnt", 0)
        unique_author_cnt_today = today_data.get("unique_author_cnt", 0)
        ref_cnt_today = today_data.get("ref_cnt", 0)
        
        # 使用综合指标：unique_author_cnt 或 tweet_cnt
        # 降低阈值：unique_author_cnt >= 1 或 tweet_cnt >= 2
        if unique_author_cnt_today >= 1 or tweet_cnt_today >= 2:
            if today_value > 0 and avg_7d == 0:
                trend_label = "Emerging"
            elif today_value >= 1.5 * avg_7d and (today_value >= 2 or tweet_cnt_today >= 2):
                trend_label = "Rising"
            elif today_value >= 3 or tweet_cnt_today >= 5:
                # 检查是否是过去7天最大值
                past_7d_values = [
                    daily_data.get(date, {}).get("unique_author_cnt", 0)
                    for date in all_dates
                    if date < today and date >= date_7d_ago
                ]
                past_7d_tweet_cnt = [
                    daily_data.get(date, {}).get("tweet_cnt", 0)
                    for date in all_dates
                    if date < today and date >= date_7d_ago
                ]
                if (past_7d_values and today_value >= max(past_7d_values + [today_value])) or \
                   (past_7d_tweet_cnt and tweet_cnt_today >= max(past_7d_tweet_cnt + [tweet_cnt_today])):
                    trend_label = "Peak"
            elif today_value <= 0.5 * avg_7d and avg_7d > 0:
                trend_label = "Fading"
            elif 0.8 * avg_7d <= today_value <= 1.2 * avg_7d and (avg_7d >= 2 or tweet_cnt_today >= 3):
                trend_label = "Persistent"
        
        if trend_label:
            trends.append({
                "topic_type": topic_type,
                "topic_key": topic_key,
                "trend_label": trend_label,
                "today_value": today_value,
                "avg_7d": avg_7d,
            })
    
    save_jsonl(trends, os.path.join(output_dir, "trends_14d.jsonl"))
    print(f"  Total trends: {len(trends)}")
    print("Step H: 完成\n")
    
    return trends


# ============================================================================
# Step I - Daily Report 输出
# ============================================================================

def step_i_daily_report(
    hot_topics_top5: List[dict],
    trends_14d: List[dict],
    output_dir: str = ".",
) -> dict:
    """
    Step I: Daily Report 输出
    生成易读的热点话题日报
    """
    print("Step I: Daily Report 输出...")
    
    # 构建 topic_key -> trend 映射
    trend_map = {
        (t.get("topic_type", ""), t.get("topic_key", "")): t
        for t in trends_14d
    }
    
    # 为每个 top5 topic 添加趋势标签，并生成易读格式
    top5_readable = []
    for topic in hot_topics_top5:
        topic_type = topic.get("topic_type", "")
        topic_key = topic.get("topic_key", "")
        trend = trend_map.get((topic_type, topic_key))
        
        # 构建易读的热点信息
        hot_topic = {
            "rank": topic.get("rank", 0),
            "title": topic.get("title", topic_key),
            "description": topic.get("description", ""),
            "type": topic_type,
            "hot_score": round(topic.get("hot_score", 0), 2),
            "metrics": {
                "tweet_count": topic.get("tweet_cnt", 0),
                "author_count": topic.get("unique_author_cnt", 0),
                "total_likes": topic.get("sum_like_cnt", 0),
                "total_reposts": topic.get("sum_repost_cnt", 0),
                "total_replies": topic.get("sum_reply_cnt", 0),
                "total_quotes": topic.get("sum_quote_cnt", 0),
                "reference_count": topic.get("ref_cnt", 0),
            },
            "trend": {
                "label": trend.get("trend_label", "") if trend else None,
                "today_value": trend.get("today_value", 0) if trend else 0,
                "avg_7d": round(trend.get("avg_7d", 0.0), 2) if trend else 0.0,
            },
            "example_tweets": topic.get("example_tweets", []),
        }
        
        # 如果是 center_tweet，添加推文链接
        if topic_type == "center_tweet" and topic.get("tweet_url"):
            hot_topic["tweet_url"] = topic.get("tweet_url")
            hot_topic["tweet_author"] = topic.get("tweet_author", "")
        
        top5_readable.append(hot_topic)
    
    # 生成 daily_report.json（易读格式）
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window": "24h",
        "summary": {
            "total_topics_analyzed": len(trends_14d) if trends_14d else 0,
            "top5_hot_topics": [
                {
                    "rank": t["rank"],
                    "title": t["title"],
                    "description": t["description"],
                    "hot_score": t["hot_score"],
                }
                for t in top5_readable
            ],
        },
        "top5_hot_topics": top5_readable,  # 完整信息
        "trends_summary": {
            "total_trends": len(trends_14d),
            "trends_by_label": {}
        },
        "manual_labeling": [],  # 人工标注记录（待填充）
    }
    
    # 统计趋势标签分布
    for trend in trends_14d:
        label = trend.get("trend_label", "")
        if label:
            report["trends_summary"]["trends_by_label"][label] = \
                report["trends_summary"]["trends_by_label"].get(label, 0) + 1
    
    output_path = os.path.join(output_dir, "daily_report.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    # 同时生成一个更简洁的易读版本（中文）
    readable_report = {
        "生成时间": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "时间窗口": "24小时",
        "Top5 热点话题": [
            {
                "排名": t["rank"],
                "话题": t["title"],
                "描述": t["description"],
                "热度分数": t["hot_score"],
                "推文数": t["metrics"]["tweet_count"],
                "参与作者数": t["metrics"]["author_count"],
                "总点赞数": t["metrics"]["total_likes"],
                "总转发数": t["metrics"]["total_reposts"],
                "趋势": t["trend"]["label"] if t["trend"]["label"] else "无趋势数据",
            }
            for t in top5_readable
        ],
    }
    
    readable_path = os.path.join(output_dir, "daily_report_readable.json")
    with open(readable_path, "w", encoding="utf-8") as f:
        json.dump(readable_report, f, ensure_ascii=False, indent=2)
    
    print("Step I: 完成")
    print(f"  生成文件: daily_report.json, daily_report_readable.json\n")
    
    return report


# ============================================================================
# Main Pipeline
# ============================================================================

def run_pipeline(
    initial_kol_path: str = "initial_kol_500.json",
    tweets_14d_path: str = "tweets_14d.jsonl",
    tweets_24h_path: str = "tweets_24h.jsonl",
    output_dir: str = ".",
    timezone_offset: int = 8,
):
    """
    运行完整的 Pipeline（Step C - Step I）
    """
    print("=" * 60)
    print("资本科技热点 Pipeline")
    print("=" * 60)
    print()
    
    # Step C: ETL 清洗与标准化
    tweets_14d_clean, tweets_24h_clean = step_c_etl(
        initial_kol_path, tweets_14d_path, tweets_24h_path, output_dir, timezone_offset
    )
    
    # Step D: 传播关系派生
    edges_14d, edges_24h = step_d_propagation_edges(
        tweets_14d_clean, tweets_24h_clean, output_dir
    )
    
    # Step E: 候选主题生成
    topic_candidates = step_e_topic_candidates(
        tweets_24h_clean, edges_24h, output_dir, filter_capital_tech=True
    )
    
    # Step F: Topic 聚合
    topics_24h = step_f_topic_aggregation(
        topic_candidates, tweets_24h_clean, edges_24h, output_dir
    )
    
    # Step G: 热度评分与 Top5
    hot_topics_top5 = step_g_hot_score_top5(
        topics_24h, tweets_24h_clean, topic_candidates, initial_kol_path, output_dir
    )
    
    # Step H: 趋势判断
    trends_14d = step_h_trend_analysis(
        tweets_14d_clean, edges_14d, topics_24h, output_dir
    )
    
    # Step I: Daily Report 输出
    daily_report = step_i_daily_report(hot_topics_top5, trends_14d, output_dir)
    
    print("=" * 60)
    print("Pipeline 完成！")
    print("=" * 60)
    print(f"\n输出文件目录: {output_dir}")
    print("\n主要输出文件:")
    print("  - tweets_14d_clean.jsonl")
    print("  - tweets_24h_clean.jsonl")
    print("  - edges_14d.jsonl")
    print("  - edges_24h.jsonl")
    print("  - topic_candidates_24h.jsonl")
    print("  - topics_24h.jsonl")
    print("  - hot_topics_top5.json")
    print("  - trends_14d.jsonl")
    print("  - daily_report.json")


if __name__ == "__main__":
    run_pipeline()

