# 资本科技热点 Pipeline V1 步骤文档

## 说明
本文档基于 `pipeline_v1_advanced.py` 代码实际实现编写，确保与代码完全一致。

---

## Step C — ETL 清洗与标准化（直接接爬虫输出）

### C.0 输入文件（来自爬虫）
initial_kol_500.json
{
  "generated_at": "ISO-8601",
  "seeds": [...100 accounts...],
  "expanded": [...400 accounts...],
  "all": [...500 accounts...]
}
tweets_14d.jsonl（每行一条推文）
tweets_24h.jsonl（每行一条推文）
每条推文结构：
{
  "tweet_id": "string",
  "author_id": "string",
  "author_username": "string",
  "created_at": "ISO-8601",
  "text": "string",
  "public_metrics": {
    "like_count": 0,
    "repost_count": 0,
    "reply_count": 0,
    "quote_count": 0
  },
  "referenced_tweets": [
    { "type": "reposted|quoted", "id": "string" }
  ],
  "entities": {
    "hashtags": [],
    "cashtags": [],
    "urls": [],
    "mentions": []
  }
}

### C.1 账号全集校验（只分析 500 个 KOL）
目的：确保后续分析仅基于initial_kol_500.json中定义的500个KOL账号，防止爬虫误采或账号污染。
具体操作：
1）读取 initial_kol_500.json，从 all 字段中提取所有账号的 username
2）对所有 username 执行统一标准化：转小写、去掉前缀@、去除首尾空格
3）构建 kol_set：{ author_username }（标准化后的用户名集合）
4）推文过滤规则：
对 tweets_14d.jsonl：
仅保留 author_username（标准化后）∈ kol_set 的推文
对 tweets_24h.jsonl：
同样仅保留 KOL 账号推文（标准化后匹配）

输出文件
kol_all_500.jsonl（500 个 KOL 的 username 列表，每行一个 JSON 对象 {"username": "..."}）
tweets_14d_kol.jsonl
tweets_24h_kol.jsonl

### C.2 时间字段标准化
目的：为所有推文统一构建可用于时间聚合与趋势分析的时间字段。
具体操作：
对每一条推文：
1）解析 created_at（ISO-8601，UTC）
   - 处理 "Z" 后缀：替换为 "+00:00"
   - 使用 datetime.fromisoformat() 解析
   - 如果无时区信息，设置为 UTC
2）构建以下字段：
created_ts：UTC 时间戳（秒，整数）
created_at_local：本地时区时间（UTC +8，ISO-8601 格式）
local_date：本地日期（YYYY-MM-DD）

异常处理：
若时间解析失败（ValueError 或 AttributeError）：
created_ts = 0
created_at_local = 保留原 created_at 字符串
local_date = ""

### C.3 文本字段标准化（不改语义，只做可计算化）
目的：保留原始文本，同时生成可用于后续分析的规范化文本版本。
具体操作：
对每一条推文：
1）新增字段：raw_text = text（保留原始文本）
2）构建 clean_text：
   - 从 entities.urls 中提取 URL：
     * 如果 url 是字符串，直接在 text 中替换为 <URL>
     * 如果 url 是字典且包含 "url" 字段，使用 url["url"] 在 text 中替换为 <URL>
     （注意：代码中只检查 url["url"]，不检查 expanded_url）
   - 合并连续空格为单个空格（使用正则表达式 \s+）
   - 去除首尾空格（strip()）

### C.4 entities 标准化（逐字段对齐爬虫输出）
目的：对 hashtags、mentions、urls 等结构化字段进行统一处理。
操作：对 entities 做"轻标准化"，不改变字段结构：
具体操作：
对每一条推文：
1）hashtags：全部转换为小写（如果元素是字符串）
2）cashtags：保持原样，不做修改
3）urls：从 URL 或 expanded_url 中解析主域名
   - 如果 url 是字符串，直接解析域名
   - 如果 url 是字典，使用 url.get("url", "") 或 url.get("expanded_url", "")
   - 去掉 www. 前缀
   - 去重后保存为 url_domains 数组（新增字段，不修改 entities.urls）
4）mentions：转小写，去掉 @ 前缀（使用 norm_username 函数）

