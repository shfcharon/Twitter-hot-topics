# V2 Pipeline 说明

## 概述

`pipeline_v2.py` 是基于 V1 Advanced 的 V2-A 方案实现，核心目标是**输出"人类理解的热点讨论议题"**，而不是简单的符号聚合（hashtag/domain/cashtag）。

## 核心改进

### 1. 修复 Hash 不稳定问题
- **V1 问题**：使用 Python 内置 `hash()`，每次运行结果不同
- **V2 解决**：使用 `hashlib.md5()`，确保 hash 值稳定

### 2. 改进聚类算法
- **V1 问题**：DBSCAN + StandardScaler + cosine，容易过度碎裂
- **V2 解决**：使用 `AgglomerativeClustering`，直接计算 cosine 距离，不进行 StandardScaler

### 3. 从符号为中心升级为事件候选为中心
- **V1**：候选对象是符号（hashtag/domain/cashtag）
- **V2**：候选对象是事件（一组 tweet_id，包含实体、关键短语）

### 4. 两阶段聚类
- **Stage-1**：Tweet 级别聚类（使用 embedding）
- **Stage-2**：Event 合并（基于共享实体和关键短语）

### 5. 事件打分（EventScore）
- 替代 HotScore
- 包含 coherence（簇内一致性），防止"拼凑簇"
- 硬过滤：author_cnt < 2 且 engagement < 50 的跳过

### 6. 更好的呈现
- **title**：实体 + 关键短语（而不是 #tag）
- **one_liner**：一句话说明争论点/事件点
- **key_entities**：公司/产品/人名/ticker
- **evidence_tweets**：按影响力排序的 5 条推文
- **why_trending**：burst + 传播链解释

## 文件结构

```
V2/
├── pipeline_v2.py              # V2 主程序
├── V2_方案说明.md               # 详细方案说明
├── README.md                    # 本文件
├── initial_kol_500.json        # 输入：KOL 列表
├── tweets_14d.jsonl            # 输入：14天推文
├── tweets_24h.jsonl           # 输入：24小时推文
├── tweets_14d_clean.jsonl      # 输出：清洗后的14天推文
├── tweets_24h_clean.jsonl     # 输出：清洗后的24小时推文
├── edges_14d.jsonl            # 输出：14天传播边
├── edges_24h.jsonl            # 输出：24小时传播边
├── event_candidates_24h.jsonl  # 输出：事件候选（V2新增）
├── events_24h.jsonl            # 输出：聚类后的事件（V2新增）
├── hot_events_top5_v2.json    # 输出：Top5热点事件（V2新增）
├── trends_14d.jsonl           # 输出：14天趋势
├── daily_report_v2.json        # 输出：完整日报（V2新增）
└── daily_report_readable_v2.json  # 输出：易读版日报（V2新增）
```

## 使用方法

```python
from pipeline_v2 import run_pipeline

run_pipeline(
    initial_kol_path="initial_kol_500.json",
    tweets_14d_path="tweets_14d.jsonl",
    tweets_24h_path="tweets_24h.jsonl",
    output_dir=".",
    use_v2_features=True,  # 使用 V2 功能
    min_cluster_size=2,
    use_openai_embedding=False,  # 可选：使用 OpenAI embedding
    openai_api_key=None,  # 可选：OpenAI API key
)
```

或者直接运行：

```bash
cd V2
python3 pipeline_v2.py
```

## 输出示例

### hot_events_top5_v2.json

```json
{
  "generated_at": "2025-12-29T02:56:11.569023+00:00",
  "window": "24h",
  "version": "V2 (Event-Driven)",
  "top5": [
    {
      "event_id": "ev_0001",
      "tweet_ids": ["2003645819497623665", "2003674789110771948"],
      "entities": {
        "tickers": [],
        "hashtags": [],
        "domains": [],
        "mentions": ["gdb"],
        "companies": []
      },
      "key_phrases": ["gdb chatgpt", "chatgpt for health", ...],
      "author_cnt": 2,
      "tweet_cnt": 2,
      "engagement": 585.5,
      "event_score": 15.79,
      "rank": 1
    }
  ]
}
```

### daily_report_readable_v2.json

```json
{
  "生成时间": "2025-12-29 02:56:11 UTC",
  "时间窗口": "24小时",
  "版本": "V2 (事件驱动版本)",
  "Top5 热点事件": [
    {
      "排名": 1,
      "事件": "gdb chatgpt",
      "一句话描述": "ChatGPT for health:",
      "事件分数": 15.79,
      "参与作者数": 2,
      "推文数": 2,
      "总互动量": 585.5,
      "传播强度": 1,
      "簇内一致性": 0.886,
      "关键实体": {...},
      "为何热门": "跨作者传播 1 次；总互动量 585.5"
    }
  ]
}
```

## V2 vs V1 对比

| 方面 | V1 Advanced | V2 |
|------|-------------|-----|
| **候选对象** | 符号（hashtag/domain/cashtag） | 事件候选（一组 tweet_id） |
| **聚类对象** | Topic（符号） | Event（事件） |
| **Hash 函数** | Python 内置 hash（不稳定） | hashlib.md5（稳定） |
| **聚类算法** | DBSCAN + StandardScaler + cosine | AgglomerativeClustering + cosine（无 StandardScaler） |
| **聚类阶段** | 单阶段 | 两阶段（Tweet→Event→Merge） |
| **打分方式** | HotScore（基于 topic） | EventScore（基于 event，包含 coherence） |
| **标题生成** | 关键词列表 | 实体 + 关键短语 |
| **描述** | 统计信息 | one_liner（一句话说明） |
| **输出内容** | 符号聚合 | 真实讨论议题 |

## 技术细节

### Hash 稳定性修复

**V1**：
```python
hash_val = hash(word) % 256  # 不稳定
```

**V2**：
```python
hash_obj = hashlib.md5(word.encode('utf-8'))
hash_val = int(hash_obj.hexdigest(), 16) % 256  # 稳定
```

### 聚类算法改进

**V1**：
```python
scaler = StandardScaler()
embeddings_scaled = scaler.fit_transform(embeddings_matrix)
clustering = DBSCAN(eps=0.4, min_samples=min_cluster_size, metric='cosine')
```

**V2**：
```python
# 不进行 StandardScaler
clustering = AgglomerativeClustering(
    n_clusters=None,
    distance_threshold=0.3,  # cosine distance threshold
    linkage='average',
    metric='cosine'
)
```

## 注意事项

1. **依赖**：
   - 基础：`numpy`, `json`, `re`, `math`, `collections`, `datetime`, `urllib.parse`
   - 可选：`sklearn`（用于 AgglomerativeClustering），`openai`（用于 OpenAI embedding）

2. **性能**：
   - 如果数据量很大，建议使用 OpenAI embedding 或更高效的 embedding 方法
   - 两阶段聚类可能较慢，可以通过调整 `min_cluster_size` 和 `distance_threshold` 来优化

3. **过滤条件**：
   - 当前硬过滤：`author_cnt < 2 且 engagement < 50` 的事件会被跳过
   - 如果输出事件太少，可以适当放宽过滤条件

## 更多信息

详细方案说明请参考 `V2_方案说明.md`。

