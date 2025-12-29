# V2-B 方案说明文档

## 概述

`pipeline_v2_B.py` 是基于 V2 的 V2-B 方案实现，核心思想是**构建多层图（Heterogeneous Graph）并使用社区发现算法**，让聚类天然偏向"讨论共同体"，而不是符号聚合。

## 核心思想

### 为什么 V2-B？

V2-A 虽然从符号升级为事件候选，但仍然存在以下问题：
1. **标题生成不够清晰**：退化为关键短语或包含无意义内容
2. **实体提取不足**：很多事件的实体都是空的
3. **无法识别"讨论共同体"**：缺少"谁在讨论 + 怎么传播"的结构
4. **无法回答"发生了什么"**：输出更像是"推文聚合"，而不是"事件/议题"

V2-B 通过**讨论图谱 + 社区发现**解决这些问题：
- 构建多层图，将"谁在讨论"、"怎么传播"、"讨论内容相似"三件事绑定在一起
- 使用社区发现算法识别"讨论团体"
- 基于社区的中心节点生成更清晰的标题和描述

## 多层图（Heterogeneous Graph）结构

### 节点（Nodes）

1. **Tweet 节点**：每条推文
2. **Author 节点**：每个 KOL（Key Opinion Leader）
3. **Entity 节点**：实体（公司/产品/人名/ticker/hashtag/domain/关键短语）

### 边（Edges）

1. **Tweet—Tweet 边**：
   - 基于 embedding 相似度
   - 相似度 > 阈值（默认 0.7）的推文之间建立边
   - 权重 = 余弦相似度

2. **Author—Tweet 边**：
   - 发帖关系
   - 权重 = 发帖次数（通常为 1）

3. **Tweet—Entity 边**：
   - 提及关系
   - 推文中出现的实体（hashtag/cashtag/domain/公司名等）
   - 权重 = 提及次数

4. **Author—Author 边**：
   - 传播关系（repost/quote）
   - 如果作者 A 转发/引用作者 B 的推文，建立边
   - 权重 = 传播次数

5. **Entity—Entity 边**：
   - 共现关系
   - 如果两个实体在同一推文中出现，建立边
   - 权重 = 共现次数

## 社区发现（Community Detection）

### 算法

使用**简化的 Louvain 算法**（纯 Python 实现，不依赖 networkx 或 leidenalg）：

1. **初始化**：每个节点一个社区
2. **迭代优化**：
   - 对每个节点，尝试移动到邻居节点的社区
   - 计算模块度（Modularity）的变化
   - 如果模块度提高，移动节点
3. **收敛**：直到没有节点可以移动或达到最大迭代次数

### 模块度（Modularity）

模块度衡量社区划分的质量：
- 社区内部的连接应该比随机连接更密集
- 社区之间的连接应该比随机连接更稀疏

公式：
```
Q = (1/2m) * Σ[A_ij - (k_i * k_j)/(2m)] * δ(c_i, c_j)
```
其中：
- `A_ij`：节点 i 和 j 之间的边权重
- `k_i`：节点 i 的度（所有边的权重和）
- `m`：所有边的权重和
- `δ(c_i, c_j)`：如果节点 i 和 j 在同一社区则为 1，否则为 0

### 输出

社区 = 议题 cluster，每个社区包含：
- 一组相关的推文
- 参与讨论的 KOL
- 相关的实体（公司/产品/ticker/hashtag等）

## 社区评分和 Top5 选择

### 社区分数（Community Score）

```
CommunityScore = w1*log(engagement) + w2*author_cnt + w3*propagation + w4*log(tweet_cnt) + w5*log(avg_followers)
```

其中：
- **engagement**：总互动量（likes + reposts*2 + replies*0.5 + quotes*1.5）
- **author_cnt**：参与讨论的不同 KOL 数量
- **propagation**：跨作者传播强度（edges 中"跨作者传播"次数）
- **tweet_cnt**：推文数量
- **avg_followers**：平均 KOL 粉丝数

### 硬过滤

- `author_cnt < 2 且 engagement < 50`：跳过

### Top5 选择

按 CommunityScore 降序排序，取前 5 个社区。