### C.5 结构化去重（关键！）
目的：避免同一推文多次出现，确保分析唯一性。
去重规则：
1）以 tweet_id 作为唯一键
2）若出现重复：
保留 created_ts（时间戳）更晚的
若时间相同（created_ts 相等），保留字段更完整（字符串长度更长）的版本
3）如果 tweet_id 为空，跳过该推文

最终输出：
tweets_14d_clean.jsonl
tweets_24h_clean.jsonl

---

## Step D — 传播关系派生（基于 referenced_tweets）

目的：从推文中派生出 KOL 之间的传播关系，用于后续热点与趋势分析。
处理对象：
tweets_14d_clean
tweets_24h_clean

传播边生成规则：
对每条推文：
1）检查 referenced_tweets 字段
2）如果 referenced_tweets 为空，跳过
3）遍历 referenced_tweets 数组中的每个元素：
   - 如果元素不是字典，跳过
   - 检查 type 字段
   - 仅当 type ∈ {"reposted", "quoted"} 时生成传播边
   - 忽略 reply 类型和其他类型
   - 如果 target_tweet_id（即 ref["id"]）为空，跳过

传播边结构：
{
  "source_tweet_id": "string",  # 当前推文的 tweet_id
  "source_author_username": "string",  # 当前推文作者（标准化后）
  "target_tweet_id": "string",  # 被引用推文的 id
  "edge_type": "reposted" | "quoted",  # 边的类型
  "created_at": "ISO-8601",  # 当前推文的 created_at
  "local_date": "YYYY-MM-DD"  # 当前推文的 local_date
}

输出文件：
edges_14d.jsonl
edges_24h.jsonl

---

## Step E — 候选主题生成（从爬虫字段直接派生 + 内容关键词提取）

目标：从 24 小时内的推文中生成候选"主题信号"。

主题过滤机制：
使用预定义的资本科技关键词表（CAPITAL_TECH_KEYWORDS）
关键词覆盖：
AI / ML
投资 / VC
科技公司
加密 / 区块链
科技趋势与商业

### E.0 输入
tweets_24h_clean（用于当天热点）
edges_24h（用于传播强度）

### E.1 候选 1：Hashtag Topic
从每条推文 entities.hashtags 生成候选：
- 遍历每条推文的 hashtags 数组
- 对于每个非空 hashtag：
  - 如果开启主题过滤（filter_capital_tech=True）：
    * 检查推文文本（text）或 hashtag 是否匹配资本科技关键词
    * 如果不匹配，跳过（计入 filtered_count）
  - 生成候选：
    topic_type = "hashtag"
    topic_key = hashtag（转换为小写）
    tweet_id = 当前推文的 tweet_id
    author_username = 当前推文作者（标准化后）
    created_at = 当前推文的 created_at
    local_date = 当前推文的 local_date

### E.2 候选 2：Cashtag Topic
从 entities.cashtags 生成候选：
- 遍历每条推文的 cashtags 数组
- 对于每个非空 cashtag：
  - 不做主题过滤（默认视为资本相关）
  - 生成候选：
    topic_type = "cashtag"
    topic_key = cashtag（保持原样，不做修改）
    tweet_id = 当前推文的 tweet_id
    author_username = 当前推文作者（标准化后）
    created_at = 当前推文的 created_at
    local_date = 当前推文的 local_date

### E.3 候选 3：Domain Topic（链接域名）
从 url_domains 生成候选：
- 遍历每条推文的 url_domains 数组（C.4 中生成）
- 对于每个非空 domain：
  - 如果开启主题过滤（filter_capital_tech=True）：
    * 检查推文文本（text）是否匹配资本科技关键词
    * 如果不匹配，跳过（计入 filtered_count）
  - 生成候选：
    topic_type = "domain"
    topic_key = domain
    tweet_id = 当前推文的 tweet_id
    author_username = 当前推文作者（标准化后）
    created_at = 当前推文的 created_at
    local_date = 当前推文的 local_date

