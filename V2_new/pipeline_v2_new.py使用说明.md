# pipeline_v2_new.py 使用说明

## 一、概述

`pipeline_v2_new.py` 是 V2 事件级聚类方案的最终实现版本，核心思想是：

**你不是在做"文本聚类"，你是在做"现实世界事件的自动归纳"。**

### 1.1 核心特点

1. **人工资产层前置**：Step 0 定义所有人工资产（Entity Dictionary, Action Verbs, Stop Words）
2. **事件候选生成受限**：entity 和 action 必须来自白名单
3. **强规则过滤升级**：更完整的黑名单和泛词表
4. **传播锚点优先**：完全结构化，权重最高
5. **结构化权重层级**：合并条件按优先级排序
6. **受限语义确认**：默认关闭，不作为自动合并依据

### 1.2 方案架构

```
Step 0: 人工资产层（代码中定义）
  ↓
Step 1: 事件候选生成（受限）
  ↓
Step 2: 强规则过滤（升级）
  ↓
Step 3: 传播锚点聚类（权重最高）
  ↓
Step 4: 增量式事件合并（结构化权重层级）
  ↓
Step 5: 受限语义确认（默认关闭）
  ↓
Step 6: 合并所有事件簇并评分
  ↓
Step 7: 可解释输出
```

## 二、环境要求

### 2.1 Python 版本
- Python 3.7+

### 2.2 依赖库
- `json`（标准库）
- `os`（标准库）
- `re`（标准库）
- `math`（标准库）
- `collections`（标准库）
- `datetime`（标准库）
- `typing`（标准库）
- `urllib.parse`（标准库，用于 URL 解析）

**无需安装额外依赖**，所有功能使用 Python 标准库实现。

## 三、输入文件

### 3.1 必需文件

1. **`tweets_24h_clean.jsonl`**
   - 清洗后的 24 小时推文数据
   - 每行一个 JSON 对象，包含：
     - `tweet_id`: 推文 ID
     - `author_username`: 作者用户名
     - `created_ts`: 创建时间戳
     - `clean_text`: 清洗后的文本
     - `text`: 原始文本
     - `entities`: 实体信息
     - `public_metrics`: 公开指标（like_count, repost_count 等）
     - `referenced_tweets`: 引用的推文列表

2. **`edges_24h.jsonl`**
   - 24 小时内的传播关系
   - 每行一个 JSON 对象，包含：
     - `source_tweet_id`: 源推文 ID
     - `target_tweet_id`: 目标推文 ID
     - `edge_type`: 边类型（reposted/quoted）

### 3.2 可选文件

3. **`initial_kol_500.json`**
   - KOL 信息（用于计算影响力权重）
   - 包含 `all` 字段，每个 KOL 包含：
     - `username`: 用户名
     - `followers_count`: 粉丝数

## 四、使用方法

### 4.1 基本用法

```bash
cd V2_new
python pipeline_v2_new.py
```

默认使用当前目录下的：
- `tweets_24h_clean.jsonl`
- `edges_24h.jsonl`
- `initial_kol_500.json`（如果存在）

### 4.2 指定输入文件

```bash
python pipeline_v2_new.py tweets_24h_clean.jsonl edges_24h.jsonl
```

### 4.3 在代码中调用

```python
from pipeline_v2_new import run_pipeline

run_pipeline(
    tweets_24h_clean_path="tweets_24h_clean.jsonl",
    edges_24h_path="edges_24h.jsonl",
    initial_kol_path="initial_kol_500.json",
    output_dir=".",
    use_semantic=False  # 默认关闭语义确认
)
```

## 五、输出文件

### 5.1 中间输出文件

1. **`event_candidates_v2_new.jsonl`**（Step 1 输出）
   - 所有事件候选
   - 每个候选包含：`event_id`, `entity`, `action`, `time`, `text`, `author`, `is_anchor` 等

2. **`event_candidates_filtered_v2_new.jsonl`**（Step 2 输出）
   - 过滤后的事件候选
   - 已排除平台域名、泛词、无实体无动作的候选

3. **`event_clusters_anchor_v2_new.jsonl`**（Step 3 输出）
   - 传播锚点事件簇
   - 每个簇包含：`cluster_id`, `cluster_type`, `weight`, `anchor_tweet`, `event_ids`, `authors` 等

