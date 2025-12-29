# Pipeline 步骤文档修正说明

## 不一致之处及修正

### 1. C.3 文本字段标准化 - URLs 替换细节

**步骤文档中的描述**：
> 将 entities 中出现的 URL 替换为 <URL>

**代码实际实现**：
- 检查 `entities.urls` 数组
- 如果 url 是字符串，直接替换
- 如果 url 是字典，只检查 `url` 字段（代码中未检查 `expanded_url`）

**修正后的步骤描述**：
```
C.3 文本字段标准化（不改语义，只做可计算化）
目的：保留原始文本，同时生成可用于后续分析的规范化文本版本。
具体操作：
对每一条推文：
1）新增字段：raw_text：原始 text
2）构建 clean_text：
   - 从 entities.urls 中提取 URL：
     * 如果 url 是字符串，直接在 text 中替换为 <URL>
     * 如果 url 是字典，使用 url["url"] 字段在 text 中替换为 <URL>
     （注意：代码中只检查 url["url"]，不检查 expanded_url）
   - 合并连续空格为单个空格（使用正则表达式 \s+）
   - 去除首尾空格
```

### 2. Step H.2 趋势标签判定 - 阈值不一致

**步骤文档中的描述**：
> Emerging / Rising / Peak：要求 unique_author_cnt >= 2 或 tweet_cnt >= 3

**代码实际实现**：
```python
if unique_author_cnt_today >= 1 or tweet_cnt_today >= 2:
```

**修正后的步骤描述**：
```
H.2 趋势标签判定
基于：
当日值（unique_author_cnt / tweet_cnt）
前 7 日平均值

趋势标签：
Emerging
Rising
Peak
Fading
Persistent

规则（完全可执行）：
前置条件：unique_author_cnt >= 1 或 tweet_cnt >= 2
（注意：代码中已优化为更宽松的阈值）

Emerging：today > 0 且 avg_7d == 0

Rising：today >= 1.5 * avg_7d 且 (today >= 2 或 tweet_cnt_today >= 2)
（注意：代码中使用 today >= 2 或 tweet_cnt_today >= 2，而不是 today >= 3）

Peak：today >= 3 或 tweet_cnt_today >= 5，且 today 是过去 7 天最大值（unique_author_cnt）或 tweet_cnt_today 是过去 7 天最大值
（注意：代码中允许使用 unique_author_cnt 或 tweet_cnt 任一指标判断是否为最大值）

Fading：today <= 0.5 * avg_7d 且 avg_7d > 0

Persistent：0.8 * avg_7d <= today <= 1.2 * avg_7d 且 (avg_7d >= 2 或 tweet_cnt_today >= 3)
（注意：代码中使用 avg_7d >= 2 或 tweet_cnt_today >= 3，而不是仅 avg_7d >= 3）
```

### 3. Step G.1 HotScore 计算 - 公式细节

**步骤文档中的描述**：
> 根据 topic 类型采用不同公式：
> center_tweet：降权处理
> 仍保留多 KOL 参与的权重

**代码实际实现**：
- center_tweet 使用降权公式（penalty = 0.3 或 0.6）
- 其他类型使用多推文和多KOL奖励公式

**修正后的步骤描述**：
```
G.1 HotScore 计算
根据 topic 类型采用不同公式：

对于 center_tweet 类型：
- 如果 unique_author_cnt < 2：penalty = 0.3
- 如果 unique_author_cnt >= 2：penalty = 0.6
- 公式：
  HotScore = (
      0.5 * log1p(ref_cnt) * penalty +
      0.5 * log1p(sum_repost_cnt + sum_quote_cnt) * penalty +
      1.5 * unique_author_cnt +
      0.3 * log1p(avg_like_count) * penalty +
      0.2 * log1p(avg_author_followers) * penalty
  )

对于 hashtag/cashtag/domain 类型：
- 多推文奖励：multi_tweet_bonus = 1.0 + 0.2 * log1p(tweet_cnt - 1) if tweet_cnt > 1 else 1.0
- 多KOL奖励：multi_author_bonus = 1.0 + 0.3 * log1p(unique_author_cnt - 1) if unique_author_cnt > 1 else 1.0
- 公式：
  HotScore = (
      1.0 * log1p(ref_cnt) * multi_tweet_bonus +
      1.0 * log1p(sum_repost_cnt + sum_quote_cnt) * multi_tweet_bonus +
      3.0 * unique_author_cnt * multi_author_bonus +
      0.5 * log1p(avg_like_count) * multi_tweet_bonus +
      0.3 * log1p(avg_author_followers) * multi_author_bonus +
      0.5 * log1p(tweet_cnt)
  )
```

### 4. Step G.2 Top5 选择规则 - 详细逻辑

**步骤文档中的描述**：
> 1）按 HotScore 降序排序
> 2）优先保留：多 KOL、多推文
> 3）若不足 5 个，补充高分主题