### E.4 候选 4：Center Tweet（传播中心）
定义：被其他推文 repost / quote 的推文。
生成规则：
1）统计 edges_24h 中每个 target_tweet_id 的引用次数
2）构建 tweet_map：tweet_id -> tweet（从 tweets_24h_clean）
3）对每个被引用的 target_tweet_id（count > 0）：
   - 如果开启主题过滤（filter_capital_tech=True）：
     * 从 tweet_map 中查找该推文
     * 如果推文存在：
       - 检查推文文本（text）、hashtags、cashtags 是否匹配资本科技关键词
       - 如果不匹配，跳过（计入 filtered_count）
     * 如果推文不存在：
       - 仍然生成候选（但 author_username、created_at、local_date 为空）
   - 生成候选：
     topic_type = "center_tweet"
     topic_key = target_tweet_id
     tweet_id = target_tweet_id
     author_username = 推文作者（标准化后，如果推文存在）
     created_at = 推文的 created_at（如果推文存在）
     local_date = 推文的 local_date（如果推文存在）

### E.5 候选 5：Content Keyword（内容关键词，V1 Advanced 新增）
定义：从推文内容中提取的关键词（不仅仅是 hashtag/domain/cashtag）。
生成规则：
1）对每条推文：
   - 获取 clean_text（如果不存在，使用 text）
   - 如果文本为空，跳过
   - 调用 extract_keywords_from_text() 提取关键词：
     * 提取单词（使用正则表达式 \b\w+\b，转小写）
     * 过滤停用词（扩展的停用词列表）
     * 只保留长度 > 3 的词
     * 统计词频
     * 过滤低频词（min_freq=1，但最终只保留 freq >= 2 的关键词）
     * 按频率排序，返回前 10 个关键词
2）对每个提取的关键词：
   - 如果开启主题过滤（filter_capital_tech=True）：
     * 检查关键词是否匹配资本科技关键词
     * 如果不匹配，跳过
   - 统计该关键词在所有推文中的出现频率
   - 记录包含该关键词的推文 ID 列表
3）只保留出现频率 >= 2 的关键词
4）为每个关键词生成候选：
   topic_type = "content_keyword"
   topic_key = keyword
   tweet_id = 包含该关键词的第一条推文的 tweet_id
   author_username = ""（空）
   created_at = ""（空）
   local_date = ""（空）

候选主题结构
{
  "topic_type": "hashtag|cashtag|domain|center_tweet|content_keyword",
  "topic_key": "string",
  "tweet_id": "string",
  "author_username": "string",  # 标准化后（content_keyword 为空）
  "created_at": "ISO-8601",  # content_keyword 为空
  "local_date": "YYYY-MM-DD"  # content_keyword 为空
}

输出文件：
topic_candidates_24h.jsonl
（同时输出过滤统计：Filtered out (non-capital-tech): N，Content keywords extracted: N）

---

## Step F — Topic 聚合（规则驱动聚合成"话题对象"）

目标：将候选主题聚合为完整的 Topic 统计对象。
分组规则：按 (topic_type, topic_key) 分组

统计指标：
- tweet_cnt：包含该 topic 的推文数量（去重后的 tweet_id 集合大小）
- unique_author_cnt：涉及的不同 KOL 数量（去重后的 author_username 集合大小）
- sum_like_cnt：所有相关推文的 like_count 总和
- sum_repost_cnt：所有相关推文的 repost_count 总和
- sum_reply_cnt：所有相关推文的 reply_count 总和
- sum_quote_cnt：所有相关推文的 quote_count 总和
- ref_cnt：被引用次数

特殊规则（center_tweet）：
1）unique_author_cnt：使用转发/引用该推文的不同 KOL 数量
   - 从 edges_24h 中统计：target_tweet_id -> source_author_username 集合
   - 不是统计推文作者数量，而是统计转发/引用的 KOL 数量
2）ref_cnt：来自 edges_24h 中对该推文的引用次数（target_tweet_id 出现次数）

对于其他类型（hashtag/cashtag/domain/content_keyword）：
- unique_author_cnt：统计包含该 topic 的推文的不同作者数量
- ref_cnt：统计包含该 topic 的推文被引用的总次数

输出文件：
topics_24h.jsonl
{
  "topic_type": "hashtag|cashtag|domain|center_tweet|content_keyword",
  "topic_key": "string",
  "window": "24h",
  "tweet_cnt": 0,
  "unique_author_cnt": 0,
  "sum_like_cnt": 0,
  "sum_repost_cnt": 0,
  "sum_reply_cnt": 0,
  "sum_quote_cnt": 0,
  "ref_cnt": 0
}

