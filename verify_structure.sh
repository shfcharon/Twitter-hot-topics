#!/bin/bash

echo "=== 验证文件夹结构 ==="
echo ""

echo "V0 文件夹检查："
echo "- 代码文件："
ls -1 V0/*.py 2>/dev/null | wc -l | xargs echo "  找到"
echo "- 输入文件："
ls -1 V0/*.json V0/*.jsonl 2>/dev/null | grep -E "(candidate_pool|initial_kol|tweets_|edges_)" | wc -l | xargs echo "  找到"
echo "- 文档文件："
ls -1 V0/*.md 2>/dev/null | wc -l | xargs echo "  找到"
echo ""

echo "V1 文件夹检查："
echo "- 代码文件："
ls -1 V1/*.py 2>/dev/null | wc -l | xargs echo "  找到"
echo "- 输入文件："
ls -1 V1/*.json V1/*.jsonl 2>/dev/null | grep -E "(initial_kol|tweets_)" | wc -l | xargs echo "  找到"
echo "- 文档文件："
ls -1 V1/*.md 2>/dev/null | wc -l | xargs echo "  找到"
echo ""

echo "=== 关键文件检查 ==="
echo ""

# 检查 V0 关键文件
echo "V0 关键文件："
[ -f "V0/pipeline.py" ] && echo "  ✓ pipeline.py" || echo "  ✗ pipeline.py 缺失"
[ -f "V0/100seed.py" ] && echo "  ✓ 100seed.py" || echo "  ✗ 100seed.py 缺失"
[ -f "V0/expansion_candidates.py" ] && echo "  ✓ expansion_candidates.py" || echo "  ✗ expansion_candidates.py 缺失"
[ -f "V0/kol_500.py" ] && echo "  ✓ kol_500.py" || echo "  ✗ kol_500.py 缺失"
[ -f "V0/initial_kol_500.json" ] && echo "  ✓ initial_kol_500.json" || echo "  ✗ initial_kol_500.json 缺失"
echo ""

# 检查 V1 关键文件
echo "V1 关键文件："
[ -f "V1/pipeline_advanced.py" ] && echo "  ✓ pipeline_advanced.py" || echo "  ✗ pipeline_advanced.py 缺失"
[ -f "V1/initial_kol_500.json" ] && echo "  ✓ initial_kol_500.json" || echo "  ✗ initial_kol_500.json 缺失"
[ -f "V1/tweets_14d.jsonl" ] && echo "  ✓ tweets_14d.jsonl" || echo "  ✗ tweets_14d.jsonl 缺失"
[ -f "V1/tweets_24h.jsonl" ] && echo "  ✓ tweets_24h.jsonl" || echo "  ✗ tweets_24h.jsonl 缺失"
echo ""

echo "=== 输出文件名检查 ==="
echo ""
echo "V0 输出文件（示例）："
ls -1 V0/hot_topics_top5.json V0/daily_report.json 2>/dev/null | sed 's/^/  /'
echo ""
echo "V1 输出文件（应包含 _v1 后缀）："
echo "  - hot_topics_top5_v1.json (在代码中已设置)"
echo "  - daily_report_v1.json (在代码中已设置)"
echo "  - daily_report_readable_v1.json (在代码中已设置)"
echo "  - semantic_topics_24h.jsonl (V1 新增)"
echo "  - growth_predictions_24h.jsonl (V1 新增)"
echo ""

echo "=== 验证完成 ==="