**代码实际实现**：
- 详细的过滤逻辑：非 center_tweet 要求 unique_author_cnt >= 2 或 tweet_cnt >= 2
- center_tweet 要求 unique_author_cnt >= 2
- 如果不足5个，优先补充非 center_tweet 类型

**修正后的步骤描述**：
```
G.2 Top5 选择规则
1）按 HotScore 降序排序
2）优先选择多KOL讨论和多推文聚合的话题：
   - 对于 hashtag/cashtag/domain 类型：
     * 要求：unique_author_cnt >= 2 或 tweet_cnt >= 2
   - 对于 center_tweet 类型：
     * 要求：unique_author_cnt >= 2（多个KOL转发/引用）
3）如果过滤后不足 5 个：
   - 优先补充非 center_tweet 类型的高分话题
   - 如果还不够，补充其他高分话题
4）最终取前 5 个
```

### 5. Step G.3 可读信息生成 - 示例推文数量

**步骤文档中的描述**：
> 示例推文（点赞数最高的前 5 条）

**代码实际实现**：
- 按点赞数排序，取前5条
- 添加 `total_related_tweets` 字段

**修正后的步骤描述**：
```
G.3 可读信息生成
为 Top5 生成：
- title：可读的标题
- description：描述（强调多KOL参与和多推文聚合）
- example_tweets：示例推文列表
  * 按点赞数降序排序
  * 取前 5 条推文
  * 每条包含：tweet_id, author, text（前200字符）, like_count, created_at
- total_related_tweets：总推文数（新增字段）
- center_tweet 自动生成推文链接（tweet_url, tweet_author, tweet_text）
```

### 6. Step E.4 Center Tweet - 主题过滤时机

**步骤文档中的描述**：
> 2）若该推文存在：判断其内容是否符合资本科技主题
> 3）为每个符合条件的推文生成 center_tweet 候选

**代码实际实现**：
- 先统计所有 target_tweet_id 的引用次数
- 然后对每个 target_tweet_id 检查主题相关性（如果 filter_capital_tech 开启）
- 如果推文不存在（不在 tweets_24h_clean 中），仍然会创建候选（但 author_username 等字段为空）

**修正后的步骤描述**：
```
E.4 候选 4：Center Tweet（传播中心）
定义：被其他推文 repost / quote 的推文。
生成规则：
1）统计 edges_24h 中每个 target_tweet_id 的引用次数
2）对每个被引用的 target_tweet_id：
   - 若该推文存在于 tweets_24h_clean 中：
     * 判断其内容是否符合资本科技主题（如果开启过滤）
     * 如果符合或未开启过滤，生成候选
   - 若该推文不存在：
     * 仍然生成候选，但 author_username、created_at、local_date 字段为空
3）为每个符合条件的推文生成 center_tweet 候选
   topic_type = "center_tweet"
   topic_key = target_tweet_id
```

### 7. Step I - Daily Report 输出结构

**步骤文档中的描述**：
> Report 内容：
> Top5 热点话题（含热度分数与趋势）
> 关键指标统计
> 示例推文
> center_tweet 链接（若有）

**代码实际实现**：
- daily_report.json 包含：summary、top5_hot_topics、trends_summary、manual_labeling
- daily_report_readable.json 是中文简洁版本

**修正后的步骤描述**：
```
Step I — Daily Report 输出
目的：生成面向人类阅读的热点日报。

Report 内容：
1）summary：
   - total_topics_analyzed：分析的主题总数
   - top5_hot_topics：Top5 简要信息（rank, title, description, hot_score）
2）top5_hot_topics：完整信息
   - rank, title, description, type, hot_score
   - metrics：tweet_count, author_count, total_likes, total_reposts, total_replies, total_quotes, reference_count
   - trend：label, today_value, avg_7d
   - example_tweets：示例推文列表
   - center_tweet 链接（tweet_url, tweet_author，如果有）
3）trends_summary：
   - total_trends：趋势总数
   - trends_by_label：各趋势标签的数量分布
4）manual_labeling：人工标注记录（待填充）

输出文件：
1）完整结构化报告：daily_report.json
2）简洁中文版本：daily_report_readable.json
   - 生成时间、时间窗口
   - Top5 热点话题（排名、话题、描述、热度分数、推文数、参与作者数、总点赞数、总转发数、趋势）
```

## 总结

主要不一致之处：
1. **C.3 URLs 替换**：需要说明具体字段检查逻辑
2. **H.2 趋势判定阈值**：代码使用更宽松的阈值（>=1 或 >=2），而不是文档中的（>=2 或 >=3）
3. **H.2 趋势判定规则**：Rising、Peak、Persistent 的具体条件与代码不完全一致
4. **G.1 HotScore 公式**：需要详细说明两种类型的公式差异
5. **G.2 Top5 选择**：需要详细说明过滤和补充逻辑
6. **G.3 示例推文**：需要说明 total_related_tweets 字段
7. **E.4 Center Tweet**：需要说明推文不存在时的处理
8. **Step I 输出结构**：需要详细说明两个输出文件的结构

