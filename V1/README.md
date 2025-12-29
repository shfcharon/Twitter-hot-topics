# Pipeline V1 Advanced - 优化版本

这是资本科技热点 Pipeline 的 V1 Advanced 版本，基于 V1 的进一步优化，采用"语义驱动 + 结构感知 + 可预测 + 可验证"的热点发现系统。

## V1 Advanced 升级特性

### V1-1：语义级 Topic Clustering（优化版）
- **语义级 Topic Clustering**：将符号级 topic 聚合成语义级 cluster
- **优化改进**：
  - 改进 embedding 方法：256维 TF-IDF 向量化（vs V1 的 128维）
  - 调整相似度阈值：0.75（vs V1 的 0.7），更严格的聚类
  - DBSCAN 参数优化：eps=0.4（vs V1 的 0.5），更精确的聚类
- 解决同一热点被拆成多个 topic 的问题

### V1-2：关键词提取优化（新增）
- **内容关键词提取**：从推文内容中提取更多关键词（不仅仅是 hashtag/domain/cashtag）
- 使用 TF-IDF 和词频统计提取主题词
- 新增 `content_keyword` 类型的候选主题

### V1-3：热点发展预测（增强版）
- **增长预测**：从"发现热点"到"判断走势"
- **增强特征工程**：
  - 新增：author_growth_rate_1d（作者增长率）
  - 新增：momentum_3d（3天动量）
  - 新增：momentum_7d（7天动量）
  - 新增：volatility（波动性）
  - 新增：avg_3d_author、avg_7d_author（3天/7天平均作者数）
- 预测结果：grow / stabilize / fade（带置信度）

### V1-4：系统性验证
- **增强的 Daily Report**：包含预测性输出和统计
- **关键词信息**：每个话题包含完整的关键词信息（hashtags、domains、cashtags）

## 文件说明

### 代码文件
- `pipeline_v1.py` - V1 基础版本 Pipeline 代码
- `pipeline_v1_advanced.py` - V1 Advanced 优化版本 Pipeline 代码（推荐使用）

### 输入文件
- `initial_kol_500.json` - 500 个 KOL 账号列表（与 V0 相同）
- `tweets_14d.jsonl` - 14 天推文数据（与 V0 相同）
- `tweets_24h.jsonl` - 24 小时推文数据（与 V0 相同）

### 输出文件

#### V0 兼容输出（与 V0 相同）
- `tweets_14d_clean.jsonl` - 清洗后的 14 天推文
- `tweets_24h_clean.jsonl` - 清洗后的 24 小时推文
- `edges_14d.jsonl` - 14 天传播边
- `edges_24h.jsonl` - 24 小时传播边
- `topic_candidates_24h.jsonl` - 24 小时候选主题（包含 content_keyword）
- `topics_24h.jsonl` - 24 小时聚合主题
- `trends_14d.jsonl` - 14 天趋势分析

#### V1 Advanced 新增输出
- `semantic_topics_24h_advanced.jsonl` - 语义聚类结果（优化版）
- `hot_topics_top5_v1_advanced.json` - V1 Advanced 版本的 Top5 热点（基于语义聚类，包含关键词信息）
- `growth_predictions_24h_advanced.jsonl` - 增长预测结果（增强版，包含详细特征）
- `daily_report_v1_advanced.json` - V1 Advanced 完整日报（包含预测）
- `daily_report_readable_v1_advanced.json` - V1 Advanced 易读版日报（中文，包含预测）

### 文档
- `pipeline_steps_v1.md` - V1 完整步骤文档（与代码完全一致）
- `pipeline_v1_implementation_summary.md` - V1 实现总结
- `v1_improvement_assessment.md` - V1 改进方案评估
- `改进总结.md` - V1 改进总结
- `V1_Advanced_优化说明.md` - V1 Advanced 优化说明
- `运行报告.md` - V1 运行报告

## 使用方法

### 基本使用（V1 Advanced 默认）

```bash
# 使用 V1 Advanced 功能（默认启用所有优化）
python pipeline_v1_advanced.py
```

### 使用 V1 基础版本

