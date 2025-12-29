#!/bin/bash

# V0 文件
# 代码文件
cp pipeline.py V0/
cp 100seed.py V0/
cp expansion_candidates.py V0/
cp kol_500.py V0/

# V0 输入文件
cp candidate_pool.json V0/ 2>/dev/null || true
cp initial_kol_500.json V0/ 2>/dev/null || true
cp tweets_14d.jsonl V0/ 2>/dev/null || true
cp tweets_24h.jsonl V0/ 2>/dev/null || true
cp edges_following.jsonl V0/ 2>/dev/null || true
cp edges_mentions.jsonl V0/ 2>/dev/null || true
cp edges_interactions.jsonl V0/ 2>/dev/null || true

# V0 输出文件（如果存在）
cp tweets_14d_clean.jsonl V0/ 2>/dev/null || true
cp tweets_24h_clean.jsonl V0/ 2>/dev/null || true
cp tweets_14d_kol.jsonl V0/ 2>/dev/null || true
cp tweets_24h_kol.jsonl V0/ 2>/dev/null || true
cp kol_all_500.jsonl V0/ 2>/dev/null || true
cp edges_14d.jsonl V0/ 2>/dev/null || true
cp edges_24h.jsonl V0/ 2>/dev/null || true
cp topic_candidates_24h.jsonl V0/ 2>/dev/null || true
cp topics_24h.jsonl V0/ 2>/dev/null || true
cp hot_topics_top5.json V0/ 2>/dev/null || true
cp trends_14d.jsonl V0/ 2>/dev/null || true
cp daily_report.json V0/ 2>/dev/null || true
cp daily_report_readable.json V0/ 2>/dev/null || true
cp seed_100.json V0/ 2>/dev/null || true
cp expansion_candidates.jsonl V0/ 2>/dev/null || true

# V0 文档
cp pipeline_evaluation.md V0/ 2>/dev/null || true
cp pipeline_fixes_summary.md V0/ 2>/dev/null || true
cp pipeline_steps_corrected.md V0/ 2>/dev/null || true
cp pipeline_steps_corrections.md V0/ 2>/dev/null || true
cp pipeline_top5_optimization.md V0/ 2>/dev/null || true

# V1 文件
# 代码文件
cp pipeline_advanced.py V1/

# V1 输入文件（复制自 V0）
cp initial_kol_500.json V1/ 2>/dev/null || true
cp tweets_14d.jsonl V1/ 2>/dev/null || true
cp tweets_24h.jsonl V1/ 2>/dev/null || true

# V1 文档
cp pipeline_v1_implementation_summary.md V1/ 2>/dev/null || true
cp v1_improvement_assessment.md V1/ 2>/dev/null || true

echo "Files organized successfully!"
