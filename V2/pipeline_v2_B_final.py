"""
资本科技热点 Pipeline V2-B Improved（讨论图谱 + 社区发现版本 - 改进版）
基于 V2-B 的改进版本，实现以下优化：

改进内容：
1. 改进实体提取：
   - 扩展实体类型（产品名、技术名、事件类型等）
   - 从推文内容中提取关键词作为产品/技术名

2. 改进标题生成：
   - 当没有中心实体时，从推文内容提取关键词生成标题
   - 使用推文中的关键词和短语生成更清晰的标题

3. 改进中心节点识别：
   - 改进中心度计算，考虑更多因素（度、连接权重、在社区中的重要性）
   - 考虑节点的 PageRank 风格重要性

核心思想：
构建一个多层图（Heterogeneous Graph），让聚类天然偏向"讨论共同体"，而不是符号。

节点（Nodes）：
- Tweet
- Author（KOL）
- Entity（公司/产品/技术名/人名/ticker/hashtag/domain/关键短语）

边（Edges）：
- Tweet—Tweet：embedding 相似度 > 阈值
- Author—Tweet：发帖关系
- Tweet—Entity：提及关系
- Author—Author：传播关系（repost/quote）
- Entity—Entity：共现关系（同簇高频共现）

社区发现（Community Detection）：
- 使用简化的 Louvain 算法
- 输出社区 = 议题 cluster
- 社区的"议题标题"来自：社区内最中心的实体节点 + 最中心的 tweet + 推文关键词
"""

import json
import re
import math
import hashlib
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Set, Any, Optional, Tuple
from urllib.parse import urlparse
import os
import numpy as np

# 尝试导入可选的依赖
try:
    from sklearn.cluster import AgglomerativeClustering
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    print("Warning: sklearn not available, clustering will use fallback method")

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("Warning: openai not available, will use fallback embedding method")

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

CAPITAL_TECH_KEYWORDS_LOWER = [kw.lower() for kw in CAPITAL_TECH_KEYWORDS]

# ============================================================================
# 基础工具函数（从 V2 复制）
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
    """判断内容是否与资本科技主题相关"""
    if not text:
        text = ""
    text_lower = text.lower()
    
    for keyword in CAPITAL_TECH_KEYWORDS_LOWER:
        if keyword in text_lower:
            return True
    
    if hashtags:
        for tag in hashtags:
            tag_lower = tag.lower() if isinstance(tag, str) else str(tag).lower()
            for keyword in CAPITAL_TECH_KEYWORDS_LOWER:
                if keyword in tag_lower or tag_lower in keyword:
                    return True
    
    if cashtags and len(cashtags) > 0:
        return True
    
    return False


def extract_domain(url: str) -> Optional[str]:
    """从 URL 中提取域名"""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc
        if domain:
            if domain.startswith("www."):
                domain = domain[4:]
            return domain
    except:
        pass
    return None


def simple_text_embedding(text: str) -> List[float]:
    """稳定的文本嵌入（使用 hashlib.md5）"""
    words = re.findall(r'\b\w+\b', text.lower())
    
    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by',
                  'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did',
                  'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can', 'this', 'that',
                  'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'rt', 'https', 'http',
                  'www', 'com', 'co', 'uk', 'org', 'net', 'io', 'ai', 'me', 'us'}
    
    word_freq = defaultdict(int)
    for word in words:
        if len(word) > 2 and word not in stop_words:
            word_freq[word] += 1
    
    weighted_words = []
    for word, freq in word_freq.items():
        tf = math.log1p(freq)
        length_bonus = 1.0 + 0.1 * (len(word) - 3) if len(word) > 3 else 1.0
        weighted_words.append((word, tf * length_bonus))
    
    weighted_words.sort(key=lambda x: x[1], reverse=True)
    weighted_words = weighted_words[:256]
    
    vector = [0.0] * 256
    for word, weight in weighted_words:
        hash_obj = hashlib.md5(word.encode('utf-8'))
        hash_val = int(hash_obj.hexdigest(), 16) % 256
        vector[hash_val] += weight
    
    norm = math.sqrt(sum(x*x for x in vector))
    if norm > 0:
        vector = [x / norm for x in vector]
    else:
        vector = [0.0] * 256
    
    return vector


def get_embedding(text: str, use_openai: bool = False, openai_api_key: Optional[str] = None) -> Optional[List[float]]:
    """获取文本嵌入"""
    if use_openai and OPENAI_AVAILABLE and openai_api_key:
        try:
            response = openai.embeddings.create(
                model="text-embedding-3-small",
                input=text[:8000]
            )
            return response.data[0].embedding
        except Exception as e:
            print(f"  Warning: OpenAI embedding failed: {e}, using fallback")
    
    return simple_text_embedding(text)


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
# Step C/D: ETL 和传播关系（复用 V2 的逻辑，简化版）
# ============================================================================

def step_c_etl_simplified(
    initial_kol_path: str,
    tweets_14d_path: str,
    tweets_24h_path: str,
    output_dir: str = ".",
    timezone_offset: int = 8,
) -> tuple[List[dict], List[dict]]:
    """Step C: ETL 清洗与标准化（简化版）"""
    print("Step C: ETL 清洗与标准化...")
    
    # 加载 KOL 账号列表
    with open(initial_kol_path, "r", encoding="utf-8") as f:
        kol_data = json.load(f)
    kol_set = {norm_username(acc.get("username", "")) for acc in kol_data.get("all", [])}
    
    # 加载并过滤推文
    tweets_14d = load_jsonl(tweets_14d_path)
    tweets_24h = load_jsonl(tweets_24h_path)
    
    tweets_14d_kol = [t for t in tweets_14d if norm_username(t.get("author_username", "")) in kol_set]
    tweets_24h_kol = [t for t in tweets_24h if norm_username(t.get("author_username", "")) in kol_set]
    
    # 时间标准化
    tz = timezone(timedelta(hours=timezone_offset))
    for tweets in [tweets_14d_kol, tweets_24h_kol]:
        for tweet in tweets:
            created_at_str = tweet.get("created_at", "")
            try:
                if created_at_str.endswith("Z"):
                    created_at_str = created_at_str[:-1] + "+00:00"
                dt_utc = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                if dt_utc.tzinfo is None:
                    dt_utc = dt_utc.replace(tzinfo=timezone.utc)
                tweet["created_ts"] = int(dt_utc.timestamp())
                dt_local = dt_utc.astimezone(tz)
                tweet["created_at_local"] = dt_local.isoformat()
                tweet["local_date"] = dt_local.strftime("%Y-%m-%d")
            except:
                tweet["created_ts"] = 0
                tweet["created_at_local"] = created_at_str
                tweet["local_date"] = ""
    
    # 文本标准化
    for tweets in [tweets_14d_kol, tweets_24h_kol]:
        for tweet in tweets:
            text = tweet.get("text", "")
            tweet["raw_text"] = text
            clean_text = text
            entities = tweet.get("entities", {})
            urls = entities.get("urls", [])
            for url in urls:
                if isinstance(url, str):
                    clean_text = clean_text.replace(url, "<URL>")
                elif isinstance(url, dict) and "url" in url:
                    clean_text = clean_text.replace(url["url"], "<URL>")
            clean_text = re.sub(r'\s+', ' ', clean_text).strip()
            tweet["clean_text"] = clean_text
    
    # Entities 标准化
    for tweets in [tweets_14d_kol, tweets_24h_kol]:
        for tweet in tweets:
            entities = tweet.get("entities", {})
            hashtags = entities.get("hashtags", [])
            if isinstance(hashtags, list):
                entities["hashtags"] = [tag.lower() if isinstance(tag, str) else tag for tag in hashtags]
            
            url_domains = []
            urls = entities.get("urls", [])
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
            tweet["url_domains"] = list(set(url_domains))
            
            mentions = entities.get("mentions", [])
            if isinstance(mentions, list):
                entities["mentions"] = [norm_username(m) if isinstance(m, str) else m for m in mentions]
            tweet["entities"] = entities
    
    # 去重
    tweet_dict_14d = {}
    tweet_dict_24h = {}
    for tweet in tweets_14d_kol:
        tweet_id = tweet.get("tweet_id", "")
        if tweet_id:
            if tweet_id not in tweet_dict_14d:
                tweet_dict_14d[tweet_id] = tweet
            else:
                if tweet.get("created_ts", 0) > tweet_dict_14d[tweet_id].get("created_ts", 0):
                    tweet_dict_14d[tweet_id] = tweet
    
    for tweet in tweets_24h_kol:
        tweet_id = tweet.get("tweet_id", "")
        if tweet_id:
            if tweet_id not in tweet_dict_24h:
                tweet_dict_24h[tweet_id] = tweet
            else:
                if tweet.get("created_ts", 0) > tweet_dict_24h[tweet_id].get("created_ts", 0):
                    tweet_dict_24h[tweet_id] = tweet
    
    tweets_14d_clean = list(tweet_dict_14d.values())
    tweets_24h_clean = list(tweet_dict_24h.values())
    
    save_jsonl(tweets_14d_clean, os.path.join(output_dir, "tweets_14d_clean_v2B_final.jsonl"))
    save_jsonl(tweets_24h_clean, os.path.join(output_dir, "tweets_24h_clean_v2B_final.jsonl"))
    
    print(f"  14d: {len(tweets_14d_clean)} tweets")
    print(f"  24h: {len(tweets_24h_clean)} tweets")
    print("Step C: 完成\n")
    
    return tweets_14d_clean, tweets_24h_clean