## 社区呈现（基于中心节点）

### 中心节点识别

对每个社区，找到：
1. **最中心的实体节点**：基于连接权重（与 tweet 的连接 + 与其他 entity 的共现）
2. **最中心的 tweet 节点**：基于连接权重（与其他 tweet 的相似度 + 与 entity 的连接）

### 标题生成

基于中心实体和中心推文生成标题：
1. 优先使用中心实体（公司名/ticker/hashtag）
2. 如果没有中心实体，使用其他重要实体
3. 如果都没有，使用默认标题

### 描述生成

1. **one_liner**：从中心推文或最热门的推文中提取前 150 个字符
2. **key_entities**：收集社区内的关键实体（companies/tickers/hashtags/domains）
3. **evidence_tweets**：按影响力排序的 5 条推文
4. **why_trending**：burst + 传播链解释

## 为什么 V2-B 更像"热点讨论"？

### V1/V2-A 的问题

- 只有"内容相似 + 符号聚合"
- 缺少"共同体结构"
- 无法识别"谁在讨论"、"怎么传播"

### V2-B 的优势

1. **绑定三件事**：
   - "谁在讨论"（Author 节点和 Author-Author 边）
   - "怎么传播"（Author-Author 传播边）
   - "讨论内容相似"（Tweet-Tweet 相似度边）

2. **识别讨论共同体**：
   - 社区发现算法天然识别"讨论团体"
   - 社区内的节点（推文、作者、实体）都是相关的

3. **更好的标题和描述**：
   - 基于社区的中心节点（最中心的实体 + 最中心的 tweet）
   - 可以更好地理解"发生了什么"

## Pipeline 流程

### Step C: ETL 清洗与标准化
- 账号全集校验
- 时间字段标准化
- 文本字段标准化
- entities 标准化
- 结构化去重

### Step D: 传播关系派生
- 构建传播边（repost/quote）

### Step E: 构建多层图
1. 添加 Tweet 节点（计算 embedding）
2. 添加 Author 节点（从推文中提取）
3. 添加 Entity 节点（从推文中提取实体）
4. 构建 Tweet-Tweet 相似度边
5. 构建 Author-Tweet 发帖边
6. 构建 Tweet-Entity 提及边
7. 构建 Author-Author 传播边
8. 构建 Entity-Entity 共现边

### Step F: 社区发现
1. 使用简化的 Louvain 算法
2. 迭代优化模块度
3. 输出社区（议题 cluster）

### Step G: 社区评分和 Top5 选择
1. 为每个社区计算指标（engagement, author_cnt, propagation等）
2. 计算 CommunityScore
3. 硬过滤（author_cnt < 2 且 engagement < 50）
4. 按分数排序，取 Top5

### Step I: 社区呈现
1. 找到社区的中心节点（最中心的实体 + 最中心的 tweet）
2. 生成标题（基于中心实体）
3. 生成描述（基于中心推文）
4. 收集关键实体和证据推文
5. 生成 why_trending 解释

## 输出文件

### 基础输出（带 v2B 后缀）
- `tweets_14d_clean_v2B.jsonl`
- `tweets_24h_clean_v2B.jsonl`
- `edges_14d_v2B.jsonl`
- `edges_24h_v2B.jsonl`

### V2-B 特有输出
- `communities_24h_v2B.jsonl` - 所有社区信息
- `hot_communities_top5_v2B.json` - Top5 热点议题
- `daily_report_v2B.json` - 完整日报
- `daily_report_readable_v2B.json` - 易读版日报（中文）

## 使用方式

```python
from pipeline_v2_B import run_pipeline

run_pipeline(
    initial_kol_path="initial_kol_500.json",
    tweets_14d_path="tweets_14d.jsonl",
    tweets_24h_path="tweets_24h.jsonl",
    output_dir=".",
    similarity_threshold=0.7,  # Tweet-Tweet 相似度阈值
    use_openai_embedding=False,  # 可选：使用 OpenAI embedding
    openai_api_key=None,  # 可选：OpenAI API key
)
```

或者直接运行：

```bash
cd V2
python3 pipeline_v2_B.py
```