---

## Step F' — 语义 Topic Clustering（V1 新增）

目标：将符号级 topic 聚合成语义级 cluster，解决同一热点被拆成多个 topic 的问题。

### F'.0 输入
topics_24h
topic_candidates_24h
tweets_24h_clean
edges_24h

### F'.1 构造 Topic 文本表示
对每个 topic：
1）调用 get_topic_text() 函数构造语义文本：
   - 对于 hashtag：
     * 添加 "#{topic_key}"
     * 从 topic_candidates 中找到所有匹配的候选
     * 收集相关推文的 clean_text（限制每条 200 字符，最多 5 条）
     * 组合成文本：hashtag + clean_texts
   - 对于 domain：
     * 添加 domain（topic_key）
     * 从 topic_candidates 中找到所有匹配的候选
     * 收集相关推文的 clean_text（限制每条 200 字符，最多 5 条）
     * 组合成文本：domain + clean_texts
   - 对于 cashtag：
     * 添加 cashtag（topic_key，如果已有 $ 则保持，否则添加 $）
     * 从 topic_candidates 中找到所有匹配的候选
     * 收集相关推文的 clean_text（限制每条 200 字符，最多 5 条）
     * 组合成文本：cashtag + clean_texts
   - 对于 content_keyword：
     * 注意：代码中 get_topic_text 函数目前没有专门处理 content_keyword 类型
     * 会返回空字符串（因为 topic_type 不匹配任何已知类型）
     * 但 topic_key 本身就是关键词，在聚类时可以通过其他方式使用
     * 实际实现中，content_keyword 类型的 topic 可能不会被有效聚类
   - 对于 center_tweet：
     * 获取该推文的 clean_text（如果存在）
     * 从 edges_24h 中找到所有引用该推文的边
     * 收集引用推文的 clean_text（限制每条 200 字符，最多 5 条）
     * 组合成文本：原推文 + 引用推文

### F'.2 生成 Embedding 向量
对每个 topic 的文本表示：
1）优先使用 OpenAI embedding（如果 use_openai_embedding=True 且 API key 可用）：
   - 使用 text-embedding-3-small 模型
   - 限制文本长度为 8000 字符
   - 如果失败，使用降级方案
2）降级方案：使用 simple_text_embedding()：
   - 改进的 TF-IDF 风格向量化（256维）
   - 提取单词（使用正则表达式 \b\w+\b，转小写）
   - 过滤停用词（扩展的停用词列表）和短词（长度 > 2）
   - 统计词频
   - 计算权重：TF = log1p(freq)，长度奖励 = 1.0 + 0.1 * (len(word) - 3) if len(word) > 3 else 1.0
   - 按权重排序，取前 256 个词
   - 使用哈希函数将词映射到向量位置（hash(word) % 256）
   - 累加权重到对应位置
   - 归一化向量（L2 归一化）

### F'.3 聚类
1）如果 topics 数量 < 2 或 use_clustering=False：
   - 每个 topic 单独一个 cluster
   - 返回未聚类的 semantic_topics
2）构建 embeddings 矩阵
3）如果 sklearn 可用：
   - 使用 StandardScaler 标准化 embeddings
   - 使用 DBSCAN 聚类：
     * eps=0.4（距离阈值，更小的值 = 更严格的聚类）
     * min_samples=min_cluster_size（默认 2）
     * metric='cosine'（余弦距离）
   - 如果 DBSCAN 失败，使用降级方案
4）降级方案：使用 simple_distance_clustering()：
   - 计算余弦相似度矩阵（纯 numpy）
   - 相似度阈值：0.75（更严格的阈值）
   - 对于每个点，找到相似度 > 0.75 的点
   - 如果相似点数量 >= min_cluster_size，创建一个 cluster
   - 否则标记为噪声点（label = -1）

### F'.4 构建 Semantic Topics
1）对每个 cluster：
   - 生成 semantic_topic_id：st_{cluster_id:04d}
   - 收集所有 member topics（topic_type, topic_key）
   - 选择代表性文本（选择最长的文本，限制 500 字符）
   - 记录 cluster_size
2）对噪声点（label = -1）：
   - 每个噪声点单独一个 cluster
3）建立映射：topic_to_semantic_id：(topic_type, topic_key) -> semantic_topic_id

