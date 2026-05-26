#!/usr/bin/env python3
"""
直接查询 skill 562 的内容
"""
import json
import psycopg2

def main():
    # 连接数据库 (从 tests/.env 读取的凭据)
    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        database="app",
        user="postgres",
        password="admin888"
    )

    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, execution_mode, macro_script FROM learned_skills WHERE id = %s",
            (562,)
        )
        row = cur.fetchone()

        if not row:
            print("Skill 562 not found!")
            return

        skill_id, name, execution_mode, macro_script = row

        print(f"Skill ID: {skill_id}")
        print(f"Name: {name}")
        print(f"Execution Mode: {execution_mode}")
        print(f"\nMacro Script ({len(macro_script)} steps):")
        print("=" * 80)

        for i, step in enumerate(macro_script, 1):
            print(f"\nStep {i}:")
            print(json.dumps(step, indent=2, ensure_ascii=False))

        # 分析是否有 screenshot 或耗时的操作
        print("\n" + "=" * 80)
        print("操作分析:")
        has_screenshot = False
        has_ocr = False
        has_wait = False
        total_wait_time = 0

        for step in macro_script:
            if step.get('event_type') == 'screenshot':
                has_screenshot = True
                if step.get('payload', {}).get('ocr'):
                    has_ocr = True
            if step.get('event_type') == 'wait':
                has_wait = True
                payload = step.get('payload', {})
                seconds = payload.get('seconds', 0)
                duration_ms = payload.get('duration_ms', 0)
                total_wait_time += seconds if seconds else duration_ms / 1000
            if step.get('type') == 'extract' and step.get('extract_type') == 'screenshot':
                has_screenshot = True

        print(f"  - 包含 screenshot: {has_screenshot}")
        print(f"  - 包含 OCR: {has_ocr}")
        print(f"  - 包含 wait: {has_wait} (总计 {total_wait_time:.1f}s)")

        if has_screenshot:
            print("\n⚠️  WARNING: Macro 包含 screenshot 操作，这会导致浏览器渲染暂停！")

    finally:
        conn.close()

if __name__ == "__main__":
    main()
