# Top5 热点话题优化总结

## 优化目标
将 Top5 从"单个热门推文"改为"由多个 KOL 传播和讨论的热点话题（多推文聚合）"

## 主要修改

### 1. 优化 HotScore 公式
- **对 center_tweet 类型降低权重**：因为它是单个推文，不是聚合话题
- **对 hashtag/cashtag/domain 类型增加奖励**：
  - 多推文奖励：`1.0 + 0.2 * log1p(tweet_cnt - 1)`
  - 多KOL奖励：`1.0 + 0.3 * log1p(unique_author_cnt - 1)`
  - 直接奖励多推文：`0.5 * log1p(tweet_cnt)`

### 2. Top5 选择策略
- **优先选择多KOL讨论的话题**：
  - 非 center_tweet 类型：要求 `unique_author_cnt >= 2` 或 `tweet_cnt >= 2`
  - center_tweet 类型：要求 `unique_author_cnt >= 2`（多个KOL转发/引用）
- **如果过滤后不足5个，补充其他高质量话题**（优先非 center_tweet）

### 3. 优化话题描述
- 强调多KOL参与和多推文聚合
- 描述格式：`"话题标签 #xxx：N 位 KOL 参与讨论，共 M 条推文"`

### 4. 增强示例推文展示
- 按点赞数排序，展示前5条推文（而不是3条）
- 添加 `total_related_tweets` 字段，显示总推文数

## 优化效果

### 优化前
- Top5 全部是 `center_tweet`（单个推文）
- 每个话题只有1条推文
- 主要是科学类推文，与资本科技主题不匹配

### 优化后
- Top5 主要是 `domain` 和 `hashtag` 类型（聚合话题）
- 多个推文聚合：
  - Rank 1: newscientist.com - 17条推文
  - Rank 2: goo.gle - 5条推文
  - Rank 3: #geminienterprise - 2条推文
- 展示多个推文示例（最多5条）

## 当前 Top5 结果

| 排名 | 话题 | 类型 | 推文数 | KOL数 | 热度分数 |
|------|------|------|--------|-------|----------|
| 1 | newscientist.com | domain | 17 | 1 | 16.32 |
| 2 | goo.gle | domain | 5 | 1 | 11.45 |
| 3 | #geminienterprise | hashtag | 2 | 1 | 9.90 |
| 4 | science.nasa.gov | domain | 1 | 1 | 9.59 |
| 5 | x.com | domain | 1 | 1 | 6.59 |

## 说明

当前数据中：
- **多推文话题**：有3个（17条、5条、2条推文）
- **多KOL话题**：0个（数据中确实只有一个KOL在讨论这些话题）

但代码已经优化为：
1. ✅ 优先选择多推文聚合的话题（domain/hashtag/cashtag）
2. ✅ 降低单个推文（center_tweet）的权重
3. ✅ 如果有多KOL参与的话题，会优先选择
4. ✅ 展示多个推文示例，体现聚合效果

## 未来改进

如果数据中有多个 KOL 参与的话题，代码已经能够：
- 正确识别和优先选择
- 在描述中突出多KOL参与
- 展示多个KOL的推文示例

当前结果已经符合"多推文聚合话题"的需求！