输出文件：
semantic_topics_24h_advanced.jsonl
{
  "semantic_topic_id": "st_0000",
  "member_topics": [
    {"topic_type": "hashtag", "topic_key": "..."},
    ...
  ],
  "representative_text": "...",
  "cluster_size": 2
}

---

## Step G' — 基于 Semantic Topic 的热度评分与 Top5（V1 新增）

目标：对 semantic topic 聚合计算 HotScore，并选择 Top5。

### G'.0 输入
topics_24h
semantic_topics_24h_advanced
topic_to_semantic_id
tweets_24h_clean
topic_candidates_24h
initial_kol_500.json（用于 KOL 影响力权重）

### G'.1 聚合 Semantic Topic 指标
对每个 semantic topic：
1）收集所有 member topics 的指标：
   - 遍历 member_topics 列表
   - 从 topics_24h 中找到对应的 topic
   - 聚合以下指标：
     * total_tweet_cnt：所有 member topics 的 tweet_cnt 总和
     * total_sum_like_cnt：所有 member topics 的 sum_like_cnt 总和
     * total_sum_repost_cnt：所有 member topics 的 sum_repost_cnt 总和
     * total_sum_reply_cnt：所有 member topics 的 sum_reply_cnt 总和
     * total_sum_quote_cnt：所有 member topics 的 sum_quote_cnt 总和
     * total_ref_cnt：所有 member topics 的 ref_cnt 总和
2）收集相关推文：
   - 从 topic_tweets_map 中获取所有 member topics 的相关推文 ID
   - 合并到 all_related_tweet_ids 集合
3）收集唯一作者：
   - 从相关推文中提取 author_username（标准化后）
   - 合并到 total_unique_authors 集合
4）计算平均指标：
   - avg_like_count = total_sum_like_cnt / total_tweet_cnt
   - avg_author_followers = 从 initial_kol_500.json 中获取相关 KOL 的 followers_count 平均值

### G'.2 计算 HotScore
对每个 semantic topic：
1）检查是否包含关键词（hashtag/domain/cashtag）：
   - 遍历 member_topics
   - 如果 topic_type ∈ {"hashtag", "domain", "cashtag"}，has_keywords = True
   - 统计 keyword_count
2）计算奖励因子：
   - multi_tweet_bonus = 1.0 + 0.2 * log1p(total_tweet_cnt - 1) if total_tweet_cnt > 1 else 1.0
   - multi_author_bonus = 1.0 + 0.3 * log1p(unique_author_cnt - 1) if unique_author_cnt > 1 else 1.0
   - keyword_bonus = 1.0 + 0.5 * log1p(keyword_count) if has_keywords else 0.5（没有关键词的降权）
3）计算 HotScore：
   HotScore = (
       1.0 * log1p(total_ref_cnt) * multi_tweet_bonus * keyword_bonus +
       1.0 * log1p(total_sum_repost_cnt + total_sum_quote_cnt) * multi_tweet_bonus * keyword_bonus +
       3.0 * unique_author_cnt * multi_author_bonus * keyword_bonus +
       0.5 * log1p(avg_like_count) * multi_tweet_bonus * keyword_bonus +
       0.3 * log1p(avg_author_followers) * multi_author_bonus * keyword_bonus +
       0.5 * log1p(total_tweet_cnt) * keyword_bonus
   )

### G'.3 Top5 选择规则
1）按 HotScore 降序排序
2）优先选择多KOL讨论和包含关键词的真实话题：
   - **第一优先级**：unique_author_cnt >= 2 且 tweet_cnt >= 2 且 has_keywords（包含 hashtag/domain/cashtag）
   - **第二优先级**：unique_author_cnt >= 1 且 tweet_cnt >= 2 且 has_keywords
   - **不再补充**：如果符合条件的不足 5 个，宁愿 Top5 少于 5 个，也要确保质量
3）最终取前 5 个

### G'.4 可读信息生成
为每个 Top5 semantic topic：
1）从 member_topics 中提取关键词：
   - hashtags：收集所有 hashtag 类型的 topic_key
   - domains：收集所有 domain 类型的 topic_key
   - cashtags：收集所有 cashtag 类型的 topic_key
   - keywords：组合成显示格式（hashtag 加 #，cashtag 加 $）
