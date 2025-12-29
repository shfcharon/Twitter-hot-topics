# Pipeline V1 实现总结

## 概述

`pipeline_advanced.py` 是基于 `pipeline.py` (V0) 的完整升级版本，实现了三大核心改进：

1. **V1-1：热点聚类升级** - 语义级 Topic Clustering
2. **V1-2：热点发展预测** - 从"发现"到"判断走势"
3. **V1-3：系统性验证** - 增强的 Daily Report（包含预测性输出）

## 主要新增功能

### Step F'：语义 Topic Clustering

**功能**：将符号级 topic（hashtag、domain、center_tweet）聚合成语义级 cluster

**实现**：
- `get_topic_text()`: 为每个 topic 构造语义表示文本
- `get_embedding()`: 获取文本嵌入（支持 OpenAI API 和降级方案）
- `step_f_prime_semantic_clustering()`: 执行聚类（使用 DBSCAN 或降级方案）

**输出**：
- `semantic_topics_24h.jsonl`: 语义聚类结果
- `topic_to_semantic_id`: topic -> semantic_topic_id 映射

**降级方案**：
- 如果 OpenAI API 不可用，使用简单的 TF-IDF 风格向量化
- 如果 sklearn 不可用，使用基于余弦相似度的简单聚类

### Step G'：基于 Semantic Topic 的 HotScore

**功能**：对 semantic topic 聚合计算 HotScore

**实现**：
- `step_g_prime_semantic_hot_score()`: 聚合所有 member topics 的指标
- 使用与 V0 相同的 HotScore 公式，但基于聚合指标
- 优先选择多KOL讨论和多推文聚合的话题

**输出**：
- `hot_topics_top5_v1.json`: V1 版本的 Top5 热点

### Step H'：热点发展预测

**功能**：预测热点话题的未来走势（grow / stabilize / fade）

**实现**：
- `step_h_prime_growth_prediction()`: 基于规则 + 回归的预测
- 计算增长特征：author_growth_1d, tweet_growth_1d, acceleration 等
- 使用简单的规则预测（方案 B1）

**输出**：
- `growth_predictions_24h.jsonl`: 预测结果

**预测逻辑**：
- `grow`: 强增长（+2 authors, +2 tweets）或加速增长
- `stabilize`: 稳定活动（变化在阈值内）
- `fade`: 下降（-1 authors 或 -2 tweets）

### Step I'：增强的 Daily Report

**功能**：在原有报告基础上添加预测性输出

**新增字段**：
- `predictions_summary`: 预测结果统计
- `prediction`: 每个热点的预测信息（outcome, confidence, rationale, features）

**输出**：
- `daily_report.json`: 包含预测信息的完整报告
- `daily_report_readable.json`: 中文版本，包含预测结果

## 使用方法

### 基本使用（V0 兼容）

```python
from pipeline_advanced import run_pipeline

# 使用 V0 功能（向后兼容）
run_pipeline(
    initial_kol_path="initial_kol_500.json",
    tweets_14d_path="tweets_14d.jsonl",
    tweets_24h_path="tweets_24h.jsonl",
    use_v1_features=False,  # 禁用 V1 功能
)
```

### 使用 V1 功能

```python
# 使用 V1 功能（默认启用）
run_pipeline(
    initial_kol_path="initial_kol_500.json",
    tweets_14d_path="tweets_14d.jsonl",
    tweets_24h_path="tweets_24h.jsonl",
    use_v1_features=True,
    use_semantic_clustering=True,
    use_growth_prediction=True,
    min_cluster_size=2,
)
```

### 使用 OpenAI Embedding（可选）

```python
# 使用 OpenAI embedding（需要 API key）
run_pipeline(
    initial_kol_path="initial_kol_500.json",
    tweets_14d_path="tweets_14d.jsonl",
    tweets_24h_path="tweets_24h.jsonl",
    use_v1_features=True,
    use_semantic_clustering=True,
    use_openai_embedding=True,
    openai_api_key="your-api-key-here",
)
```

## 输出文件

### V0 输出（保持不变）
- `tweets_14d_clean.jsonl`
- `tweets_24h_clean.jsonl`
- `edges_14d.jsonl`
- `edges_24h.jsonl`
- `topic_candidates_24h.jsonl`
- `topics_24h.jsonl`
- `hot_topics_top5.json` (如果未使用 V1)
- `trends_14d.jsonl`
- `daily_report.json`
- `daily_report_readable.json`

### V1 新增输出
- `semantic_topics_24h.jsonl`: 语义聚类结果
- `hot_topics_top5_v1.json`: V1 版本的 Top5 热点
- `growth_predictions_24h.jsonl`: 增长预测结果

## 依赖项

### 必需
- Python 3.7+
- numpy
- 标准库（json, re, math, collections, datetime, urllib.parse, os）

### 可选（用于更好的性能）
- `sklearn`: 用于 DBSCAN 聚类和标准化
- `openai`: 用于 OpenAI embedding API

**注意**：如果可选依赖不可用，代码会自动使用降级方案。

## 配置参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `use_v1_features` | bool | True | 是否使用 V1 功能 |
| `use_semantic_clustering` | bool | True | 是否使用语义聚类 |
| `use_growth_prediction` | bool | True | 是否使用增长预测 |
| `min_cluster_size` | int | 2 | 聚类最小簇大小 |
| `use_openai_embedding` | bool | False | 是否使用 OpenAI embedding |
| `openai_api_key` | str | None | OpenAI API key |

## 改进效果

### V0 → V1 对比

| 方面 | V0 | V1 |
|------|----|----|
| Topic 粒度 | 符号级（hashtag、domain、tweet） | 语义级（cluster） |
| 热点发现 | 规则驱动 + 计数聚合 | 语义驱动 + 结构感知 |
| 趋势分析 | 后验趋势标签 | 后验 + 预测 |
| 输出 | 静态报告 | 静态 + 预测性报告 |

### 示例

**V0 输出**：
- Topic 1: #openai (5 tweets)
- Topic 2: openai.com (3 tweets)
- Topic 3: center_tweet_123 (2 tweets)

**V1 输出**：
- Semantic Topic 1: OpenAI 发布（聚合了 #openai、openai.com、center_tweet_123，共 10 tweets）
- 预测：grow（置信度 0.75，理由：Strong growth: +3 authors, +5 tweets）

## 注意事项

1. **向后兼容**：V1 完全兼容 V0，可以通过 `use_v1_features=False` 回退到 V0
2. **降级方案**：所有新功能都有降级方案，即使依赖不可用也能运行
3. **性能**：语义聚类会增加计算时间，建议根据数据量调整参数
4. **API 成本**：如果使用 OpenAI embedding，会产生 API 调用费用

## 未来改进方向

1. **V1-3 系统性验证**：添加离线验证（backtest）和在线验证（人工标注升级）
2. **LLM 辅助预测**：实现方案 B2（LLM 做走势判断器）
3. **更高级的聚类**：支持 HDBSCAN 或其他聚类算法
4. **特征工程**：添加更多预测特征（KOL 影响力、时间模式等）

## 总结

V1 版本成功实现了三大核心改进，将系统从"规则驱动 + 计数聚合"升级为"语义驱动 + 结构感知 + 可预测"的热点发现系统。所有功能都提供了降级方案，确保在依赖不可用时仍能正常工作。