4. **`event_clusters_incremental_v2_new.jsonl`**（Step 4 输出）
   - 增量式主题
   - 每个主题包含：`cluster_id`, `cluster_type`, `weight`, `event_ids`, `authors`, `merge_conditions` 等

### 5.2 最终输出文件

5. **`hot_events_top5_v2_new.json`**（Step 6 输出）
   - Top5 热点事件（完整数据）
   - 包含：`rank`, `cluster_id`, `event_score`, `author_cnt`, `tweet_cnt`, `propagation`, `engagement` 等

6. **`daily_report_v2_new.json`**（Step 7 输出）
   - 完整日报（结构化数据）
   - 包含：`top5_events`，每个事件包含 `event_title`, `why_trending`, `key_entities`, `supporting_tweets`, `decision_trace` 等

7. **`daily_report_readable_v2_new.json`**（Step 7 输出）
   - 易读版日报（中文）
   - 包含：`Top5 热点事件`，每个事件包含 `排名`, `事件标题`, `为何热门`, `关键实体`, `决策轨迹` 等

## 六、人工资产层配置

### 6.1 Entity Dictionary（实体字典）

在代码中定义，包含三类：

**A. Companies（公司）**
```python
FRONTIER_COMPANIES = {
    "OpenAI", "Anthropic", "Google", "DeepMind", "Meta", "Microsoft", ...
}
```

**B. Products / Models（产品/模型）**
```python
FRONTIER_PRODUCTS = {
    "GPT-4", "GPT-5", "ChatGPT", "Codex", "Sora", ...
}
```

**C. Infra / Concepts（基础设施/概念）**
```python
FRONTIER_CONCEPTS = {
    "LLM", "Multimodal", "MoE", "RLHF", "RLAIF", ...
}
```

**维护方法**：
- 直接在代码中修改对应的集合
- 建议定期更新，添加新的公司、产品、概念

### 6.2 Action Verbs（动作词）

在代码中定义，包含四类：

**发布 / 变化类**
```python
ACTION_RELEASE = {
    "launch", "release", "announce", "ship", "open-source", ...
}
```

**投融资**
```python
ACTION_FUNDING = {
    "raise", "funding", "invest", "acquire", "acquisition", ...
}
```

**技术进展**
```python
ACTION_TECH = {
    "benchmark", "outperform", "replace", "scale", "optimize", ...
}
```

**事件 / 风险**
```python
ACTION_EVENT = {
    "leak", "rumor", "incident", "outage", "ban", "regulation", ...
}
```

**维护方法**：
- 直接在代码中修改对应的集合
- 建议根据实际数据添加新的动作词

### 6.3 Hard Stop Words / Platform Blacklist（硬停止词/平台黑名单）

**平台 / 域名**
```python
PLATFORM_DOMAINS = {
    "google.com", "twitter.com", "x.com", "youtube.com", ...
}
```

**泛化词**
```python
HARD_STOP_WORDS = {
    "ai", "technology", "tech", "startup", "market", ...
}
```

**维护方法**：
- 直接在代码中修改对应的集合
- 建议根据实际数据添加新的平台域名和泛词

## 七、参数调整

### 7.1 传播锚点阈值

在 `step1_event_candidates_restricted` 中：

```python
is_anchor = ref_count >= 1  # 可调整
```

- 默认：`>= 1`（被引用 1 次即为锚点）
- 建议：根据数据量调整，如果数据量大可以提高到 `>= 2`

### 7.2 合并权重阈值

在 `step4_incremental_merge_weighted` 中：

```python
min_merge_weight: float = 4.0
```

- 默认：`4.0`（最低权重）
- 合并条件权重：
  - 同一 anchor: 10.0
  - 同一 entity + 同一 action: 8.0
  - 同一 entity + 时间接近: 6.0
  - 不同 KOL + 时间接近 + action 相同: 4.0

### 7.3 时间窗口

在 `check_merge_conditions_weighted` 中：

```python
max_time_diff: int = 48 * 3600  # 48 小时
```

- 默认：48 小时
- 建议：根据实际需求调整（24 小时、72 小时等）

### 7.4 语义确认

在 `run_pipeline` 中：

