#!/bin/bash

echo "=== 分析根目录重复文件 ==="
echo ""

# 检查哪些文件在根目录和 V0/V1 中都存在
echo "在根目录和 V0 中都存在的文件："
for file in *.py *.json *.jsonl *.md 2>/dev/null; do
    if [ -f "V0/$file" ]; then
        echo "  ✓ $file (重复)"
    fi
done

echo ""
echo "在根目录和 V1 中都存在的文件："
for file in *.py *.json *.jsonl *.md 2>/dev/null; do
    if [ -f "V1/$file" ]; then
        echo "  ✓ $file (重复)"
    fi
done

echo ""
echo "只在根目录的文件（可能是工具文件）："
for file in *.sh *.md 2>/dev/null; do
    if [ ! -f "V0/$file" ] && [ ! -f "V1/$file" ]; then
        echo "  ? $file"
    fi
done