2）生成标题：
   - 如果有关键词：使用前 3 个关键词作为标题
     * 如果关键词 > 3 个："{keyword1}, {keyword2}, {keyword3} 等 {N} 个关键词"
     * 否则：", ".join(keywords)
   - 如果没有关键词：使用默认标题 "热点话题 #{rank}（{cluster_size} 个相关主题聚合）"
3）生成描述：
   - 包含 cluster_size、unique_author_cnt、tweet_cnt
   - 包含关键词信息（如果有）：
     * "标签: #hashtag1, #hashtag2；"
     * "域名: domain1, domain2；"
     * "股票: $cashtag1, $cashtag2；"
4）保存关键词信息：
   - keywords 字段：包含 hashtags、domains、cashtags、all_keywords
5）添加示例推文：
   - 从 all_related_tweet_ids 中获取推文
   - 按点赞数降序排序
   - 取前 5 条推文
   - 每条包含：tweet_id, author, text（前200字符）, like_count, created_at

输出文件:
hot_topics_top5_v1_advanced.json
{
  "generated_at": "ISO-8601",
  "window": "24h",
  "version": "V1 (Semantic Clustering)",
  "top5": [
    {
      "semantic_topic_id": "st_0000",
      "rank": 1,
      "title": "...",
      "description": "...",
      "tweet_cnt": 0,
      "unique_author_cnt": 0,
      "sum_like_cnt": 0,
      "sum_repost_cnt": 0,
      "sum_reply_cnt": 0,
      "sum_quote_cnt": 0,
      "ref_cnt": 0,
      "hot_score": 0.0,
      "member_topics": [...],
      "representative_text": "...",
      "cluster_size": 0,
      "all_related_tweet_ids": [...],
      "keywords": {
        "hashtags": [...],
        "domains": [...],
        "cashtags": [...],
        "all_keywords": [...]
      },
      "example_tweets": [...],
      "total_related_tweets": 0
    }
  ]
}

---

## Step H — 趋势判断

数据来源：
tweets_14d_clean
edges_14d
topics_24h

### H.1 构建 daily time series
按 (topic_type, topic_key, local_date) 统计：
- tweet_cnt：该日期包含该 topic 的推文数量
- unique_author_cnt：该日期涉及的不同 KOL 数量（使用 set 去重）
- sum_repost_cnt：该日期相关推文的 repost_count 总和
- ref_cnt：该日期该 topic 被引用的次数

处理逻辑：
1）从 tweets_14d_clean 中提取 hashtags、cashtags、url_domains、content_keywords
2）从 edges_14d 中提取 center_tweet 的引用关系（按日期）
3）构建 target_tweet_id -> {date: count} 映射（用于 ref_cnt 统计）

### H.2 趋势标签判定
基于：
当日值（unique_author_cnt / tweet_cnt）
前 7 日平均值

趋势标签：
Emerging
Rising
Peak
Fading
Persistent

规则（完全可执行）：
**前置条件**：unique_author_cnt >= 1 或 tweet_cnt >= 2

**Emerging**：today > 0 且 avg_7d == 0

**Rising**：today >= 1.5 * avg_7d 且 (today >= 2 或 tweet_cnt_today >= 2)

**Peak**：today >= 3 或 tweet_cnt_today >= 5，且满足以下任一条件：
- today（unique_author_cnt）是过去 7 天最大值
- tweet_cnt_today 是过去 7 天最大值

**Fading**：today <= 0.5 * avg_7d 且 avg_7d > 0

**Persistent**：0.8 * avg_7d <= today <= 1.2 * avg_7d 且 (avg_7d >= 2 或 tweet_cnt_today >= 3)

**只分析 topics_24h 中的 topic**：
- 仅对出现在 topics_24h.jsonl 中的 (topic_type, topic_key) 进行趋势分析

输出文件：
trends_14d.jsonl
{
  "topic_type": "hashtag|cashtag|domain|center_tweet|content_keyword",
  "topic_key": "string",
  "trend_label": "Emerging|Rising|Peak|Fading|Persistent",
  "today_value": 0,  # unique_author_cnt
  "avg_7d": 0.0  # 前7天 unique_author_cnt 的平均值
}

