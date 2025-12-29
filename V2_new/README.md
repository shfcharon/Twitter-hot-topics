# V2_new 文件夹说明

## 一、文件夹内容

### 1.1 文档文件

1. **`V2_聚类问题分析与新方案2.md`** ⭐ **主要方案文档**
   - V2 聚类问题的完整分析与新方案设计
   - 包含完整的方案架构、详细步骤、核心创新点
   - **这是最终版的方案文档**

2. **`pipeline_v2_new.py使用说明.md`** ⭐ **使用说明文档**
   - `pipeline_v2_new.py` 的完整使用说明
   - 包含环境要求、输入文件、使用方法、参数调整、常见问题等
   - **这是代码的使用指南**

3. **`V2_聚类问题分析与新方案.md`**（历史版本）
   - 之前的方案文档，已移动到 V2_new 文件夹

4. **`V2_事件级聚类方案_实施总结.md`**（历史版本）
   - 之前的实施总结，已移动到 V2_new 文件夹

### 1.2 代码文件

1. **`pipeline_v2_new.py`** ⭐ **主要代码文件**
   - V2 事件级聚类方案的最终实现
   - 包含完整的 7 个步骤（Step 0-7）
   - **这是最终版的代码实现**

2. **`pipeline_v2_event_centric.py`**（历史版本）
   - 之前的代码实现，已移动到 V2_new 文件夹

### 1.3 输出文件

所有通过 `pipeline_v2_event_centric.py` 生成的文件已移动到 V2_new 文件夹。

## 二、核心改进

### 2.1 与之前版本的主要区别

| 方面 | V2 Event-Centric | V2 New（最终版） |
|------|-----------------|-----------------|
| **人工资产层** | 无 | ✅ Step 0 前置 |
| **entity 提取** | 开放提取 | ✅ 白名单限制 |
| **action 提取** | 开放提取 | ✅ 白名单限制 |
| **规则过滤** | 基础 | ✅ 升级（更完整） |
| **合并条件** | 等权 | ✅ 结构化权重层级 |
| **传播锚点** | 有 | ✅ 有（权重最高） |

### 2.2 关键改进点

1. **人工资产层前置（Step 0）**
   - Entity Dictionary（Companies, Products, Concepts）
   - Action Verbs（Release, Funding, Tech, Event）
   - Hard Stop Words / Platform Blacklist

2. **事件候选生成受限（Step 1）**
   - entity 必须命中 Entity Dictionary
   - action 必须命中 Action Verbs
   - 否则直接丢弃

3. **强规则过滤升级（Step 2）**
   - 更完整的平台域名黑名单
   - 更完整的泛词表
   - Hard Drop Rules（命中即丢）

4. **结构化权重层级（Step 4）**
   - 同一 anchor: 10.0（最强）
   - 同一 entity + 同一 action: 8.0
   - 同一 entity + 时间接近: 6.0
   - 不同 KOL + 时间接近 + action 相同: 4.0

## 三、使用指南

### 3.1 快速开始

1. **阅读方案文档**
   ```bash
   # 查看完整方案设计
   cat V2_聚类问题分析与新方案2.md
   ```

2. **阅读使用说明**
   ```bash
   # 查看代码使用说明
   cat pipeline_v2_new.py使用说明.md
   ```

3. **运行代码**
   ```bash
   # 确保输入文件存在
   python pipeline_v2_new.py
   ```

### 3.2 输入文件要求

- `tweets_24h_clean.jsonl`：清洗后的 24 小时推文
- `edges_24h.jsonl`：24 小时内的传播关系
- `initial_kol_500.json`：KOL 信息（可选）

### 3.3 输出文件

- `event_candidates_v2_new.jsonl`：事件候选
- `event_candidates_filtered_v2_new.jsonl`：过滤后的事件候选
- `event_clusters_anchor_v2_new.jsonl`：传播锚点事件簇
- `event_clusters_incremental_v2_new.jsonl`：增量式主题
- `hot_events_top5_v2_new.json`：Top5 热点事件
- `daily_report_v2_new.json`：完整日报
- `daily_report_readable_v2_new.json`：易读版日报

## 四、文件组织

### 4.1 推荐阅读顺序

1. **`V2_聚类问题分析与新方案2.md`** - 了解方案设计
2. **`pipeline_v2_new.py使用说明.md`** - 了解如何使用代码
3. **`pipeline_v2_new.py`** - 查看代码实现

### 4.2 历史文件

- `V2_聚类问题分析与新方案.md`：之前的方案文档
- `V2_事件级聚类方案_实施总结.md`：之前的实施总结
- `pipeline_v2_event_centric.py`：之前的代码实现

这些文件已移动到 V2_new 文件夹，供参考。

## 五、核心思想

**你不是在做"文本聚类"，你是在做"现实世界事件的自动归纳"。**

只要把这句话当成设计前提，所有问题都会自然消失。

## 六、下一步

1. **配置人工资产层**
   - 根据实际数据更新 Entity Dictionary
   - 根据实际数据更新 Action Verbs
   - 根据实际数据更新 Stop Words

2. **运行 Pipeline**
   - 准备输入文件
   - 运行 `pipeline_v2_new.py`
   - 查看输出结果

3. **人工复核**
   - 查看 `daily_report_readable_v2_new.json`
   - 根据反馈调整规则和参数

4. **迭代优化**
   - 根据实际效果调整参数
   - 根据实际数据更新人工资产层

