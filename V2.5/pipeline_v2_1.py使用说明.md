### 目的

`pipeline_v2_1.py` 是 V2.5 的可运行实现：用 LLM 做**事件判定/结构化/同事件对齐/标题摘要**，用代码做**过滤、降维、聚类合并、打分、Top5 与日报输出**，并且全链路落盘可回溯。

---

### 目录结构（必须）

在 `V2.5/` 下：

- `inputs/`
  - `tweets_24h_clean.jsonl`（必须）
  - `kol_profiles.jsonl`（必须）
  - `edges_24h.jsonl`（可选）
  - `human_edits.jsonl`（可选）
- `assets/`（必须，已提供）
- `outputs/`（自动生成）
- `logs/`（自动生成）

---

### 运行方式

#### 方式 A：启用 LLM（推荐）

在 `V2.5/` 目录下运行：

```bash
export OPENAI_API_KEY="YOUR_KEY"
python3 pipeline_v2_1.py --llm_enabled
```

默认模型：`gpt-4.1-mini`，默认温度：`0.0`（保证可复现）。

#### 方式 B：不启用 LLM（仅用于调试流程）

```bash
python3 pipeline_v2_1.py --no_llm
```

注意：不启用 LLM 时，Step1 会把所有 tweet 视为 non-event，最终 Top5 为空（这是预期行为）。

---

### 常用参数

- `--model gpt-4.1-mini`：选择模型
- `--max_tweets 200`：只跑前 N 条 tweet（快速调试）
- `--min_text_len 30`：规则过滤最短文本长度
- `--same_event_threshold 0.75`：Step5 合并阈值（same_event=true 且 confidence≥阈值才会连边合并）
- `--max_bucket_size 120`：Step4 blocking bucket 最大保留数（按 engagement 截断）
- `--max_pairs_total 4000`：Step4 最多生成多少候选 pairs（成本控制）
- `--overwrite_outputs`：清空指定 output/log 文件后重新跑（重要）

示例（全量跑 + 清空旧结果）：

```bash
export OPENAI_API_KEY="YOUR_KEY"
python3 pipeline_v2_1.py --llm_enabled --overwrite_outputs
```

---

### 输出文件说明（outputs/）

- `events_structured.jsonl`
  - Step1 每条 tweet 的结构化抽取结果（`step1` 字段）
- `events_filtered.jsonl`
  - Step2+3 通过 gate 后的 EventCard（含 `step2_gate`）
- `event_pairs_candidates.jsonl`
  - Step4 规则降维生成的候选 pairs
- `event_pairs_same_event.jsonl`
  - Step5 LLM 判同事件的结果（包含 `decision` 和原始候选原因）
- `event_clusters.json`
  - Step6 聚类合并后的 cluster 列表（含 score 相关字段）
- `hot_events_top5.json`
  - Step7/8 完成后的 Top5 cluster（含 title/summary）
- `daily_report.json`
  - 完整日报（结构化，适合下游程序/前端）
- `daily_report_readable.json`
  - 易读中文版本（适合直接查看）

日志（logs/）：

- `llm_raw.jsonl`
  - 记录每次 LLM 调用的原始 content（便于回溯与 prompt 调试）
- `run_stats.json`
  - 各 step 输入/输出计数与丢弃原因分布（定位“哪一步筛没了”）

---

### human_edits.jsonl（Step 9）格式

放在 `inputs/human_edits.jsonl`，每行一条：

- **merge**：合并两个 cluster
```json
{"op":"merge","a":"cl_0001","b":"cl_0007","note":"同一融资事件，被拆成两簇"}
```

- **delete**：删除一个 cluster
```json
{"op":"delete","cluster_id":"cl_0012","note":"营销广告/弱相关"}
```

- **rename**：重命名标题（覆盖 Step8 生成）
```json
{"op":"rename","cluster_id":"cl_0003","title_cn":"OpenAI 发布新一代模型接口","note":"让标题更具体"}
```

运行后，已应用 edits 会写入 `daily_report.json` 的 `human_edits_applied`。

---

### kol_profiles.jsonl（V2.5 内置生成规则说明）

本仓库的 `V2.5/inputs/kol_profiles.jsonl` 是从 `initial_kol_500.json` 自动生成的：

- **kol_tier / kol_weight**（按 followers 分桶）：
  - `S`（≥1,000,000）→ `5.0`
  - `A`（≥200,000）→ `3.0`
  - `B`（≥50,000）→ `1.5`
  - `C`（其他）→ `1.0`

`domain/verified` 若源数据没有则为 `null`（可后续手工补齐或接入外部画像）。