同时返回：
- topic_daily：{(topic_type, topic_key): {date: {tweet_cnt, unique_author_cnt, ...}}}
- all_dates：所有日期的排序列表

---

## Step H' — 热点发展预测（V1 Advanced 新增）

目标：预测热点话题的未来走势（grow / stabilize / fade），使用增强的特征工程。

### H'.0 输入
topics_24h
topic_daily（来自 Step H）
all_dates（来自 Step H）

### H'.1 特征工程（增强版）
对每个 topic：
1）获取最近几天的数据：
   - today = all_dates[-1]
   - yesterday = all_dates[-2]（如果存在）
   - date_3d_ago = all_dates[-4]（如果存在，否则 all_dates[0]）
   - date_7d_ago = all_dates[-8]（如果存在，否则 all_dates[0]）
2）计算基础特征：
   - today_author_cnt：今日 unique_author_cnt
   - today_tweet_cnt：今日 tweet_cnt
   - today_ref_cnt：今日 ref_cnt
   - yesterday_author_cnt：昨日 unique_author_cnt
   - yesterday_tweet_cnt：昨日 tweet_cnt
3）计算增长特征：
   - author_growth_1d = today_author_cnt - yesterday_author_cnt
   - tweet_growth_1d = today_tweet_cnt - yesterday_tweet_cnt
   - author_growth_rate_1d = author_growth_1d / yesterday_author_cnt（如果 yesterday_author_cnt > 0）
4）计算3日均值和7日均值：
   - 遍历 all_dates，如果 date < today：
     * 如果 date >= date_3d_ago：累加到 avg_3d_author、avg_3d_tweet，count_3d++
     * 如果 date >= date_7d_ago：累加到 avg_7d_author、avg_7d_tweet，count_7d++
   - avg_3d_author = sum / count_3d（如果 count_3d > 0）
   - avg_7d_author = sum / count_7d（如果 count_7d > 0）
5）计算趋势特征（增强版）：
   - momentum_3d = (today_author_cnt - avg_3d_author) / (avg_3d_author + 1)
   - momentum_7d = (today_author_cnt - avg_7d_author) / (avg_7d_author + 1)
   - volatility（波动性）：
     * 收集过去 7 天的 unique_author_cnt 值
     * 计算均值和方差
     * volatility = sqrt(variance)

### H'.2 预测逻辑（增强版）
对每个 topic：
1）初始化：
   - prediction = "stabilize"
   - confidence = 0.5
2）应用预测规则（按优先级）：
   - **grow（快速增长）**：
     * 如果 author_growth_rate_1d > 0.5 且 today_author_cnt >= 2：
       prediction = "grow"
       confidence = min(0.9, 0.5 + 0.1 * author_growth_rate_1d)
   - **grow（3天正动量）**：
     * 如果 momentum_3d > 0.3 且 today_author_cnt >= 2：
       prediction = "grow"
       confidence = min(0.85, 0.5 + 0.15 * momentum_3d)
   - **grow（7天正动量）**：
     * 如果 momentum_7d > 0.2 且 today_author_cnt >= 3：
       prediction = "grow"
       confidence = min(0.8, 0.5 + 0.1 * momentum_7d)
   - **fade（快速下降）**：
     * 如果 author_growth_rate_1d < -0.3 且 today_author_cnt < yesterday_author_cnt：
       prediction = "fade"
       confidence = min(0.9, 0.5 + 0.1 * abs(author_growth_rate_1d))
   - **fade（3天负动量）**：
     * 如果 momentum_3d < -0.2 且 today_author_cnt < avg_3d_author：
       prediction = "fade"
       confidence = min(0.85, 0.5 + 0.15 * abs(momentum_3d))
   - **fade（7天负动量）**：
     * 如果 momentum_7d < -0.15 且 today_author_cnt < avg_7d_author：
       prediction = "fade"
       confidence = min(0.8, 0.5 + 0.1 * abs(momentum_7d))
   - **stabilize（稳定）**：
     * 如果 abs(momentum_7d) < 0.1 且 today_author_cnt >= 2：
       prediction = "stabilize"
       confidence = 0.7
3）调整置信度：
   - 如果 today_author_cnt < 2：confidence *= 0.7（降低置信度）