```python
use_semantic: bool = False  # 默认关闭
```

- 默认：关闭
- 建议：保持关闭，仅在需要时开启

## 八、常见问题

### 8.1 没有生成事件候选

**原因**：
- entity 或 action 未命中白名单
- 推文数据不符合要求

**解决方法**：
1. 检查 `event_candidates_v2_new.jsonl`，查看丢弃统计
2. 扩展 Entity Dictionary 或 Action Verbs
3. 检查输入数据格式

### 8.2 传播锚点数量为 0

**原因**：
- 传播关系数据不足
- 阈值设置过高

**解决方法**：
1. 检查 `edges_24h.jsonl` 数据
2. 降低传播锚点阈值（`ref_count >= 1`）

### 8.3 增量式主题合并过多

**原因**：
- 合并权重阈值过低
- 时间窗口过大

**解决方法**：
1. 提高 `min_merge_weight`（如改为 6.0）
2. 缩小时间窗口（如改为 24 小时）

### 8.4 输出文件为空

**原因**：
- 所有事件候选都被过滤
- 没有满足条件的簇

**解决方法**：
1. 检查 Step 1 和 Step 2 的输出
2. 放宽过滤条件（谨慎）
3. 扩展 Entity Dictionary 和 Action Verbs

## 九、最佳实践

### 9.1 人工资产层维护

1. **定期更新 Entity Dictionary**
   - 添加新的公司、产品、概念
   - 移除不再相关的实体

2. **定期更新 Action Verbs**
   - 根据实际数据添加新的动作词
   - 保持动作词的准确性

3. **定期更新 Stop Words**
   - 添加新的平台域名
   - 添加新的泛词

### 9.2 参数调优

1. **根据数据量调整阈值**
   - 数据量大：提高传播锚点阈值
   - 数据量小：降低传播锚点阈值

2. **根据业务需求调整权重**
   - 更重视传播关系：提高 anchor 权重
   - 更重视实体匹配：提高 entity+action 权重

3. **根据时间窗口调整**
   - 热点变化快：缩小时间窗口（24 小时）
   - 热点变化慢：扩大时间窗口（72 小时）

### 9.3 结果验证

1. **查看中间输出**
   - 检查 `event_candidates_v2_new.jsonl` 的丢弃统计
   - 检查 `event_clusters_anchor_v2_new.jsonl` 的锚点数量

2. **查看最终输出**
   - 检查 `daily_report_readable_v2_new.json` 的事件标题
   - 检查 `decision_trace` 的决策轨迹

3. **人工复核**
   - 每日人工复核 Top5 事件
   - 根据反馈调整规则和参数

## 十、技术细节

### 10.1 实体提取逻辑

- 使用文本匹配（大小写不敏感）
- 必须完全命中 Entity Dictionary 中的实体
- 支持多个实体（返回列表）

### 10.2 动作提取逻辑

- 使用文本匹配（大小写不敏感）
- 必须完全命中 Action Verbs 中的动作词
- 只返回第一个匹配的动作词

### 10.3 传播锚点识别

- 基于 `edges_24h.jsonl` 统计每个 tweet 被引用的次数
- 默认阈值：`>= 1`（可调整）
- 所有指向锚点的 tweet 自动属于同一事件簇

### 10.4 合并权重计算

- 同一 anchor: 10.0（最强）
- 同一 entity + 同一 action: 8.0
- 同一 entity + 时间接近: 6.0
- 不同 KOL + 时间接近 + action 相同: 4.0（最低阈值）

### 10.5 事件评分公式

```python
event_score = (
    1.0 * log1p(engagement) +
    3.0 * author_cnt +
    1.5 * log1p(propagation) +
    0.5 * log1p(tweet_cnt) +
    0.3 * log1p(avg_followers) +
    cluster_weight * 0.5  # anchor cluster 权重加成
)
```

## 十一、版本信息

- **版本**: V2 New (Event-Centric with Human Assets)
- **最后更新**: 2025-12-29
- **作者**: V2 开发团队

## 十二、联系与支持

如有问题或建议，请：
1. 查看 `V2_聚类问题分析与新方案2.md` 了解方案设计
2. 检查代码注释和文档
3. 根据实际数据调整参数和规则

