#!/bin/bash

# 清理根目录中与 V0/V1 重复的文件
# 保留工具文件和文档

echo "=== 清理根目录重复文件 ==="
echo ""

# 要删除的重复文件列表
FILES_TO_DELETE=(
    # 代码文件
    "100seed.py"
    "expansion_candidates.py"
    "kol_500.py"
    "pipeline.py"
    "pipeline_advanced.py"
    
    # 输入文件
    "candidate_pool.json"
    "initial_kol_500.json"
    "tweets_14d.jsonl"
    "tweets_24h.jsonl"
    "edges_following.jsonl"
    "edges_mentions.jsonl"
    "edges_interactions.jsonl"
    
    # 输出文件
    "daily_report.json"
    "daily_report_readable.json"
    "hot_topics_top5.json"
    "edges_14d.jsonl"
    "edges_24h.jsonl"
    "topic_candidates_24h.jsonl"
    "topics_24h.jsonl"
    "trends_14d.jsonl"
    "tweets_14d_clean.jsonl"
    "tweets_24h_clean.jsonl"
    "tweets_14d_kol.jsonl"
    "tweets_24h_kol.jsonl"
    "kol_all_500.jsonl"
    "expansion_candidates.jsonl"
    "seed_100.json"
    
    # 文档文件（已在V0/V1中）
    "pipeline_evaluation.md"
    "pipeline_fixes_summary.md"
    "pipeline_steps_corrected.md"
    "pipeline_steps_corrections.md"
    "pipeline_top5_optimization.md"
    "pipeline_v1_implementation_summary.md"
    "v1_improvement_assessment.md"
)

# 保留的文件（工具文件和根目录文档）
KEEP_FILES=(
    "FOLDER_STRUCTURE.md"
    "organize_files.sh"
    "verify_structure.sh"
    "cleanup_duplicates.sh"
    "analyze_duplicates.sh"
    "文件整理完成说明.md"
)

echo "将删除以下重复文件："
for file in "${FILES_TO_DELETE[@]}"; do
    if [ -f "$file" ]; then
        echo "  - $file"
    fi
done

echo ""
echo "将保留以下工具文件："
for file in "${KEEP_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "  ✓ $file"
    fi
done

echo ""
read -p "确认删除？(y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "正在删除..."
    for file in "${FILES_TO_DELETE[@]}"; do
        if [ -f "$file" ]; then
            rm "$file"
            echo "  ✓ 已删除: $file"
        fi
    done
    echo ""
    echo "清理完成！"
else
    echo "取消删除。"
fi

