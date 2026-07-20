---
name: AppMap Analysis
description: Survey a project's source code and produce AppMaps (structured five-layer entity maps) for macro generation.
namespace: roles
trigger_patterns:
  - "生成源码地图"
  - "分析项目结构"
  - "铺满技能"
  - "Generate source map"
parameters:
  project_id:
    type: integer
    description: The target project ID.
  working_directory:
    type: string
    description: The root directory of the project to survey.
requires:
  tools:
    - query_code_chunks
    - query_code_relations
    - read_app_map
    - write_app_map
    - list_app_maps
    - generate_macros_from_app_map
    - read_file
    - write_file
    - execute_command
    - grep_search
scripts:
  batch_write:
    path: scripts/batch_writer.py
    description: Batch-write all AppMap records from a collector JSON file.
    usage: |
      uv run python app/config/skills/app_map_analysis/scripts/batch_writer.py \
        --project-id {project_id} --input {json_path}
  reference_collector:
    path: scripts/collector.py
    description: Reference collector script. Copy to project root, adapt FRAMEWORK CONFIG, then run.
    usage: |
      cp app/config/skills/app_map_analysis/scripts/collector.py {project_root}/collect_appmaps.py
    usage: |
      cp app/core/atlas/source/skeleton/collector.py {project_root}/collect_appmaps.py
---

# AppMap Analysis

Survey a software project and produce complete five-layer AppMaps. The maps feed a deterministic template factory that batch-produces macros — accuracy of the map directly determines whether macros reference things that actually exist.

## 🎯 Mission Objective

Produce complete AppMaps for ALL business entities. Every entry must be traceable to a real location in the source — entries that cannot be spot-checked are rejected by the validator.

## Survey Procedure

Do NOT survey entity-by-entity with manual grep/read loops (too slow, burns the step budget, invites truncation). Instead:

1. **Recon (≤ 10 read/grep calls)** — read 2-3 sample controllers, 2-3 sample views, and skim the DB schema — just enough to learn the framework's conventions:
   - how action methods look (e.g. ThinkPHP `public function`)
   - how views mark elements (`id=` / `name=` / `lay-filter=`) — record this per element as `selector_type`
   - how `CREATE TABLE` is written; how controllers reference tables
   - whether the admin site's origin is discoverable — if yes, pass it as `extra: {"base_url": "..."}`; route `url` stays a site-relative path starting with `/`
   - Locate the entity's surface by project type:
     - Web 后端: 路由注册 / 控制器 CRUD / 视图模板 / DB Schema
     - Android: AndroidManifest.xml / Activity / Layout XML / ContentProvider
     - macOS/iOS: ViewController / XIB / Storyboard / SwiftUI Views
     - Electron: 主进程 IPC / 渲染进程路由
     - CLI 工具: 命令注册 / 子命令 / flags

2. **Use the reference collector script** — a copy is already at `collect_appmaps.py` in the project root. Configure the FRAMEWORK CONFIG section at the top (controller_dirs, view_dirs, sql_path, route_pattern), then run it:
   ```bash
   python collect_appmaps.py . --sql <sql_file>
   ```

   The reference script mechanically scans ALL entities at once:
   - controllers → every action method + exact line
   - views → element symbols (`id`/`name`/`lay-filter`) + page path + line, with `selector_type`
   - schema → table / pk / cols
   - Outputs ONE JSON file to `/tmp/appmap_extracted.json`. STDOUT is a single summary line — it will NOT be truncated.

   Spot-check 2-3 entities in the JSON; update the script's config or heuristics and re-run until correct.

3. **Enrich semantics** — update the reference script's heuristics section to match your project conventions:
   - `kind`: lists/search → `read`, edit/add/del → `write`
   - `risk_tier`: price/stock/balance/refund writes → `money`, other writes → `data`, reads → `ui`
   - `touches_tables` / `set_fields` / `pk`

4. ⚠️ **CRITICAL — Batch write** ⚠️ Do NOT stop after the script runs. Immediately proceed to batch-write:

   ```bash
   uv run python app/config/skills/app_map_analysis/scripts/batch_writer.py \
     --project-id {project_id} --input /tmp/appmap_extracted.json
   ```

   This persists all AppMap records and generates macros in one pass. The script reports written/skipped/failed counts.

5. **Verify** — read back 2-3 written AppMaps via `read_app_map` to confirm. If failures exist, fix the JSON file and re-run step 4.

## Hard Rules

- NEVER fabricate routes, actions, elements, or tables. If you cannot find evidence in the source, do not include the entry.
- controller/line and page/line citations are spot-checked mechanically; hallucinated entries cause the ENTIRE write to be rejected.
- Money-write actions (price, balance, stock, refund) MUST be marked `risk_tier: money`.
- Money-write fields accept absolute values only.
- The entity name and aliases must include both the English identifier and the Chinese business term.
- Use ABSOLUTE paths for all tool calls. Collector scripts and their JSON output live at the project root — NEVER inside `.evoloop/`.
- Element coverage stays MANDATORY: 列表页搜索框、列表页结果表格、表单页保存/提交按钮、写操作涉及的输入字段。缺少它们对应 action 无法产宏。If the collector cannot find them, leave them out (never fabricate).

## Output Contract (via batch_writer.py)

```
entity, platform, aliases
routes:   [{name, url, method, source_action}]
actions:  [{name, kind, risk_tier, business_rule, touches_tables, set_fields?, pk?, controller, line}]
elements: [{name, page, line, binds, selector_type}]
db_tables: [{table, pk, cols}]
extra:    {base_url?}
```

Finish by reporting: entities processed, actions cataloged (read/write/money counts), macros generated.
