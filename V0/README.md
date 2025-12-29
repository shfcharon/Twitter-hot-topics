# Pipeline V0 - 基础版本

这是资本科技热点 Pipeline 的基础版本（V0），采用"规则驱动 + 计数聚合 + 排序筛选"的热点发现系统。

## 文件说明

### 代码文件
- `pipeline.py` - 主 Pipeline 代码（Step C - Step I）
- `100seed.py` - 从候选池中选出 100 个种子账号
- `expansion_candidates.py` - 生成扩展候选账号
- `kol_500.py` - 构建最终的 500 个 KOL 池

### 输入文件
- `candidate_pool.json` - 候选账号池（来自爬虫）
- `initial_kol_500.json` - 500 个 KOL 账号列表
- `tweets_14d.jsonl` - 14 天推文数据（来自爬虫）
- `tweets_24h.jsonl` - 24 小时推文数据（来自爬虫）
- `edges_following.jsonl` - 关注关系边（可选）
- `edges_mentions.jsonl` - 提及关系边（可选）
- `edges_interactions.jsonl` - 交互关系边（可选）

### 输出文件
- `tweets_14d_clean.jsonl` - 清洗后的 14 天推文
- `tweets_24h_clean.jsonl` - 清洗后的 24 小时推文
- `edges_14d.jsonl` - 14 天传播边
- `edges_24h.jsonl` - 24 小时传播边
- `topic_candidates_24h.jsonl` - 24 小时候选主题
- `topics_24h.jsonl` - 24 小时聚合主题
- `hot_topics_top5.json` - Top5 热点话题
- `trends_14d.jsonl` - 14 天趋势分析
- `daily_report.json` - 完整日报
- `daily_report_readable.json` - 易读版日报（中文）

### 文档
- `pipeline_evaluation.md` - Pipeline 评估报告
- `pipeline_fixes_summary.md` - 修复总结
- `pipeline_steps_corrected.md` - 修正后的步骤文档
- `pipeline_steps_corrections.md` - 步骤修正说明
- `pipeline_top5_optimization.md` - Top5 优化说明

## 使用方法

```bash
# 运行完整 Pipeline
python pipeline.py

# 或者指定参数
python pipeline.py
```

## 功能特点

- ✅ ETL 清洗与标准化
- ✅ 传播关系派生
- ✅ 候选主题生成
- ✅ Topic 聚合
- ✅ 热度评分与 Top5
- ✅ 趋势判断
- ✅ Daily Report 输出