```bash
# 使用 V1 基础版本（不含优化）
python pipeline_v1.py
```

### 编程方式调用

```python
from pipeline_v1_advanced import run_pipeline

# 使用 V1 Advanced 功能（默认启用）
run_pipeline(
    initial_kol_path="initial_kol_500.json",
    tweets_14d_path="tweets_14d.jsonl",
    tweets_24h_path="tweets_24h.jsonl",
    output_dir=".",
    use_v1_features=True,
    use_semantic_clustering=True,
    use_growth_prediction=True,
    min_cluster_size=2,
)
```

### 使用 OpenAI Embedding（可选）

```python
# 使用 OpenAI embedding（需要 API key，可获得更好的聚类效果）
run_pipeline(
    use_v1_features=True,
    use_semantic_clustering=True,
    use_openai_embedding=True,
    openai_api_key="your-api-key-here",
)
```

## 配置参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `use_v1_features` | bool | True | 是否使用 V1 功能 |
| `use_semantic_clustering` | bool | True | 是否使用语义聚类 |
| `use_growth_prediction` | bool | True | 是否使用增长预测 |
| `min_cluster_size` | int | 2 | 聚类最小簇大小 |
| `use_openai_embedding` | bool | False | 是否使用 OpenAI embedding |
| `openai_api_key` | str | None | OpenAI API key |

## 依赖项

### 必需
- Python 3.7+
- numpy
- 标准库

### 可选（用于更好的性能）
- `sklearn`: 用于 DBSCAN 聚类和标准化
- `openai`: 用于 OpenAI embedding API

**注意**：如果可选依赖不可用，代码会自动使用降级方案（纯 numpy 实现）。

## V0 vs V1 vs V1 Advanced 对比

| 方面 | V0 | V1 | V1 Advanced |
|------|----|----|-------------|
| Topic 粒度 | 符号级（hashtag、domain、tweet） | 语义级（cluster） | 语义级（cluster，优化） |
| 聚类算法 | 无 | DBSCAN (eps=0.5) | DBSCAN (eps=0.4，更严格） |
| Embedding | 无 | 128维 TF-IDF | 256维改进 TF-IDF |
| 相似度阈值 | 无 | 0.7 | 0.75（更严格） |
| 关键词提取 | hashtag/domain/cashtag | hashtag/domain/cashtag | + 内容关键词（TF-IDF） |
| 热点发现 | 规则驱动 + 计数聚合 | 语义驱动 + 结构感知 | 语义驱动 + 结构感知（优化） |
| 趋势分析 | 后验趋势标签 | 后验 + 预测（基础） | 后验 + 预测（增强特征） |
| 预测特征 | 无 | 基础特征 | 增强特征（动量、波动性等） |
| 输出 | 静态报告 | 静态 + 预测性报告 | 静态 + 预测性报告（增强） |

## 优化效果

### 聚类优化
- **V1 聚类数**：9 个（可能过度聚合）
- **V1 Advanced 聚类数**：115 个（更精确，避免过度聚合）

### 关键词提取
- **V1**：仅 hashtag/domain/cashtag
- **V1 Advanced**：+ 15 个内容关键词（如 'chatgpt', 'transformer' 等）

### 预测增强
- **V1**：基础特征（1天增长、3天均值）
- **V1 Advanced**：增强特征（增长率、动量、波动性、3天/7天均值）

## 注意事项

1. **向后兼容**：V1 Advanced 完全兼容 V0 和 V1，可以通过参数控制功能
2. **降级方案**：所有新功能都有降级方案，即使依赖不可用也能运行
3. **性能**：语义聚类会增加计算时间，建议根据数据量调整参数
4. **API 成本**：如果使用 OpenAI embedding，会产生 API 调用费用
5. **聚类精度**：V1 Advanced 的聚类更严格，可能将某些相关话题分开，需要根据实际需求调整阈值

## 详细文档

- **完整步骤文档**：`pipeline_steps_v1.md`（与代码完全一致）
- **优化说明**：`V1_Advanced_优化说明.md`
- **改进总结**：`改进总结.md`