def step_d_propagation_edges_simplified(
    tweets_14d_clean: List[dict],
    tweets_24h_clean: List[dict],
    output_dir: str = ".",
) -> tuple[List[dict], List[dict]]:
    """Step D: 构建传播边 edges（简化版）"""
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
                
                if ref_type in ["reposted", "quoted"] and target_tweet_id:
                    edges.append({
                        "source_tweet_id": tweet_id,
                        "source_author_username": author_username,
                        "target_tweet_id": target_tweet_id,
                        "edge_type": ref_type,
                        "created_at": created_at,
                        "local_date": local_date,
                    })
        return edges
    
    edges_14d = build_edges(tweets_14d_clean)
    edges_24h = build_edges(tweets_24h_clean)
    
    save_jsonl(edges_14d, os.path.join(output_dir, "edges_14d_v2B_final.jsonl"))
    save_jsonl(edges_24h, os.path.join(output_dir, "edges_24h_v2B_final.jsonl"))
    
    print(f"  14d edges: {len(edges_14d)}")
    print(f"  24h edges: {len(edges_24h)}")
    print("Step D: 完成\n")
    
    return edges_14d, edges_24h


# ============================================================================
# Step E: 构建多层图（Heterogeneous Graph）
# ============================================================================

# 技术产品名白名单（最终版：更严格）
TECH_PRODUCTS_WHITELIST = {
    # AI/ML 模型
    'GPT', 'GPT-3', 'GPT-4', 'GPT-5', 'ChatGPT', 'Claude', 'Gemini', 'LLaMA', 'Mistral', 'PaLM', 'LaMDA',
    'DALL-E', 'Midjourney', 'Stable Diffusion', 'Transformer', 'BERT', 'T5', 'RoBERTa', 'BART',
    # 框架/工具
    'TensorFlow', 'PyTorch', 'JAX', 'Keras', 'Scikit-learn', 'HuggingFace', 'LangChain', 'LlamaIndex',
    # 硬件
    'CUDA', 'TPU', 'GPU', 'CPU', 'H100', 'A100', 'Blackwell', 'Hopper', 'Grace', 'Grace Hopper',
    # 服务/平台
    'API', 'SDK', 'SaaS', 'PaaS', 'IaaS', 'AWS', 'GCP', 'Azure', 'OpenAI', 'Anthropic',
    # 技术术语
    'ML', 'AI', 'AGI', 'NLP', 'CV', 'RL', 'LLM', 'RAG', 'Fine-tuning', 'Prompt Engineering',
    # 产品/服务
    'Replit', 'Codex', 'Copilot', 'GitHub', 'GitLab', 'Docker', 'Kubernetes', 'Terraform',
}

# 常见地名（需要过滤）
COMMON_PLACES = {
    'France', 'Germany', 'Italy', 'Spain', 'England', 'Switzerland', 'Austria', 'Portugal',
    'Thailand', 'Indonesia', 'India', 'China', 'Japan', 'Brazil', 'Argentina', 'Colombia',
    'Montenegro', 'Latvia', 'Greece', 'Turkey', 'Panama', 'Mauritius', 'Bali', 'Phuket',
    'Istanbul', 'Florence', 'World', 'United', 'Kingdom', 'Arabia', 'Saudi', 'Vietnam',
}

# 常见人名（需要过滤）
COMMON_NAMES = {
    'James', 'John', 'Robert', 'Michael', 'William', 'David', 'Richard', 'Joseph', 'Thomas', 'Charles',
    'Charlie', 'Carlos', 'Abigail', 'Taryn', 'Sami', 'Felice', 'Newitz', 'Annalee', 'Beall', 'Munger',
    'Zheng', 'Bingzhang', 'Frankel', 'Kevin', 'Raising',
}

# 普通词（需要过滤）
COMMON_WORDS = {
    'Scientists', 'Empire', 'Phenomenal', 'University', 'Flex', 'Research', 'Association', 'Excavations',
    'Subscriptions', 'Cryptologic', 'Palace', 'Killer', 'Webb', 'Baby', 'Though', 'Moments', 'Biologists',
    'Hyper', 'Changes', 'Feedback', 'Postal', 'There', 'Controlling', 'Ottoman', 'Biosciences', 'Roman',
    'Space', 'Tiger', 'Everything', 'Known', 'Colossal', 'Scientist', 'German', 'International', 'Ghana',
    'Genoa', 'Doctor', 'Earth', 'Teen', 'Colombia', 'Netherlands', 'Service', 'Using', 'Learn', 'Build',
    'Easily', 'Lynx', 'Iberian', 'White', 'Rapid', 'Topkapi', 'Switzerland', 'England', 'France',
    'Indonesia', 'Bali', 'Mauritius', 'Italy', 'Island', 'Austria', 'Montenegro', 'United', 'India',
    'Arabia', 'Kingdom', 'Florence', 'Greece', 'Vietnam', 'Portugal', 'Saudi', 'Phuket', 'Turkey',
    'Panama', 'Latvia', 'Brazil',
}


