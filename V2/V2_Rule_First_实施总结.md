# V2 Rule-First Pipeline 实施总结

## 已完成的工作

### 1. 完整流程文档
- **文件**: `V2_聚类设计蓝图_完整流程.md`
- **内容**: 详细描述了 V2 Rule-First + Human-Aligned Pipeline 的完整操作流程
- **包括**:
  - 设计思想
  - Pipeline 总览
  - 每个步骤的详细说明（E2, F2, F3, G2, I2）
  - 规则字典定义
  - 实施步骤
  - 人工复核指南

### 2. 完整代码实现
- **文件**: `pipeline_v2_rule_first.py`
- **功能**: 实现了完整的 V2 Rule-First Pipeline
- **包括**:
  - Step E2: Tweet 级事件候选生成
  - Step F2: 强规则过滤
  - Step F3: 受限语义聚类
  - Step G2: 事件级评分
  - Step I2: 可解释输出

### 3. 规则字典
代码中已定义以下规则字典（需要人工维护）：
- `PLATFORM_DOMAINS`: 平台域名列表
- `GENERIC_WORDS`: 泛词列表
- `FRONTIER_ACTION_VERBS`: 前沿动作词列表
- `TECH_PRODUCTS_WHITELIST`: 技术产品名白名单
- `COMMON_COMPANIES`: 常见公司名列表

## 运行结果

### 第一次运行（相似度阈值 0.75）
- E2: 生成了 302 个事件候选 ✅
- F2: 过滤后剩余 134 个候选 ✅
  - 过滤统计：
    - 无实体无动作: 86
    - 转推模板: 80
    - 只有URL: 1
    - 平台域名: 1
- F3: 生成了 0 个事件簇 ⚠️
  - 原因：相似度阈值 0.75 太高，没有 tweet 对通过

### 第二次运行（相似度阈值 0.65）
- F3: 仍然生成了 0 个事件簇 ⚠️
  - 原因：简单的 TF-IDF 风格 embedding 可能不够准确

## 发现的问题

### 1. 相似度阈值问题
- **问题**: 即使降低到 0.65，仍然没有 tweet 对通过相似度检查
- **原因**: 
  - 简单的 TF-IDF 风格 embedding 可能不够准确
  - 推文文本较短，相似度计算可能不够稳定
- **建议**:
  - 进一步降低阈值到 0.5 或 0.55
  - 或者改进 embedding 方法（使用更好的文本嵌入模型）
  - 或者放宽硬约束条件（允许只满足 1 个条件）

### 2. 硬约束可能过严
- **问题**: 要求满足 ≥2 个硬约束条件可能过严
- **建议**: 
  - 可以调整为满足 ≥1 个条件即可
  - 或者对不同条件设置不同权重

### 3. 聚类方法
- **当前**: 使用简单的连通分量聚类
- **建议**: 
  - 可以使用 Agglomerative Clustering（需要 sklearn）
  - 或者使用 HDBSCAN（需要 hdbscan 库）

## 下一步建议

### 1. 调整参数
修改 `pipeline_v2_rule_first.py` 中的参数：
```python
# 在 step_f3_restricted_clustering 中
similarity_threshold: float = 0.55,  # 进一步降低

# 在 check_hard_constraints 中
return len(satisfied) >= 1, satisfied  # 改为满足 ≥1 个条件
```

### 2. 改进 embedding
- 使用更好的文本嵌入模型（如 OpenAI embedding）
- 或者使用更复杂的 TF-IDF 计算

### 3. 使用更好的聚类算法
- 安装 sklearn: `pip install scikit-learn`
- 使用 Agglomerative Clustering

### 4. 人工复核
- 查看 `event_candidates_filtered_24h.jsonl`，确认过滤是否正确
- 查看相似度矩阵统计，了解为什么没有通过相似度检查
- 根据实际情况调整规则字典和阈值

## 文件清单

### 文档文件
- `V2_聚类设计蓝图_完整流程.md` - 完整操作流程文档
- `V2_Rule_First_实施总结.md` - 本文件

### 代码文件
- `pipeline_v2_rule_first.py` - 完整的 Pipeline 实现

### 输出文件（已生成）
- `event_candidates_24h.jsonl` - E2 输出
- `event_candidates_filtered_24h.jsonl` - F2 输出
- `event_clusters_24h.jsonl` - F3 输出（当前为空）
- `hot_events_top5_v2.json` - G2 输出（当前为空）
- `daily_report_v2.json` - I2 输出
- `daily_report_readable_v2.json` - I2 输出

## 总结

V2 Rule-First Pipeline 的核心思想已经完整实现：
- ✅ 先用规则限定"允许成为热点的东西"
- ✅ 再用聚类合并"相似表达"
- ✅ 最小语义单元 = 一条 tweet
- ✅ 强制可解释输出

当前需要调整的是相似度阈值和硬约束条件，以便生成实际的事件簇。建议根据实际数据特点进行调优。

