# 资本科技热点 Pipeline 步骤文档（修正版）

## 修正说明
本文档已根据 pipeline.py 代码实际实现进行修正，确保与代码完全一致。

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

## Step E — 候选主题生成（从爬虫字段直接派生）

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

候选主题结构
{
  "topic_type": "hashtag|cashtag|domain|center_tweet",
  "topic_key": "string",
  "tweet_id": "string",
  "author_username": "string",  # 标准化后
  "created_at": "ISO-8601",
  "local_date": "YYYY-MM-DD"
}

输出文件：
topic_candidates_24h.jsonl
（同时输出过滤统计：Filtered out (non-capital-tech): N）

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

对于其他类型（hashtag/cashtag/domain）：
- unique_author_cnt：统计包含该 topic 的推文的不同作者数量
- ref_cnt：统计包含该 topic 的推文被引用的总次数

输出文件：
topics_24h.jsonl
{
  "topic_type": "hashtag|cashtag|domain|center_tweet",
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

## Step G — 热度评分与 Top5 生成

### G.1 HotScore 计算
根据 topic 类型采用不同公式：

**对于 center_tweet 类型**：
- 如果 unique_author_cnt < 2：penalty = 0.3
- 如果 unique_author_cnt >= 2：penalty = 0.6
- 公式：
  HotScore = (
      0.5 * log1p(ref_cnt) * penalty +
      0.5 * log1p(sum_repost_cnt + sum_quote_cnt) * penalty +
      1.5 * unique_author_cnt +
      0.3 * log1p(avg_like_count) * penalty +
      0.2 * log1p(avg_author_followers) * penalty
  )

**对于 hashtag/cashtag/domain 类型**：
- 多推文奖励：multi_tweet_bonus = 1.0 + 0.2 * log1p(tweet_cnt - 1) if tweet_cnt > 1 else 1.0
- 多KOL奖励：multi_author_bonus = 1.0 + 0.3 * log1p(unique_author_cnt - 1) if unique_author_cnt > 1 else 1.0
- 公式：
  HotScore = (
      1.0 * log1p(ref_cnt) * multi_tweet_bonus +
      1.0 * log1p(sum_repost_cnt + sum_quote_cnt) * multi_tweet_bonus +
      3.0 * unique_author_cnt * multi_author_bonus +
      0.5 * log1p(avg_like_count) * multi_tweet_bonus +
      0.3 * log1p(avg_author_followers) * multi_author_bonus +
      0.5 * log1p(tweet_cnt)
  )

其中：
- avg_like_count = sum_like_cnt / tweet_cnt（如果 tweet_cnt > 0）
- avg_author_followers = 相关推文作者的平均 followers_count（从 initial_kol_500.json 中获取）

### G.2 Top5 选择规则
1）按 HotScore 降序排序
2）优先选择多KOL讨论和多推文聚合的话题：
   - 对于 hashtag/cashtag/domain 类型：
     * 要求：unique_author_cnt >= 2 或 tweet_cnt >= 2
   - 对于 center_tweet 类型：
     * 要求：unique_author_cnt >= 2（多个KOL转发/引用）
3）如果过滤后不足 5 个：
   - 优先补充非 center_tweet 类型的高分话题
   - 如果还不够，补充其他高分话题
4）最终取前 5 个

### G.3 可读信息生成
为 Top5 生成：
- rank：排名（1-5）
- title：可读的标题
  * hashtag: "#{topic_key}"
  * cashtag: "${topic_key}" 或 topic_key（如果已有$）
  * domain: topic_key
  * center_tweet: "热门推文 (@{author})" 或 "热门推文 (@{author}) - {N} 位 KOL 转发/引用"
- description：描述（强调多KOL参与和多推文聚合）
  * 根据 unique_author_cnt 和 tweet_cnt 生成不同描述
- example_tweets：示例推文列表
  * 按点赞数降序排序
  * 取前 5 条推文
  * 每条包含：tweet_id, author, text（前200字符）, like_count, created_at
- total_related_tweets：总推文数（新增字段）
- center_tweet 额外字段：tweet_author, tweet_text, tweet_url

输出文件:
hot_topics_top5.json
{
  "generated_at": "ISO-8601",
  "window": "24h",
  "top5": [...]
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
1）从 tweets_14d_clean 中提取 hashtags、cashtags、url_domains
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
（注意：代码中已优化为更宽松的阈值，不是文档中的 >= 2 或 >= 3）

**Emerging**：today > 0 且 avg_7d == 0

**Rising**：today >= 1.5 * avg_7d 且 (today >= 2 或 tweet_cnt_today >= 2)
（注意：代码中使用 today >= 2 或 tweet_cnt_today >= 2，而不是仅 today >= 3）

**Peak**：today >= 3 或 tweet_cnt_today >= 5，且满足以下任一条件：
- today（unique_author_cnt）是过去 7 天最大值
- tweet_cnt_today 是过去 7 天最大值
（注意：代码中允许使用 unique_author_cnt 或 tweet_cnt 任一指标判断是否为最大值）

**Fading**：today <= 0.5 * avg_7d 且 avg_7d > 0

**Persistent**：0.8 * avg_7d <= today <= 1.2 * avg_7d 且 (avg_7d >= 2 或 tweet_cnt_today >= 3)
（注意：代码中使用 avg_7d >= 2 或 tweet_cnt_today >= 3，而不是仅 avg_7d >= 3）

**只分析 topics_24h 中的 topic**：
- 仅对出现在 topics_24h.jsonl 中的 (topic_type, topic_key) 进行趋势分析

输出文件：
trends_14d.jsonl
{
  "topic_type": "hashtag|cashtag|domain|center_tweet",
  "topic_key": "string",
  "trend_label": "Emerging|Rising|Peak|Fading|Persistent",
  "today_value": 0,  # unique_author_cnt
  "avg_7d": 0.0  # 前7天 unique_author_cnt 的平均值
}

---

## Step I — Daily Report 输出

目的：生成面向人类阅读的热点日报。

Report 内容：
1）summary：
   - total_topics_analyzed：分析的主题总数（trends_14d 的长度）
   - top5_hot_topics：Top5 简要信息（rank, title, description, hot_score）
2）top5_hot_topics：完整信息
   - rank, title, description, type, hot_score
   - metrics：tweet_count, author_count, total_likes, total_reposts, total_replies, total_quotes, reference_count
   - trend：label, today_value, avg_7d
   - example_tweets：示例推文列表（最多5条）
   - center_tweet 链接（tweet_url, tweet_author，如果有）
3）trends_summary：
   - total_trends：趋势总数
   - trends_by_label：各趋势标签的数量分布（字典）
4）manual_labeling：人工标注记录（待填充，空数组）

输出文件：
1）完整结构化报告：daily_report.json
   {
     "generated_at": "ISO-8601",
     "window": "24h",
     "summary": {...},
     "top5_hot_topics": [...],
     "trends_summary": {...},
     "manual_labeling": []
   }
2）简洁中文版本：daily_report_readable.json
   {
     "生成时间": "YYYY-MM-DD HH:MM:SS UTC",
     "时间窗口": "24小时",
     "Top5 热点话题": [
       {
         "排名": 1,
         "话题": "...",
         "描述": "...",
         "热度分数": 0.0,
         "推文数": 0,
         "参与作者数": 0,
         "总点赞数": 0,
         "总转发数": 0,
         "趋势": "..." 或 "无趋势数据"
       }
     ]
   }

---

## Pipeline 最终输出清单

tweets_14d_clean.jsonl
tweets_24h_clean.jsonl
edges_14d.jsonl
edges_24h.jsonl
topic_candidates_24h.jsonl
topics_24h.jsonl
hot_topics_top5.json
trends_14d.jsonl
daily_report.json
daily_report_readable.json

（可选输出：kol_all_500.jsonl, tweets_14d_kol.jsonl, tweets_24h_kol.jsonl）