def extract_keywords_from_text_final(text: str, min_length: int = 4) -> List[str]:
    """从推文文本中提取关键词（最终改进版：更严格的过滤）"""
    if not text:
        return []
    
    keywords = []
    text_upper = text.upper()
    
    # 1. 优先提取技术产品名白名单中的词
    for product in TECH_PRODUCTS_WHITELIST:
        if product.upper() in text_upper:
            keywords.append(product)
    
    # 2. 提取大写开头的词或全大写词（但需要严格过滤）
    words = re.findall(r'\b[A-Z][a-z]+\b|\b[A-Z]{2,}\b', text)
    
    # 停用词列表（扩展）
    stop_words = {
        'RT', 'The', 'This', 'That', 'These', 'Those', 'When', 'Where', 'What', 'Who', 'How', 'Why',
        'From', 'With', 'About', 'After', 'Before', 'During', 'Through', 'Under', 'Over',
        'Some', 'Many', 'Most', 'More', 'Much', 'Very', 'Really', 'Just', 'Only', 'Also', 'Still', 'Even',
        'They', 'There', 'Their', 'Them', 'These', 'Those', 'Here', 'There', 'Where', 'When',
    }
    
    for word in words:
        if len(word) < min_length:
            continue
        if word in stop_words:
            continue
        if word in keywords:
            continue
        
        # 过滤掉地名
        if word in COMMON_PLACES:
            continue
        
        # 过滤掉人名
        if word in COMMON_NAMES:
            continue
        
        # 过滤掉普通词
        if word in COMMON_WORDS:
            continue
        
        # 只保留包含技术术语的词或已知的技术产品名
        word_upper = word.upper()
        is_tech_related = False
        
        # 检查是否包含技术术语
        tech_terms = ['AI', 'ML', 'LLM', 'GPT', 'API', 'SDK', 'GPU', 'CPU', 'TPU', 'NLP', 'CV', 'RL']
        for term in tech_terms:
            if term in word_upper:
                is_tech_related = True
                break
        
        # 检查是否在白名单中（部分匹配）
        for product in TECH_PRODUCTS_WHITELIST:
            if product.upper() in word_upper or word_upper in product.upper():
                is_tech_related = True
                keywords.append(word)
                break
        
        # 如果是技术相关的，添加
        if is_tech_related and word not in keywords:
            keywords.append(word)
    
    return list(set(keywords))[:10]  # 去重，最多10个


