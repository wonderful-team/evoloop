---
name: AppMap Analysis
description: Survey a project's source code and produce an AppMap (structured five-layer entity map) for macro generation.
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
---

# AppMap Analysis

Survey one entity of a software project and write a structured AppMap via `write_app_map`. The map feeds a deterministic template factory that batch-produces macros — accuracy of the map directly determines whether macros reference things that actually exist.

## 🎯 Mission Objective

Produce ONE complete, verifiable AppMap for the assigned entity. Every entry must be traceable to a real location in the source — entries that cannot be spot-checked are rejected by the validator.

## Survey Procedure

Wide coverage is achieved MECHANICALLY — do NOT survey entity-by-entity with
manual grep/read loops (too slow, burns the step budget, invites truncation).

1. **Recon (budget: at most ~10 read/grep calls)** — read 2-3 sample
   controllers, 2-3 sample views, and skim the DB schema — just enough to
   learn the framework's conventions:
   - how action methods look (e.g. ThinkPHP `public function`)
   - how views mark elements (`id=` / `name=` / `lay-filter=`) — record this per
  element as `selector_type` ("id" / "name" / "class" / "lay-filter" / "css" /
  "text"); the collector script infers it mechanically from the markup attribute
- whether the admin site's origin is discoverable (config/.env/README) — if
  yes, pass it as `extra: {"base_url": "http://host:port"}`; route `url` stays
  a site-relative path starting with `/`
   - how `CREATE TABLE` is written; how controllers reference tables
   - Identify the framework by its layout (do NOT guess; look at actual files).
   - Locate the entity's surface by project type:
     - Web 后端: 路由注册文件 / 控制器 CRUD / 视图模板 / DB Schema（migration 或 *.sql）
     - Android: AndroidManifest.xml / Activity / Layout XML / ContentProvider
     - macOS/iOS: ViewController / XIB / Storyboard / SwiftUI Views
     - Electron: 主进程 IPC / 渲染进程路由
     - CLI 工具: 命令注册 / 子命令 / flags
2. **Write a one-off collector script** — `write_file` a throwaway script
   (Python recommended) at the project root, then run it via
   `execute_command`. It must mechanically scan ALL entities at once:
   - controllers → every action method + exact line (exclude infra
     controllers and inherited/base methods)
   - views → element symbols + file + line
   - schema → table / pk / cols
   - Output ONE JSON: `{entity: {actions: [{name, line}], elements: [{name,
     page, line}], db_tables: [{table, pk, cols}]}}`.
   Spot-check a few entities in the output; fix and rerun the script until
   extraction is solid. Line numbers are COMPUTED, never guessed.
3. **Enrich semantics** — for each entity, turn raw facts into the five-layer
   payload. Heuristics may also be scripted when conventions are regular
   (e.g. lists=read/ui, edit/add/del=write, price/stock/balance/refund/
   status writes=money). You supply what code cannot know:
   - `kind` / `risk_tier` (money for price, balance, stock, refund, key writes)
   - `business_rule` (one line, from method name + framework conventions)
   - `touches_tables` / `set_fields` / `pk`
   - `aliases` (English identifier + Chinese business term)
4. **Write the map** — call `write_app_map` ONCE per entity with the complete
   payload. Citations come from the collector output (controller/page + line).
   If validation rejects it, fix the cited entries and retry.
5. **Generate macros** — after each successful write, call
   `generate_macros_from_app_map(app_map_id)`, then move to the next entity.

Element coverage stays MANDATORY (the template factory grounds on these):
列表页**搜索框**、列表页**结果表格**、表单页**保存/提交按钮**、写操作涉及的
**输入字段**。缺少它们对应 action 无法产宏。If the collector cannot find
them for an entity, leave them out (never fabricate) — the factory will
honestly report that action as a coverage gap.

## Hard Rules

- NEVER fabricate routes, actions, elements, or tables. If you cannot find evidence in the source, do not include the entry.
- controller/line and page/line citations are spot-checked mechanically; hallucinated entries cause the ENTIRE write to be rejected.
- Money-write actions (price, balance, stock, refund) MUST be marked `risk_tier: money`.
- Money-write fields accept absolute values only.
- The entity name and aliases must include both the English identifier and the Chinese business term (e.g. entity=goods, aliases include 商品).
- Use ABSOLUTE paths for all tool calls (relative paths trip the workspace security gate). Collector scripts and their JSON output live at the project root — NEVER inside `.evoloop/` (access prohibited).

## Output Contract (via write_app_map)

```
entity, platform, aliases
routes:   [{name, url, method, source_action}]   # url starts with "/"
actions:  [{name, kind, risk_tier, business_rule, touches_tables, set_fields?, pk?, controller, line}]
elements: [{name, page, line, binds, selector_type}]
db_tables: [{table, pk, cols}]
extra:    {base_url?}   # site origin, when discoverable from project config
```

Finish by reporting: entity surveyed, actions cataloged (read/write/money counts), macros generated.