## V2-B vs V2-A 对比

| 方面 | V2-A | V2-B |
|------|------|------|
| **聚类方法** | 两阶段聚类（Tweet→Event→Merge） | 社区发现（Louvain） |
| **图结构** | 无 | 多层图（Heterogeneous Graph） |
| **节点类型** | 无 | Tweet, Author, Entity |
| **边类型** | 无 | Tweet-Tweet, Author-Tweet, Tweet-Entity, Author-Author, Entity-Entity |
| **标题生成** | 实体 + 关键短语 | 基于社区中心节点（最中心的实体 + 最中心的 tweet） |
| **识别讨论共同体** | 否 | 是（通过社区发现） |
| **绑定"谁在讨论 + 怎么传播"** | 否 | 是（通过 Author-Author 边） |

## 技术细节

### 图结构实现

使用纯 Python 实现，不依赖 networkx：
- 节点集合：使用 `set` 存储
- 边集合：使用 `dict` 存储权重
- 节点属性：使用 `dict` 存储

### 社区发现实现

使用简化的 Louvain 算法：
- 贪心优化：迭代移动节点到能提高模块度的社区
- 模块度计算：基于边权重和节点度
- 收敛条件：没有节点可以移动或达到最大迭代次数

### 中心节点识别

基于连接权重计算中心度：
- **实体中心度**：与 tweet 的连接权重 + 与其他 entity 的共现权重
- **Tweet 中心度**：与其他 tweet 的相似度 + 与 entity 的连接权重

## 预期效果

### V2-A 输出示例
```json
{
  "title": "gdb chatgpt",
  "one_liner": "ChatGPT for health:",
  "key_entities": {
    "companies": [],
    "tickers": [],
    "hashtags": [],
    "domains": []
  }
}
```

### V2-B 输出示例（预期）
```json
{
  "title": "OpenAI / ChatGPT",
  "one_liner": "OpenAI announces ChatGPT for health applications, sparking discussion on AI in healthcare...",
  "key_entities": {
    "companies": ["OpenAI"],
    "tickers": [],
    "hashtags": ["ai", "healthcare"],
    "domains": []
  },
  "center_entity": "companies:OpenAI",
  "center_tweet": "2003645819497623665",
  "why_trending": "3 位 KOL 参与讨论；跨作者传播 5 次；总互动量 585"
}
```

## 优势总结

1. ✅ **识别讨论共同体**：通过社区发现算法，天然识别"讨论团体"
2. ✅ **绑定三件事**："谁在讨论"、"怎么传播"、"讨论内容相似"
3. ✅ **更好的标题和描述**：基于社区的中心节点，更清晰地表达"发生了什么"
4. ✅ **更好的实体提取**：通过图结构，可以更好地识别实体之间的关系
5. ✅ **更接近"研究员写的 daily brief"**：输出更像真正的"事件/议题"

## 注意事项

1. **性能**：
   - 图构建和社区发现可能较慢（特别是推文数量多时）
   - 可以通过调整 `similarity_threshold` 来减少 Tweet-Tweet 边的数量

2. **社区发现算法**：
   - 当前使用简化的 Louvain 算法（纯 Python 实现）
   - 如果需要更准确的社区发现，可以安装 `networkx` 和 `leidenalg` 使用标准算法

3. **中心节点识别**：
   - 当前使用简单的中心度计算（基于连接权重）
   - 可以改进为更复杂的中心度指标（如 PageRank、Betweenness Centrality 等）

4. **实体提取**：
   - 当前使用简单的规则提取实体（公司名匹配、hashtag/cashtag/domain提取）
   - 可以改进为使用 NER（命名实体识别）模型

## 总结

V2-B 通过**讨论图谱 + 社区发现**，实现了从"推文聚合"到"热点议题"的升级：

1. **构建多层图**：将推文、作者、实体组织成图结构
2. **社区发现**：识别"讨论共同体"
3. **中心节点**：找到社区的核心实体和推文
4. **标题生成**：基于中心节点生成更清晰的标题和描述

最终输出的是**"人类理解的热点讨论议题"**，可以回答"发生了什么"、"有什么影响"等问题。