def extract_all_entities(tweet: dict) -> Dict[str, List[str]]:
    """从推文中提取所有实体（改进版：扩展实体类型）"""
    entities = {
        "tickers": [],
        "hashtags": [],
        "domains": [],
        "mentions": [],
        "companies": [],
        "products": [],  # 新增：产品名
        "technologies": [],  # 新增：技术名
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
    
    # Mentions
    mentions = tweet.get("entities", {}).get("mentions", [])
    entities["mentions"] = [norm_username(m) if isinstance(m, str) else m for m in mentions if m]
    
    # 常见公司名（扩展列表）
    text = tweet.get("text", "").lower()
    common_companies = [
        "openai", "anthropic", "google", "microsoft", "apple", "meta", "amazon", "aws",
        "tesla", "nvidia", "amd", "intel", "twitter", "x", "linkedin", "facebook",
        "netflix", "uber", "airbnb", "stripe", "square", "coinbase", "binance",
    ]
    for company in common_companies:
        if company in text:
            entities["companies"].append(company.title())
    
    # 提取产品名和技术名（最终改进版：使用白名单和严格过滤）
    text_original = tweet.get("text", "")
    keywords = extract_keywords_from_text_final(text_original)
    
    # 分类关键词为产品和技术（使用白名单）
    tech_keywords_set = {kw.upper() for kw in TECH_PRODUCTS_WHITELIST}
    
    for keyword in keywords:
        keyword_upper = keyword.upper()
        
        # 检查是否在技术产品白名单中
        is_tech = False
        for tech in tech_keywords_set:
            if tech in keyword_upper or keyword_upper in tech:
                is_tech = True
                break
        
        # 检查是否包含技术术语
        if not is_tech:
            tech_indicators = ['GPT', 'LLM', 'AI', 'ML', 'AGI', 'NLP', 'CV', 'RL', 'TRANSFORMER', 'BERT', 'T5',
                             'TENSORFLOW', 'PYTORCH', 'JAX', 'CUDA', 'TPU', 'GPU', 'CPU', 'API', 'SDK',
                             'CHATGPT', 'CLAUDE', 'GEMINI', 'LLAMA', 'MISTRAL', 'DALL', 'MIDJOURNEY']
            if any(indicator in keyword_upper for indicator in tech_indicators):
                is_tech = True
        
        if is_tech:
            if keyword not in entities["technologies"]:
                entities["technologies"].append(keyword)
        else:
            # 可能是产品名（但需要更严格的检查）
            # 只保留看起来像产品名的词（长度适中，不是普通词）
            if (len(keyword) >= 4 and len(keyword) <= 20 and 
                keyword not in COMMON_WORDS and 
                keyword not in COMMON_PLACES and
                keyword not in COMMON_NAMES):
                if keyword not in entities["products"]:
                    entities["products"].append(keyword)
    
    return entities


class HeterogeneousGraph:
    """多层图（Heterogeneous Graph）"""
    
    def __init__(self):
        # 节点集合
        self.tweet_nodes: Set[str] = set()
        self.author_nodes: Set[str] = set()
        self.entity_nodes: Set[str] = set()
        
        # 边集合（使用字典存储权重）
        self.tweet_tweet_edges: Dict[Tuple[str, str], float] = {}  # (tweet1, tweet2) -> similarity
        self.author_tweet_edges: Dict[Tuple[str, str], int] = {}  # (author, tweet) -> count
        self.tweet_entity_edges: Dict[Tuple[str, str], int] = {}  # (tweet, entity) -> count
        self.author_author_edges: Dict[Tuple[str, str], int] = {}  # (author1, author2) -> count
        self.entity_entity_edges: Dict[Tuple[str, str], int] = {}  # (entity1, entity2) -> count
        
        # 节点属性
        self.tweet_embeddings: Dict[str, List[float]] = {}
        self.tweet_data: Dict[str, dict] = {}
        self.author_data: Dict[str, dict] = {}
        self.entity_data: Dict[str, dict] = {}
    
    def add_tweet(self, tweet: dict, embedding: Optional[List[float]] = None):
        """添加推文节点"""
        tweet_id = tweet.get("tweet_id", "")
        if not tweet_id:
            return
        
        self.tweet_nodes.add(tweet_id)
        self.tweet_data[tweet_id] = tweet
        
        if embedding:
            self.tweet_embeddings[tweet_id] = embedding
        
        # 添加 Author-Tweet 边
        author = norm_username(tweet.get("author_username", ""))
        if author:
            self.author_nodes.add(author)
            key = (author, tweet_id)
            self.author_tweet_edges[key] = self.author_tweet_edges.get(key, 0) + 1
            if author not in self.author_data:
                self.author_data[author] = {"tweet_count": 0}
            self.author_data[author]["tweet_count"] += 1
        
        # 添加 Tweet-Entity 边（支持新的实体类型）
        entities = extract_all_entities(tweet)
        for entity_type, entity_list in entities.items():
            for entity in entity_list:
                if entity:
                    entity_key = f"{entity_type}:{entity}"
                    self.entity_nodes.add(entity_key)
                    key = (tweet_id, entity_key)
                    self.tweet_entity_edges[key] = self.tweet_entity_edges.get(key, 0) + 1
                    if entity_key not in self.entity_data:
                        self.entity_data[entity_key] = {"type": entity_type, "name": entity, "count": 0}
                    self.entity_data[entity_key]["count"] += 1
    
    def add_tweet_similarity(self, tweet1_id: str, tweet2_id: str, similarity: float):
        """添加 Tweet-Tweet 相似度边"""
        if similarity > 0.7:  # 阈值
            key = tuple(sorted([tweet1_id, tweet2_id]))
            self.tweet_tweet_edges[key] = similarity
    
    def add_author_interaction(self, author1: str, author2: str, count: int = 1):
        """添加 Author-Author 传播边"""
        if author1 and author2 and author1 != author2:
            key = tuple(sorted([author1, author2]))
            self.author_author_edges[key] = self.author_author_edges.get(key, 0) + count
    
    def add_entity_cooccurrence(self, entity1: str, entity2: str, count: int = 1):
        """添加 Entity-Entity 共现边"""
        if entity1 and entity2 and entity1 != entity2:
            key = tuple(sorted([entity1, entity2]))
            self.entity_entity_edges[key] = self.entity_entity_edges.get(key, 0) + count
    
    def build_tweet_similarity_edges(self, similarity_threshold: float = 0.7):
        """构建 Tweet-Tweet 相似度边"""
        print("  Building Tweet-Tweet similarity edges...")
        tweet_ids = list(self.tweet_nodes)
        n = len(tweet_ids)
        
        for i in range(n):
            if i % 50 == 0:
                print(f"    Processing {i}/{n} tweets...")
            tweet1_id = tweet_ids[i]
            emb1 = self.tweet_embeddings.get(tweet1_id)
            if not emb1:
                continue
            
            for j in range(i + 1, n):
                tweet2_id = tweet_ids[j]
                emb2 = self.tweet_embeddings.get(tweet2_id)
                if not emb2:
                    continue
                
                similarity = cosine_similarity(emb1, emb2)
                if similarity > similarity_threshold:
                    self.add_tweet_similarity(tweet1_id, tweet2_id, similarity)
    
    def build_entity_cooccurrence_edges(self):
        """构建 Entity-Entity 共现边"""
        print("  Building Entity-Entity cooccurrence edges...")
        # 统计每个推文中的实体共现
        tweet_entities: Dict[str, Set[str]] = {}
        for (tweet_id, entity), count in self.tweet_entity_edges.items():
            if tweet_id not in tweet_entities:
                tweet_entities[tweet_id] = set()
            tweet_entities[tweet_id].add(entity)
        
        # 为每个推文中的实体对添加共现边
        for tweet_id, entities in tweet_entities.items():
            entity_list = list(entities)
            for i in range(len(entity_list)):
                for j in range(i + 1, len(entity_list)):
                    self.add_entity_cooccurrence(entity_list[i], entity_list[j], 1)


def step_e_build_heterogeneous_graph(
    tweets_24h_clean: List[dict],
    edges_24h: List[dict],
    output_dir: str = ".",
    filter_capital_tech: bool = True,
    similarity_threshold: float = 0.7,
    use_openai_embedding: bool = False,
    openai_api_key: Optional[str] = None,
) -> HeterogeneousGraph:
    """
    Step E: 构建多层图（Heterogeneous Graph）
    """
    print("Step E: 构建多层图（Heterogeneous Graph）...")
    
    graph = HeterogeneousGraph()
    
    # 过滤资本科技相关的推文
    filtered_tweets = []
    for tweet in tweets_24h_clean:
        if filter_capital_tech:
            text = tweet.get("text", "")
            hashtags = tweet.get("entities", {}).get("hashtags", [])
            cashtags = tweet.get("entities", {}).get("cashtags", [])
            if not is_capital_tech_related(text, hashtags, cashtags):
                continue
        filtered_tweets.append(tweet)
    
    print(f"  Filtered {len(filtered_tweets)} capital-tech related tweets")
    
    # 添加推文节点并计算 embedding
    print("  Computing embeddings and adding nodes...")
    for i, tweet in enumerate(filtered_tweets):
        if i % 50 == 0:
            print(f"    Processing {i}/{len(filtered_tweets)} tweets...")
        
        text = tweet.get("clean_text", tweet.get("text", ""))
        embedding = get_embedding(text, use_openai_embedding, openai_api_key)
        graph.add_tweet(tweet, embedding)
    
    # 构建 Tweet-Tweet 相似度边
    graph.build_tweet_similarity_edges(similarity_threshold)
    
    # 构建 Author-Author 传播边
    print("  Building Author-Author propagation edges...")
    author_interactions = defaultdict(int)
    for edge in edges_24h:
        source_author = edge.get("source_author_username", "")
        target_tweet_id = edge.get("target_tweet_id", "")
        if source_author and target_tweet_id:
            # 找到 target tweet 的作者
            target_tweet = graph.tweet_data.get(target_tweet_id)
            if target_tweet:
                target_author = norm_username(target_tweet.get("author_username", ""))
                if target_author:
                    key = tuple(sorted([source_author, target_author]))
                    author_interactions[key] += 1
    
    for (author1, author2), count in author_interactions.items():
        graph.add_author_interaction(author1, author2, count)
    
    # 构建 Entity-Entity 共现边
    graph.build_entity_cooccurrence_edges()
    
    print(f"  Graph statistics:")
    print(f"    Tweet nodes: {len(graph.tweet_nodes)}")
    print(f"    Author nodes: {len(graph.author_nodes)}")
    print(f"    Entity nodes: {len(graph.entity_nodes)}")
    print(f"    Tweet-Tweet edges: {len(graph.tweet_tweet_edges)}")
    print(f"    Author-Tweet edges: {len(graph.author_tweet_edges)}")
    print(f"    Tweet-Entity edges: {len(graph.tweet_entity_edges)}")
    print(f"    Author-Author edges: {len(graph.author_author_edges)}")
    print(f"    Entity-Entity edges: {len(graph.entity_entity_edges)}")
    print("Step E: 完成\n")
    
    return graph


# ============================================================================
# Step F: 社区发现（Community Detection）
# ============================================================================

def simple_louvain_community_detection(graph: HeterogeneousGraph, resolution: float = 1.0) -> Dict[str, int]:
    """
    简化的 Louvain 社区发现算法
    返回：node -> community_id 的映射
    """
    print("  Running simplified Louvain community detection...")
    
    # 将所有节点合并到一个统一的节点集合
    all_nodes = {}
    node_to_id = {}
    node_id = 0
    
    for tweet_id in graph.tweet_nodes:
        node_key = f"tweet:{tweet_id}"
        all_nodes[node_key] = node_id
        node_to_id[node_id] = node_key
        node_id += 1
    
    for author in graph.author_nodes:
        node_key = f"author:{author}"
        all_nodes[node_key] = node_id
        node_to_id[node_id] = node_key
        node_id += 1
    
    for entity in graph.entity_nodes:
        node_key = f"entity:{entity}"
        all_nodes[node_key] = node_id
        node_to_id[node_id] = node_key
        node_id += 1
    
    n_nodes = len(all_nodes)
    print(f"    Total nodes: {n_nodes}")
    
    # 初始化：每个节点一个社区
    communities = {i: i for i in range(n_nodes)}
    
    # 构建邻接矩阵（简化版：只考虑主要边）
    adjacency = defaultdict(lambda: defaultdict(float))
    
    # Tweet-Tweet 边
    for (tweet1, tweet2), weight in graph.tweet_tweet_edges.items():
        node1 = all_nodes.get(f"tweet:{tweet1}")
        node2 = all_nodes.get(f"tweet:{tweet2}")
        if node1 is not None and node2 is not None:
            adjacency[node1][node2] = weight
            adjacency[node2][node1] = weight
    
    # Author-Tweet 边
    for (author, tweet), weight in graph.author_tweet_edges.items():
        node1 = all_nodes.get(f"author:{author}")
        node2 = all_nodes.get(f"tweet:{tweet}")
        if node1 is not None and node2 is not None:
            adjacency[node1][node2] = weight
            adjacency[node2][node1] = weight
    
    # Tweet-Entity 边
    for (tweet, entity), weight in graph.tweet_entity_edges.items():
        node1 = all_nodes.get(f"tweet:{tweet}")
        node2 = all_nodes.get(f"entity:{entity}")
        if node1 is not None and node2 is not None:
            adjacency[node1][node2] = weight
            adjacency[node2][node1] = weight
    
    # Author-Author 边
    for (author1, author2), weight in graph.author_author_edges.items():
        node1 = all_nodes.get(f"author:{author1}")
        node2 = all_nodes.get(f"author:{author2}")
        if node1 is not None and node2 is not None:
            adjacency[node1][node2] = weight
            adjacency[node2][node1] = weight
    
    # Entity-Entity 边
    for (entity1, entity2), weight in graph.entity_entity_edges.items():
        node1 = all_nodes.get(f"entity:{entity1}")
        node2 = all_nodes.get(f"entity:{entity2}")
        if node1 is not None and node2 is not None:
            adjacency[node1][node2] = weight
            adjacency[node2][node1] = weight
    
    # 简化的社区发现：基于连通分量和模块度优化
    # 使用贪心算法：迭代合并能提高模块度的节点对
    
    def calculate_modularity(communities_dict, adj, total_weight):
        """计算模块度"""
        if total_weight == 0:
            return 0.0
        
        modularity = 0.0
        for node1, neighbors in adj.items():
            comm1 = communities_dict[node1]
            for node2, weight in neighbors.items():
                comm2 = communities_dict[node2]
                if comm1 == comm2:
                    ki = sum(adj[node1].values())
                    kj = sum(adj[node2].values())
                    modularity += weight - (ki * kj) / (2 * total_weight)
        
        return modularity / (2 * total_weight)
    
    # 计算总权重
    total_weight = sum(sum(neighbors.values()) for neighbors in adjacency.values()) / 2
    
    # 贪心合并：迭代优化
    improved = True
    iteration = 0
    max_iterations = 10
    
    while improved and iteration < max_iterations:
        improved = False
        iteration += 1
        print(f"    Iteration {iteration}...")
        
        # 尝试将每个节点移动到能提高模块度的社区
        for node in range(n_nodes):
            current_comm = communities[node]
            best_comm = current_comm
            best_delta = 0.0
            
            # 检查邻居节点的社区
            neighbor_comms = set()
            for neighbor in adjacency[node].keys():
                neighbor_comms.add(communities[neighbor])
            neighbor_comms.add(current_comm)
            
            # 尝试移动到每个可能的社区
            for new_comm in neighbor_comms:
                if new_comm == current_comm:
                    continue
                
                # 临时移动并计算模块度变化
                communities[node] = new_comm
                new_modularity = calculate_modularity(communities, adjacency, total_weight)
                communities[node] = current_comm
                current_modularity = calculate_modularity(communities, adjacency, total_weight)
                
                delta = new_modularity - current_modularity
                if delta > best_delta:
                    best_delta = delta
                    best_comm = new_comm
            
            # 如果找到更好的社区，移动
            if best_delta > 0.001 and best_comm != current_comm:
                communities[node] = best_comm
                improved = True
    
    # 转换为 node_key -> community_id 的映射
    result = {}
    for node_id, comm_id in communities.items():
        node_key = node_to_id[node_id]
        result[node_key] = comm_id
    
    print(f"    Found {len(set(communities.values()))} communities")
    print("  Community detection: 完成")
    
    return result


def step_f_community_detection(
    graph: HeterogeneousGraph,
    output_dir: str = ".",
    resolution: float = 1.0,
) -> Dict[str, int]:
    """
    Step F: 社区发现（Community Detection）
    返回：node_key -> community_id 的映射
    """
    print("Step F: 社区发现（Community Detection）...")
    
    communities = simple_louvain_community_detection(graph, resolution)
    
    # 保存社区信息
    community_nodes = defaultdict(list)
    for node_key, comm_id in communities.items():
        community_nodes[comm_id].append(node_key)
    
    communities_info = []
    for comm_id, nodes in community_nodes.items():
        if len(nodes) < 2:  # 过滤太小的社区
            continue
        
        tweets = [n for n in nodes if n.startswith("tweet:")]
        authors = [n for n in nodes if n.startswith("author:")]
        entities = [n for n in nodes if n.startswith("entity:")]
        
        communities_info.append({
            "community_id": comm_id,
            "tweet_count": len(tweets),
            "author_count": len(authors),
            "entity_count": len(entities),
            "tweets": [n.replace("tweet:", "") for n in tweets],
            "authors": [n.replace("author:", "") for n in authors],
            "entities": [n.replace("entity:", "") for n in entities],
        })
    
    save_jsonl(communities_info, os.path.join(output_dir, "communities_24h_v2B_final.jsonl"))
    print(f"  Found {len(communities_info)} communities")
    print("Step F: 完成\n")
    
    return communities


# ============================================================================
# Step G: 社区评分和 Top5 选择
# ============================================================================

def find_community_center(graph: HeterogeneousGraph, community_nodes: List[str], tweet_map: Dict[str, dict] = None) -> Tuple[Optional[str], Optional[str], List[str]]:
    """
    找到社区的中心节点（改进版：考虑更多因素）
    返回：(最中心的实体节点, 最中心的 tweet 节点, 关键词列表)
    """
    # 计算每个节点的中心度（改进：考虑度、连接权重、重要性）
    node_centrality = defaultdict(float)
    node_degree = defaultdict(int)  # 节点的度
    
    # 统计每个节点的连接权重和度
    for node_key in community_nodes:
        if node_key.startswith("tweet:"):
            tweet_id = node_key.replace("tweet:", "")
            # Tweet 的连接：与其他 tweet 的相似度 + 与 entity 的连接
            for (tweet1, tweet2), weight in graph.tweet_tweet_edges.items():
                if tweet1 == tweet_id or tweet2 == tweet_id:
                    node_centrality[node_key] += weight * 1.5  # 相似度边权重更高
                    node_degree[node_key] += 1
            
            for (tweet, entity), weight in graph.tweet_entity_edges.items():
                if tweet == tweet_id:
                    node_centrality[node_key] += weight
                    node_degree[node_key] += 1
            
            # 考虑推文的 engagement（如果有）
            if tweet_map:
                tweet = tweet_map.get(tweet_id)
                if tweet:
                    metrics = tweet.get("public_metrics", {})
                    engagement = metrics.get("like_count", 0) + metrics.get("repost_count", 0) * 2
                    node_centrality[node_key] += math.log1p(engagement) * 0.3  # engagement 加成
        
        elif node_key.startswith("entity:"):
            entity_key = node_key.replace("entity:", "")
            # Entity 的连接：与 tweet 的连接 + 与其他 entity 的共现
            for (tweet, entity), weight in graph.tweet_entity_edges.items():
                if entity == entity_key:
                    node_centrality[node_key] += weight * 1.2  # 实体连接权重更高
                    node_degree[node_key] += 1
            
            for (entity1, entity2), weight in graph.entity_entity_edges.items():
                if entity1 == entity_key or entity2 == entity_key:
                    node_centrality[node_key] += weight * 1.5  # 实体共现权重更高
                    node_degree[node_key] += 1
            
            # 考虑实体类型的重要性（companies > products > technologies > others）
            if ":" in entity_key:
                entity_type = entity_key.split(":")[0]
                type_weights = {
                    "companies": 2.0,
                    "products": 1.5,
                    "technologies": 1.3,
                    "tickers": 1.2,
                    "hashtags": 1.0,
                    "domains": 0.8,
                    "mentions": 0.5,
                }
                node_centrality[node_key] *= type_weights.get(entity_type, 1.0)
    
    # PageRank 风格的权重调整：考虑邻居节点的重要性
    # 简化版：节点的中心度 = 自身连接权重 + 0.1 * 邻居节点平均中心度
    for iteration in range(2):  # 2次迭代
        new_centrality = defaultdict(float)
        for node_key in community_nodes:
            new_centrality[node_key] = node_centrality[node_key]
            # 考虑邻居节点
            if node_key.startswith("tweet:"):
                tweet_id = node_key.replace("tweet:", "")
                neighbor_centrality = 0.0
                neighbor_count = 0
                for (tweet, entity), _ in graph.tweet_entity_edges.items():
                    if tweet == tweet_id:
                        entity_key = f"entity:{entity}"
                        if entity_key in community_nodes:
                            neighbor_centrality += node_centrality[entity_key]
                            neighbor_count += 1
                if neighbor_count > 0:
                    new_centrality[node_key] += 0.1 * (neighbor_centrality / neighbor_count)
        node_centrality = new_centrality
    
    # 找到最中心的实体和 tweet
    center_entity = None
    center_tweet = None
    max_entity_centrality = 0.0
    max_tweet_centrality = 0.0
    
    for node_key, centrality in node_centrality.items():
        if node_key.startswith("entity:") and centrality > max_entity_centrality:
            max_entity_centrality = centrality
            center_entity = node_key.replace("entity:", "")
        elif node_key.startswith("tweet:") and centrality > max_tweet_centrality:
            max_tweet_centrality = centrality
            center_tweet = node_key.replace("tweet:", "")
    
    # 提取关键词（从社区内的推文，最终改进版：使用更严格的过滤）
    keywords = []
    if tweet_map:
        for node_key in community_nodes:
            if node_key.startswith("tweet:"):
                tweet_id = node_key.replace("tweet:", "")
                tweet = tweet_map.get(tweet_id)
                if tweet:
                    text = tweet.get("text", "")
                    extracted = extract_keywords_from_text_final(text)
                    keywords.extend(extracted)
    
    # 去重并排序（按频率），但优先保留技术产品名
    keyword_freq = defaultdict(int)
    for kw in keywords:
        keyword_freq[kw] += 1
    
    # 优先保留技术产品名
    tech_keywords = []
    other_keywords = []
    for kw, freq in keyword_freq.items():
        kw_upper = kw.upper()
        is_tech = any(tech.upper() in kw_upper or kw_upper in tech.upper() for tech in TECH_PRODUCTS_WHITELIST)
        if is_tech:
            tech_keywords.append((kw, freq))
        else:
            other_keywords.append((kw, freq))
    
    # 排序：技术关键词优先，然后按频率
    tech_keywords.sort(key=lambda x: x[1], reverse=True)
    other_keywords.sort(key=lambda x: x[1], reverse=True)
    keywords = [kw[0] for kw in tech_keywords[:3]] + [kw[0] for kw in other_keywords[:2]]
    keywords = keywords[:5]
    
    return center_entity, center_tweet, keywords


def step_g_community_scoring(
    graph: HeterogeneousGraph,
    communities: Dict[str, int],
    tweets_24h_clean: List[dict],
    edges_24h: List[dict],
    initial_kol_path: str = "initial_kol_500.json",
    output_dir: str = ".",
) -> List[dict]:
    """
    Step G: 社区评分和 Top5 选择
    """
    print("Step G: 社区评分和 Top5 选择...")
    
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
    
    # 按社区分组
    community_nodes = defaultdict(list)
    for node_key, comm_id in communities.items():
        community_nodes[comm_id].append(node_key)
    
    # 为每个社区计算指标
    communities_with_scores = []
    tweet_map = {t.get("tweet_id", ""): t for t in tweets_24h_clean}
    
    for comm_id, nodes in community_nodes.items():
        if len(nodes) < 2:  # 过滤太小的社区
            continue
        
        # 提取推文、作者、实体
        tweet_ids = [n.replace("tweet:", "") for n in nodes if n.startswith("tweet:")]
        authors = [n.replace("author:", "") for n in nodes if n.startswith("author:")]
        entities = [n.replace("entity:", "") for n in nodes if n.startswith("entity:")]
        
        if len(tweet_ids) == 0:
            continue
        
        # 计算基础指标
        unique_authors = set(authors)
        total_likes = 0
        total_reposts = 0
        total_replies = 0
        total_quotes = 0
        total_followers = 0
        
        for tid in tweet_ids:
            tweet = tweet_map.get(tid)
            if tweet:
                author = norm_username(tweet.get("author_username", ""))
                if author and author in kol_influence_map:
                    total_followers += kol_influence_map[author]
                
                metrics = tweet.get("public_metrics", {})
                total_likes += metrics.get("like_count", 0)
                total_reposts += metrics.get("repost_count", 0)
                total_replies += metrics.get("reply_count", 0)
                total_quotes += metrics.get("quote_count", 0)
        
        author_cnt = len(unique_authors)
        tweet_cnt = len(tweet_ids)
        engagement = total_likes + total_reposts * 2 + total_replies * 0.5 + total_quotes * 1.5
        
        # 计算传播强度
        propagation = 0
        for edge in edges_24h:
            source_author = edge.get("source_author_username", "")
            target_tweet_id = edge.get("target_tweet_id", "")
            if source_author in unique_authors and target_tweet_id in tweet_ids:
                propagation += 1
        
        # 找到社区中心（改进版：传入 tweet_map）
        center_entity, center_tweet, keywords = find_community_center(graph, nodes, tweet_map)
        
        # 计算社区分数
        community_score = (
            1.0 * math.log1p(engagement) +
            3.0 * author_cnt +
            1.5 * math.log1p(propagation) +
            0.5 * math.log1p(tweet_cnt) +
            0.3 * math.log1p(total_followers / max(author_cnt, 1))
        )
        
        # 硬过滤
        if author_cnt < 2 and engagement < 50:
            continue
        
        communities_with_scores.append({
            "community_id": comm_id,
            "tweet_ids": tweet_ids,
            "authors": list(unique_authors),
            "entities": entities,
            "center_entity": center_entity,
            "center_tweet": center_tweet,
            "keywords": keywords,
            "author_cnt": author_cnt,
            "tweet_cnt": tweet_cnt,
            "engagement": engagement,
            "total_likes": total_likes,
            "total_reposts": total_reposts,
            "total_replies": total_replies,
            "total_quotes": total_quotes,
            "propagation": propagation,
            "community_score": community_score,
        })
    
    # 按分数排序
    communities_with_scores.sort(key=lambda x: x.get("community_score", 0), reverse=True)
    
    # 取 Top5
    top5 = communities_with_scores[:5]
    
    # 为每个社区添加排名
    for i, comm in enumerate(top5, 1):
        comm["rank"] = i
    
    # 输出
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window": "24h",
        "version": "V2-B Final (Discussion Graph + Community Detection - Final Enhanced)",
        "top5": top5,
    }
    
    output_path = os.path.join(output_dir, "hot_communities_top5_v2B_final.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"  Top5 communities generated (from {len(communities_with_scores)} communities)")
    print("Step G: 完成\n")
    
    return top5


# ============================================================================
# Step I: 社区呈现（基于中心节点生成标题）
# ============================================================================

def step_i_community_presentation(
    top5_communities: List[dict],
    graph: HeterogeneousGraph,
    tweets_24h_clean: List[dict],
    edges_24h: List[dict],
    output_dir: str = ".",
) -> dict:
    """
    Step I: 社区呈现
    基于社区的中心节点生成标题和描述
    """
    print("Step I: 社区呈现...")
    
    tweet_map = {t.get("tweet_id", ""): t for t in tweets_24h_clean}
    
    communities_readable = []
    for comm in top5_communities:
        comm_id = comm.get("community_id", 0)
        tweet_ids = comm.get("tweet_ids", [])
        entities = comm.get("entities", [])
        center_entity = comm.get("center_entity", "")
        center_tweet_id = comm.get("center_tweet", "")
        keywords = comm.get("keywords", [])
        
        # 生成 title：基于中心实体、关键词和推文内容（改进版）
        title_parts = []
        
        # 解析中心实体
        if center_entity:
            if ":" in center_entity:
                entity_type, entity_name = center_entity.split(":", 1)
                if entity_type == "companies":
                    title_parts.append(entity_name)
                elif entity_type == "tickers":
                    display_ticker = entity_name if entity_name.startswith("$") else f"${entity_name}"
                    title_parts.append(display_ticker)
                elif entity_type == "hashtags":
                    title_parts.append(f"#{entity_name}")
                elif entity_type == "products":
                    title_parts.append(entity_name)
                elif entity_type == "technologies":
                    title_parts.append(entity_name)
        
        # 如果没有中心实体，使用其他重要实体
        if not title_parts:
            # 优先使用 companies, products, technologies
            for entity_key in entities:
                if ":" in entity_key:
                    entity_type, entity_name = entity_key.split(":", 1)
                    if entity_type in ["companies", "products", "technologies"]:
                        title_parts.append(entity_name)
                        break
                    elif entity_type == "tickers":
                        display_ticker = entity_name if entity_name.startswith("$") else f"${entity_name}"
                        title_parts.append(display_ticker)
                        break
        
        # 如果还是没有，使用关键词（改进）
        if not title_parts and keywords:
            # 选择最重要的关键词（通常是技术/产品名）
            for kw in keywords[:2]:
                if len(kw) >= 3:  # 过滤太短的词
                    title_parts.append(kw)
                    if len(title_parts) >= 2:
                        break
        
        # 如果还是没有，从推文内容提取（改进）
        if not title_parts and center_tweet_id:
            center_tweet = tweet_map.get(center_tweet_id)
            if center_tweet:
                text = center_tweet.get("clean_text", center_tweet.get("text", ""))
                # 提取首句或前50个字符中的关键词
                first_sentence = text.split('.')[0] if '.' in text else text[:100]
                extracted_kw = extract_keywords_from_text_final(first_sentence)
                if extracted_kw:
                    title_parts.append(extracted_kw[0])
        
        # 生成 title（最终改进版：生成更完整的标题）
        title = None
        if title_parts:
            # 如果只有一个词，尝试结合推文内容生成更完整的标题
            if len(title_parts) == 1:
                main_entity = title_parts[0]
                # 从中心推文或最热门推文中提取关键短语
                if center_tweet_id:
                    center_tweet = tweet_map.get(center_tweet_id)
                    if center_tweet:
                        text = center_tweet.get("clean_text", center_tweet.get("text", ""))
                        # 提取包含主实体的短语
                        if main_entity.lower() in text.lower():
                            # 找到包含主实体的句子或短语
                            sentences = re.split(r'[.!?]\s+', text)
                            for sent in sentences:
                                if main_entity.lower() in sent.lower() and len(sent) > 20:
                                    # 提取关键短语（去除URL和特殊字符）
                                    sent_clean = re.sub(r'https?://\S+', '', sent)
                                    sent_clean = re.sub(r'[^\w\s]', ' ', sent_clean)
                                    words = sent_clean.split()
                                    if len(words) >= 3:
                                        # 找到主实体在句子中的位置
                                        try:
                                            idx = [w.lower() for w in words].index(main_entity.lower())
                                            # 提取主实体前后的词
                                            start = max(0, idx - 2)
                                            end = min(len(words), idx + 3)
                                            phrase = ' '.join(words[start:end])
                                            if len(phrase) > len(main_entity):
                                                title = f"{main_entity}: {phrase[:50]}"
                                                break
                                        except ValueError:
                                            pass
                
                # 如果还是没有生成完整标题，使用关键词组合
                if not title:
                    if keywords:
                        # 选择与主实体相关的关键词
                        related_kw = [kw for kw in keywords[:3] if kw.lower() != main_entity.lower()]
                        if related_kw:
                            title = f"{main_entity} / {related_kw[0]}"
                        else:
                            title = main_entity
                    else:
                        title = main_entity
            else:
                # 多个词，直接组合
                title = " / ".join(title_parts[:2])
                if len(title_parts) > 2:
                    title += " 等话题"
        else:
            # 最后的降级方案：从推文内容生成标题
            if center_tweet_id:
                center_tweet = tweet_map.get(center_tweet_id)
                if center_tweet:
                    text = center_tweet.get("clean_text", center_tweet.get("text", ""))
                    # 提取前50个字符作为标题
                    title = text[:50].strip()
                    if len(title) < 10:
                        title = f"热点议题 {comm.get('rank', 0)}"
                else:
                    title = f"热点议题 {comm.get('rank', 0)}"
            else:
                title = f"热点议题 {comm.get('rank', 0)}"
        
        # 生成 one_liner：从中心推文或最热门的推文中提取
        one_liner = "多位 KOL 讨论的热点议题"
        
        if center_tweet_id:
            center_tweet = tweet_map.get(center_tweet_id)
            if center_tweet:
                text = center_tweet.get("clean_text", center_tweet.get("text", ""))
                one_liner = text[:150] + "..." if len(text) > 150 else text
        else:
            # 使用最热门的推文
            event_tweets = [tweet_map.get(tid) for tid in tweet_ids if tweet_map.get(tid)]
            if event_tweets:
                event_tweets.sort(
                    key=lambda t: t.get("public_metrics", {}).get("like_count", 0),
                    reverse=True
                )
                top_tweet = event_tweets[0]
                text = top_tweet.get("clean_text", top_tweet.get("text", ""))
                one_liner = text[:150] + "..." if len(text) > 150 else text
        
        # 收集 key_entities（改进：包含新的实体类型）
        key_entities = {
            "companies": [],
            "tickers": [],
            "hashtags": [],
            "domains": [],
            "products": [],
            "technologies": [],
        }
        
        for entity_key in entities:
            if ":" in entity_key:
                entity_type, entity_name = entity_key.split(":", 1)
                if entity_type == "companies" and len(key_entities["companies"]) < 5:
                    key_entities["companies"].append(entity_name)
                elif entity_type == "tickers" and len(key_entities["tickers"]) < 5:
                    key_entities["tickers"].append(entity_name)
                elif entity_type == "hashtags" and len(key_entities["hashtags"]) < 5:
                    key_entities["hashtags"].append(entity_name)
                elif entity_type == "domains" and len(key_entities["domains"]) < 3:
                    key_entities["domains"].append(entity_name)
                elif entity_type == "products" and len(key_entities["products"]) < 5:
                    key_entities["products"].append(entity_name)
                elif entity_type == "technologies" and len(key_entities["technologies"]) < 5:
                    key_entities["technologies"].append(entity_name)
        
        # 如果没有实体，使用关键词（改进）
        if not any(key_entities.values()) and keywords:
            key_entities["technologies"] = keywords[:3]
        
        # 生成 evidence_tweets
        evidence_tweets = []
        tweet_with_metrics = []
        for tid in tweet_ids:
            tweet = tweet_map.get(tid)
            if tweet:
                like_count = tweet.get("public_metrics", {}).get("like_count", 0)
                repost_count = tweet.get("public_metrics", {}).get("repost_count", 0)
                total_engagement = like_count + repost_count * 2
                tweet_with_metrics.append((total_engagement, like_count, tweet))
        
        tweet_with_metrics.sort(key=lambda x: x[0], reverse=True)
        for total_engagement, like_count, tweet in tweet_with_metrics[:5]:
            evidence_tweets.append({
                "tweet_id": tweet.get("tweet_id", ""),
                "author": tweet.get("author_username", ""),
                "text": tweet.get("text", "")[:200],
                "like_count": like_count,
                "created_at": tweet.get("created_at", ""),
            })
        
        # 生成 why_trending
        author_cnt = comm.get("author_cnt", 0)
        tweet_cnt = comm.get("tweet_cnt", 0)
        propagation = comm.get("propagation", 0)
        engagement = comm.get("engagement", 0)
        
        why_trending_parts = []
        if author_cnt >= 3:
            why_trending_parts.append(f"{author_cnt} 位 KOL 参与讨论")
        if propagation > 0:
            why_trending_parts.append(f"跨作者传播 {propagation} 次")
        if engagement > 100:
            why_trending_parts.append(f"总互动量 {int(engagement)}")
        if tweet_cnt >= 5:
            why_trending_parts.append(f"共 {tweet_cnt} 条推文")
        
        why_trending = "；".join(why_trending_parts) if why_trending_parts else "引发广泛关注"
        
        communities_readable.append({
            "rank": comm.get("rank", 0),
            "community_id": comm_id,
            "title": title,
            "one_liner": one_liner,
            "key_entities": key_entities,
            "evidence_tweets": evidence_tweets,
            "why_trending": why_trending,
            "metrics": {
                "author_count": author_cnt,
                "tweet_count": tweet_cnt,
                "engagement": engagement,
                "propagation": propagation,
            },
            "community_score": round(comm.get("community_score", 0), 2),
            "center_entity": center_entity,
            "center_tweet": center_tweet_id,
            "keywords": keywords,
        })
    
    # 生成 daily_report.json
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window": "24h",
        "version": "V2-B Final (Discussion Graph + Community Detection - Final Enhanced)",
        "summary": {
            "total_communities_analyzed": len(top5_communities),
            "top5_hot_communities": [
                {
                    "rank": c["rank"],
                    "title": c["title"],
                    "one_liner": c["one_liner"],
                    "community_score": c["community_score"],
                }
                for c in communities_readable
            ],
        },
        "top5_hot_communities": communities_readable,
    }
    
    output_path = os.path.join(output_dir, "daily_report_v2B_final.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    # 生成易读版本（中文）
    readable_report = {
        "生成时间": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "时间窗口": "24小时",
        "版本": "V2-B Final (讨论图谱 + 社区发现版本 - 最终改进版)",
        "Top5 热点议题": [
            {
                "排名": c["rank"],
                "议题": c["title"],
                "一句话描述": c["one_liner"],
                "议题分数": c["community_score"],
                "参与作者数": c["metrics"]["author_count"],
                "推文数": c["metrics"]["tweet_count"],
                "总互动量": c["metrics"]["engagement"],
                "传播强度": c["metrics"]["propagation"],
                "关键实体": c["key_entities"],
                "为何热门": c["why_trending"],
                "中心实体": c["center_entity"],
            }
            for c in communities_readable
        ],
    }
    
    readable_path = os.path.join(output_dir, "daily_report_readable_v2B_final.json")
    with open(readable_path, "w", encoding="utf-8") as f:
        json.dump(readable_report, f, ensure_ascii=False, indent=2)
    
    print("Step I: 完成")
    print(f"  生成文件: daily_report_v2B_final.json, daily_report_readable_v2B_final.json\n")
    
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
    similarity_threshold: float = 0.7,
    use_openai_embedding: bool = False,
    openai_api_key: Optional[str] = None,
):
    """
    运行完整的 Pipeline V2-B（讨论图谱 + 社区发现）
    """
    print("=" * 60)
    print("资本科技热点 Pipeline V2-B Final (Discussion Graph + Community Detection - Final Enhanced)")
    print("=" * 60)
    print()
    
    # Step C: ETL 清洗与标准化
    tweets_14d_clean, tweets_24h_clean = step_c_etl_simplified(
        initial_kol_path, tweets_14d_path, tweets_24h_path, output_dir, timezone_offset
    )
    
    # Step D: 传播关系派生
    edges_14d, edges_24h = step_d_propagation_edges_simplified(
        tweets_14d_clean, tweets_24h_clean, output_dir
    )
    
    # Step E: 构建多层图
    graph = step_e_build_heterogeneous_graph(
        tweets_24h_clean, edges_24h, output_dir,
        filter_capital_tech=True,
        similarity_threshold=similarity_threshold,
        use_openai_embedding=use_openai_embedding,
        openai_api_key=openai_api_key
    )
    
    # Step F: 社区发现
    communities = step_f_community_detection(graph, output_dir)
    
    # Step G: 社区评分和 Top5 选择
    top5_communities = step_g_community_scoring(
        graph, communities, tweets_24h_clean, edges_24h, initial_kol_path, output_dir
    )
    
    # Step I: 社区呈现
    daily_report = step_i_community_presentation(
        top5_communities, graph, tweets_24h_clean, edges_24h, output_dir
    )
    
    print("=" * 60)
    print("Pipeline 完成！")
    print("=" * 60)
    print(f"\n输出文件目录: {output_dir}")
    print("\n主要输出文件:")
    print("  - tweets_14d_clean_v2B_final.jsonl")
    print("  - tweets_24h_clean_v2B_final.jsonl")
    print("  - edges_14d_v2B_final.jsonl")
    print("  - edges_24h_v2B_final.jsonl")
    print("  - communities_24h_v2B_final.jsonl (V2-B Final)")
    print("  - hot_communities_top5_v2B_final.json (V2-B Final)")
    print("  - daily_report_v2B_final.json (V2-B Final)")
    print("  - daily_report_readable_v2B_final.json (V2-B Final)")
    
    return daily_report


if __name__ == "__main__":
    run_pipeline()