### H'.3 输出预测结果
对每个 topic 生成预测记录：
{
  "topic_type": "hashtag|cashtag|domain|center_tweet|content_keyword",
  "topic_key": "string",
  "prediction": "grow|stabilize|fade",
  "confidence": 0.0-1.0,
  "features": {
    "today_author_cnt": 0,
    "today_tweet_cnt": 0,
    "author_growth_1d": 0,
    "author_growth_rate_1d": 0.0,
    "momentum_3d": 0.0,
    "momentum_7d": 0.0,
    "volatility": 0.0,
    "avg_3d_author": 0.0,
    "avg_7d_author": 0.0
  }
}

输出文件：
growth_predictions_24h_advanced.jsonl

---

## Step I — Daily Report 输出

目的：生成面向人类阅读的热点日报，包含预测性输出。

### I.0 输入
hot_topics_top5_v1_advanced（来自 Step G'）
trends_14d（来自 Step H）
growth_predictions_24h_advanced（来自 Step H'，可选）

### I.1 构建映射
1）构建 trend_map：(topic_type, topic_key) -> trend
2）构建 prediction_map：(topic_type, topic_key) -> prediction（如果 growth_predictions 存在）

### I.2 生成易读格式
对每个 Top5 topic：
1）构建热点信息：
   - rank, title, description, type, hot_score
   - metrics：tweet_count, author_count, total_likes, total_reposts, total_replies, total_quotes, reference_count
   - trend：label, today_value, avg_7d（如果存在）
   - example_tweets：示例推文列表（最多5条）
2）添加预测信息（V1）：
   - 如果 prediction_map 中存在该 topic：
     * prediction.outcome：prediction（"grow" | "stabilize" | "fade"）
     * prediction.confidence：confidence
     * prediction.features：features（详细特征）
3）如果是 center_tweet，添加推文链接：
   - tweet_url, tweet_author

### I.3 生成报告
1）完整结构化报告（daily_report_v1_advanced.json）：
   - generated_at, window
   - summary：
     * total_topics_analyzed：trends_14d 的长度
     * top5_hot_topics：Top5 简要信息（rank, title, description, hot_score）
   - top5_hot_topics：完整信息（包含预测）
   - trends_summary：
     * total_trends：趋势总数
     * trends_by_label：各趋势标签的数量分布
   - predictions_summary（如果存在）：
     * total_predictions：预测总数
     * predictions_by_outcome：各预测结果的数量分布（grow/stabilize/fade）
   - manual_labeling：人工标注记录（空数组，待填充）

2）简洁中文版本（daily_report_readable_v1_advanced.json）：
   - 生成时间、时间窗口、版本
   - Top5 热点话题：
     * 排名、话题、描述、热度分数
     * 推文数、参与作者数、总点赞数、总转发数
     * 趋势（或"无趋势数据"）
     * 预测（或"无预测数据"）、预测置信度

输出文件：
1）完整结构化报告：daily_report_v1_advanced.json
2）简洁中文版本：daily_report_readable_v1_advanced.json

---

## Pipeline 最终输出清单

### 基础输出（与 V0 相同）
tweets_14d_clean.jsonl
tweets_24h_clean.jsonl
edges_14d.jsonl
edges_24h.jsonl
topic_candidates_24h.jsonl（包含 content_keyword 类型）
topics_24h.jsonl（包含 content_keyword 类型）
trends_14d.jsonl（包含 content_keyword 类型）

### V1 Advanced 新增输出
semantic_topics_24h_advanced.jsonl
hot_topics_top5_v1_advanced.json
growth_predictions_24h_advanced.jsonl
daily_report_v1_advanced.json
daily_report_readable_v1_advanced.json

（可选输出：kol_all_500.jsonl, tweets_14d_kol.jsonl, tweets_24h_kol.jsonl）

---

## V1 Advanced 与 V0 的主要区别

1. **Step E**：新增 E.5 内容关键词提取
2. **Step F'**：新增语义 Topic Clustering（V1）
3. **Step G'**：新增基于 Semantic Topic 的热度评分与 Top5（V1）
4. **Step H'**：新增热点发展预测（V1 Advanced，增强特征工程）
5. **Step I**：增强的 Daily Report（包含预测信息）

所有 V0 的步骤（C, D, E.1-E.4, F, G, H, I）保持不变，V1 Advanced 在此基础上新增和增强功能。

