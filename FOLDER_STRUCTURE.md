# 文件夹结构说明

## 目录结构

```
twitter data/
├── V0/                    # V0 基础版本
│   ├── README.md         # V0 使用说明
│   ├── pipeline.py       # V0 主代码
│   ├── 100seed.py        # 种子账号选择
│   ├── expansion_candidates.py  # 扩展候选生成
│   ├── kol_500.py        # KOL 池构建
│   ├── candidate_pool.json       # 输入：候选账号池
│   ├── initial_kol_500.json     # 输入：500 KOL 列表
│   ├── tweets_14d.jsonl         # 输入：14 天推文
│   ├── tweets_24h.jsonl         # 输入：24 小时推文
│   ├── edges_*.jsonl            # 输入：关系边（可选）
│   └── [输出文件]                # V0 的所有输出文件
│
└── V1/                    # V1 高级版本
    ├── README.md         # V1 使用说明
    ├── pipeline_advanced.py    # V1 主代码
    ├── initial_kol_500.json     # 输入：500 KOL 列表（复制自 V0）
    ├── tweets_14d.jsonl         # 输入：14 天推文（复制自 V0）
    ├── tweets_24h.jsonl         # 输入：24 小时推文（复制自 V0）
    └── [输出文件]                # V1 的所有输出文件
```

## 文件区分规则

### V0 文件夹
包含所有 V0 相关的文件：
- ✅ V0 代码文件（pipeline.py, 100seed.py, expansion_candidates.py, kol_500.py）
- ✅ V0 输入文件（所有原始输入数据）
- ✅ V0 输出文件（所有 V0 生成的输出）
- ✅ V0 文档（评估、修复、步骤说明等）

### V1 文件夹
包含所有 V1 相关的文件：
- ✅ V1 代码文件（pipeline_advanced.py）
- ✅ V1 输入文件（从 V0 复制的必要输入文件）
- ✅ V1 输出文件（所有 V1 生成的输出，文件名已区分）
- ✅ V1 文档（实现总结、改进评估等）

## 输出文件名区分

### V0 输出文件
- `hot_topics_top5.json`
- `daily_report.json`
- `daily_report_readable.json`

### V1 输出文件（已区分，不会冲突）
- `hot_topics_top5_v1.json` ✅
- `semantic_topics_24h.jsonl` ✅（V1 新增）
- `growth_predictions_24h.jsonl` ✅（V1 新增）
- `daily_report_v1.json` ✅
- `daily_report_readable_v1.json` ✅

### 共享输出文件（两个版本都会生成，但在不同文件夹）
- `tweets_14d_clean.jsonl`
- `tweets_24h_clean.jsonl`
- `edges_14d.jsonl`
- `edges_24h.jsonl`
- `topic_candidates_24h.jsonl`
- `topics_24h.jsonl`
- `trends_14d.jsonl`

**注意**：这些文件虽然名称相同，但由于 V0 和 V1 在不同的文件夹中运行，不会产生冲突。

## 使用建议

### 运行 V0
```bash
cd V0
python pipeline.py
```

### 运行 V1
```bash
cd V1
python pipeline_advanced.py
```

### 独立运行
- V0 和 V1 完全独立，可以在不同文件夹中同时运行
- 每个版本的所有输入输出都在各自的文件夹中
- 不会产生文件冲突

## 文件完整性检查

### V0 文件夹应包含
- [x] 所有代码文件（4 个 .py 文件）
- [x] 所有输入文件（JSON/JSONL）
- [x] 所有输出文件（如果已运行）
- [x] 所有文档文件（.md 文件）

### V1 文件夹应包含
- [x] V1 代码文件（pipeline_advanced.py）
- [x] 必要输入文件（initial_kol_500.json, tweets_*.jsonl）
- [x] V1 文档文件（.md 文件）

## 注意事项

1. **不要混淆**：V0 和 V1 文件夹完全独立，不要将文件混放
2. **输入文件**：V1 的输入文件已从 V0 复制，可以独立运行
3. **输出文件**：V1 的输出文件名已区分（带 `_v1` 后缀），不会覆盖 V0
4. **代码修改**：修改 V0 代码不会影响 V1，反之亦然

