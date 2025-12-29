# V2-B Improved 改进说明

## 改进内容

根据 `V2_B_运行总结.md` 中的"下一步改进方向"，实施了以下短期改进：

### 1. 改进实体提取 ✅

#### 改进前
- 只提取了简单的实体类型：tickers, hashtags, domains, mentions, companies
- 公司名只匹配常见列表（12个公司）
- 没有提取产品名、技术名

#### 改进后
- **扩展实体类型**：
  - 新增 `products`：产品名
  - 新增 `technologies`：技术名
- **改进提取方法**：
  - 使用 `extract_keywords_from_text_improved()` 从推文内容中提取关键词
  - 识别大写开头的词或全大写词（可能是产品/技术名）
  - 匹配常见技术产品名列表（GPT, ChatGPT, Claude, Gemini, LLaMA, Transformer, BERT, TensorFlow, PyTorch, CUDA, TPU, GPU, H100, A100, Blackwell 等）
  - 扩展公司名列表（从12个增加到20+个）

#### 效果
- **Entity 节点**：从 40 个增加到 **271 个**（+577%）
- **Entity-Entity 边**：从 43 条增加到 **1046 条**（+2334%）
- **实体类型更丰富**：现在包含 products 和 technologies

### 2. 改进标题生成 ✅

#### 改进前
- 只基于中心实体生成标题
- 如果没有中心实体，使用默认标题"热点议题 X"
- 很多议题的标题都是默认标题

#### 改进后
- **多级降级策略**：
  1. 优先使用中心实体（companies/products/technologies/tickers/hashtags）
  2. 如果没有中心实体，使用其他重要实体（优先 companies/products/technologies）
  3. 如果还是没有，使用关键词（从社区内推文提取）
  4. 如果还是没有，从中心推文内容提取关键词
  5. 最后才使用默认标题

- **支持新的实体类型**：
  - 支持 `products` 和 `technologies` 类型
  - 优先使用这些类型的实体作为标题

#### 效果
- **标题质量提升**：
  - 议题 2: "GPT"（基于中心实体 `technologies:GPT`）✅
  - 议题 3: "France"（基于中心实体 `products:France`）✅
  - 议题 4: "Lynx"（基于中心实体 `products:Lynx`）✅
  - 议题 5: "Gemini"（基于关键词）✅

### 3. 改进中心节点识别 ✅

#### 改进前
- 只考虑连接权重
- 没有考虑节点的度
- 没有考虑推文的 engagement
- 没有考虑实体类型的重要性

#### 改进后
- **改进中心度计算**：
  1. **连接权重**：不同类型边的权重不同
     - Tweet-Tweet 相似度边：权重 × 1.5
     - Tweet-Entity 边：权重 × 1.0
     - Entity-Entity 共现边：权重 × 1.5
  2. **节点度**：统计节点的连接数
  3. **Engagement 加成**：推文节点的 engagement（likes + reposts*2）加成 × 0.3
  4. **实体类型权重**：
     - companies: 2.0
     - products: 1.5
     - technologies: 1.3
     - tickers: 1.2
     - hashtags: 1.0
     - domains: 0.8
     - mentions: 0.5
  5. **PageRank 风格调整**：考虑邻居节点的重要性（2次迭代）

- **关键词提取**：
  - 从社区内的推文中提取关键词
  - 返回 Top5 关键词

#### 效果
- **中心实体识别更准确**：
  - 议题 1: `companies:X` ✅
  - 议题 2: `technologies:GPT` ✅
  - 议题 3: `products:France` ✅
  - 议题 4: `products:Lynx` ✅
  - 议题 5: `domains:goo.gle` ✅

## 改进效果对比

### 图结构统计

| 指标 | V2-B | V2-B Improved | 改进 |
|------|------|---------------|------|
| Entity 节点 | 40 | 271 | +577% |
| Entity-Entity 边 | 43 | 1046 | +2334% |
| Tweet-Entity 边 | 140 | 499 | +256% |

### 标题生成质量

| 议题 | V2-B | V2-B Improved |
|------|------|---------------|
| 议题 1 | "热点议题 1" | "X" ✅ |
| 议题 2 | "热点议题 2" | "GPT" ✅ |
| 议题 3 | "热点议题 3" | "France" ✅ |
| 议题 4 | "热点议题 4" | "Lynx" ✅ |
| 议题 5 | "热点议题 5" | "Gemini" ✅ |

### 实体提取质量

**V2-B**：
- 很多议题的 key_entities 都是空的
- 只有基本的实体类型

**V2-B Improved**：
- 议题 1: 包含 companies (Aws, X), domains (newscientist.com), products, technologies ✅
- 议题 2: 包含 technologies (GPT-5, ChatGPT, GPT), products (Replit, Codex) ✅
- 议题 5: 包含 technologies (ML), products (Gemini), hashtags (geminienterprise), domains (goo.gle) ✅

## 发现的问题

### 1. 实体分类不够准确
- **问题**：很多普通词被错误分类为 products（如 "Scientists", "Empire", "Phenomenal", "University", "Flex" 等）
- **原因**：关键词提取逻辑过于简单，只检查首字母大写
- **改进方向**：使用更智能的分类逻辑（如检查是否在技术产品列表中）

### 2. 关键词提取可能包含噪声
- **问题**：一些关键词可能不是真正的产品/技术名（如 "Switzerland", "Topkapi", "Charlie" 等）
- **原因**：提取逻辑可能误识别地名、人名等
- **改进方向**：使用 NER（命名实体识别）模型或更严格的过滤规则

### 3. 标题仍然不够清晰
- **问题**：一些标题仍然是单个词（如 "X", "GPT", "France", "Lynx"）
- **原因**：虽然有了中心实体，但标题生成逻辑仍然比较简单
- **改进方向**：结合推文内容生成更完整的标题（如 "GPT-5 在 Codex 中的突破"）

## 下一步改进方向

### 短期改进（已完成）
- ✅ 改进实体提取：扩展实体类型（产品名、技术名）
- ✅ 改进标题生成：多级降级策略
- ✅ 改进中心节点识别：考虑更多因素

### 进一步改进
1. **改进实体分类**：
   - 使用更智能的分类逻辑
   - 过滤掉明显不是产品/技术名的词
   - 使用技术产品名白名单

2. **改进标题生成**：
   - 结合推文内容生成更完整的标题
   - 使用 LLM 生成更清晰的标题（如果可用）

3. **改进关键词提取**：
   - 使用 NER 模型
   - 过滤掉地名、人名等非技术关键词

## 输出文件

### 基础输出（带 v2B_improved 后缀）
- `tweets_14d_clean_v2B_improved.jsonl`
- `tweets_24h_clean_v2B_improved.jsonl`
- `edges_14d_v2B_improved.jsonl`
- `edges_24h_v2B_improved.jsonl`

### V2-B Improved 特有输出
- `communities_24h_v2B_improved.jsonl` - 所有社区信息
- `hot_communities_top5_v2B_improved.json` - Top5 热点议题
- `daily_report_v2B_improved.json` - 完整日报
- `daily_report_readable_v2B_improved.json` - 易读版日报（中文）

## 总结

V2-B Improved 成功实现了以下改进：
- ✅ **实体提取**：从 40 个实体增加到 271 个，新增 products 和 technologies 类型
- ✅ **标题生成**：从默认标题改进为基于实体/关键词的标题
- ✅ **中心节点识别**：考虑更多因素，识别更准确

虽然还有一些需要进一步改进的地方（如实体分类准确性、标题清晰度），但 V2-B Improved 已经显著提升了输出质量。

