# V1 Topic-Focused 版本说明

## 概述

`pipeline_v1_topic_focused.py` 是基于 `pipeline_v1_advanced.py` 的增强版本，核心改进是**从推文内容中提取真实的热点讨论话题**，而不仅仅是聚合的标签或网站。

## 核心问题

V0 和 V1 Advanced 版本的 Top5 和 Daily Report 输出主要是：
- 简单的关键词列表（如 `"newscientist.com"`、`"#AI"`）
- 统计信息（如 `"1 位 KOL 参与讨论，共 17 条推文"`）

**用户期望**：Top5 和 Daily Report 应该反映**真实的热点讨论话题**，例如：
- "AI公司因版权问题被起诉"
- "新量子计算技术取得重大突破"
- "某科技公司发布新产品引发广泛关注"

## 核心改进

### 1. 话题提取功能（`extract_topic_from_tweets`）

新增函数，从推文内容中提取真实话题信息：

**功能**：
- 分析最热门的推文（按点赞+转发排序）
- 识别事件类型：
  - `invention`: 发明/创造（关键词：invent, create, develop, launch, release）
  - `announcement`: 公告/发布（关键词：announce, reveal, unveil, introduce）
  - `controversy`: 争议/法律问题（关键词：sue, lawsuit, legal, copyright, dispute）
  - `funding`: 融资/收购（关键词：funding, raise, investment, IPO, acquisition）
  - `trend`: 趋势（关键词：trend, growing, increasing, popular）
  - `breakthrough`: 突破（关键词：breakthrough, milestone, achievement）
- 提取关键实体（公司名、产品名等）
- 生成话题标题和摘要

**输出**：
```python
{
    "topic_title": "OpenAI, Anthropic 相关争议/法律问题",  # 或基于推文内容
    "topic_summary": "多位 KOL 讨论：Big AI firms have built their models...",
    "key_entities": ["OpenAI", "Anthropic", "AI"],
    "event_type": "controversy",
    "core_tweet_text": "Big AI firms have built their models..."
}
```

### 2. 标题和描述生成优化

**之前（V1 Advanced）**：
- 标题：`"newscientist.com 等 1 个关键词"`
- 描述：`"1 位 KOL 参与讨论，共 17 条推文。域名: newscientist.com"`

**现在（V1 Topic-Focused）**：
- 标题：`"AI公司因版权问题被起诉"`（从推文内容提取）
- 描述：`"1 位 KOL 参与讨论，共 17 条推文。核心内容：Big AI firms have built their models by hoovering up copyrighted material..."`

### 3. 话题信息保存

每个 Top5 话题现在包含 `topic_info` 字段：
```json
{
    "topic_info": {
        "event_type": "controversy",
        "key_entities": ["OpenAI", "Anthropic"],
        "core_tweet_text": "..."
    }
}
```

## 技术实现

### 话题提取策略

1. **分析最热门推文**：按 `like_count + repost_count * 2` 排序，取前10条
2. **事件类型识别**：使用关键词匹配，统计每种事件类型的出现频率
3. **实体提取**：
   - 匹配常见公司名（OpenAI, Anthropic, Google, Microsoft 等）
   - 提取大写字母开头的词（可能是公司/产品名）
4. **标题生成**：
   - 优先使用提取的话题标题（基于事件类型和实体）
   - 如果没有提取到，回退到关键词列表
   - 如果都没有，使用核心推文的前80个字符

### 与 V1 Advanced 的兼容性

- **保留所有 V1 Advanced 功能**：
  - 语义聚类
  - 内容关键词提取
  - 趋势预测
- **仅增强标题和描述生成**：
  - 在 `step_g_prime_semantic_hot_score` 中添加话题提取
  - 在 `step_i_daily_report` 中添加 `topic_info` 字段

## 输出文件

所有输出文件使用 `_topic_focused` 后缀，避免与 V1 Advanced 冲突：

- `hot_topics_top5_v1_topic_focused.json`
- `semantic_topics_24h_topic_focused.jsonl`
- `growth_predictions_24h_topic_focused.jsonl`
- `daily_report_v1_topic_focused.json`
- `daily_report_readable_v1_topic_focused.json`

## 使用方式

```python
from pipeline_v1_topic_focused import run_pipeline

run_pipeline(
    initial_kol_path="initial_kol_500.json",
    tweets_14d_path="tweets_14d.jsonl",
    tweets_24h_path="tweets_24h.jsonl",
    output_dir=".",
    use_v1_features=True,
    use_semantic_clustering=True,
    use_growth_prediction=True,
)
```

## 示例输出对比

### V1 Advanced 输出示例
```json
{
    "title": "newscientist.com",
    "description": "1 位 KOL 参与讨论，共 17 条推文。域名: newscientist.com"
}
```

### V1 Topic-Focused 输出示例
```json
{
    "title": "AI公司因版权问题被起诉",
    "description": "1 位 KOL 参与讨论，共 17 条推文。核心内容：Big AI firms have built their models by hoovering up copyrighted material from the internet as training data...",
    "topic_info": {
        "event_type": "controversy",
        "key_entities": ["AI", "firms"],
        "core_tweet_text": "Big AI firms have built their models..."
    }
}
```

## 局限性

1. **规则基础**：话题提取使用规则和关键词匹配，不是真正的NLP理解
2. **语言限制**：主要针对英文推文，中文推文可能需要额外处理
3. **实体识别**：实体提取较简单，可能遗漏一些重要实体
4. **标题质量**：在某些情况下，标题可能不够准确或不够吸引人

## 未来改进方向

1. **使用LLM**：集成 OpenAI GPT 或其他 LLM 来生成更准确的话题标题和摘要
2. **多语言支持**：增强对中文、日文等多语言推文的处理
3. **更智能的实体识别**：使用 NER（命名实体识别）模型
4. **话题分类**：更细粒度的话题分类（技术突破、商业动态、政策变化等）

## 与 V0、V1 Advanced 的关系

```
V0 (基础版本)
  ↓
V1 Advanced (语义聚类 + 预测)
  ↓
V1 Topic-Focused (话题聚焦版本)
```

- **V0**：基础功能，符号级话题（hashtag/domain/cashtag）
- **V1 Advanced**：语义聚类，内容关键词，趋势预测
- **V1 Topic-Focused**：在 V1 Advanced 基础上，增强话题提取和描述生成

## 总结

V1 Topic-Focused 版本的核心价值是**让 Top5 和 Daily Report 更贴近用户需求**，从"聚合的标签"升级到"真实的热点讨论话题"，使输出更有意义、更易理解、更符合实际使用场景。

