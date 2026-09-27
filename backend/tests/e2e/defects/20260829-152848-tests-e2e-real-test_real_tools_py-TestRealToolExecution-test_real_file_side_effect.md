# E2E 缺陷报告：test_real_file_side_effect

- **测试 ID**: `tests/e2e/real/test_real_tools.py::TestRealToolExecution::test_real_file_side_effect`
- **发现时间**: 2026-08-29T15:28:48.308057
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
self = <test_real_tools.TestRealToolExecution object at 0x1032fae50>
http_client = <httpx.AsyncClient object at 0x10357eb10>
thread_id = 'e2e-b391275a00ae4bdc', unique_marker = 'e2e-real-2a10f40f'
temp_project = {'imported': True, 'path': PosixPath('/Users/huangjinhuan/Projects/e2e-real-05a5df61'), 'project_id': 91}

    @pytest.mark.timeout(180)
    async def test_real_file_side_effect(
        self,
        http_client: httpx.AsyncClient,
        thread_id: str,
        unique_marker: str,
        temp_project: dict[str, Any],
    ) -> None:
        """Agent 调用 write_file 后，磁盘上确实存在目标文件（落在绑定项目目录内）。
    
        /chat 对 project_id=0 走全局 active project（SSOT），落盘位置随机器状态漂移；
        这里通过 temp_project 显式绑定新项目，使工作目录确定为该项目目录。
        """
        if not temp_project.get("imported") or not temp_project.get("project_id"):
            pytest.skip("临时项目导入失败，无法确定 write_file 落盘目录")
    
        project_id = temp_project["project_id"]
        project_dir = Path(temp_project["path"])
        target_file = f"e2e-real-{unique_marker}.txt"
        prompt = (
            f"请使用 write_file 工具创建文件 `{target_file}`，"
            f"内容写入 `side-effect-{unique_marker}`。"
        )
        messages, run_end, events = await _run_chat_with_tools(
            http_client, thread_id, prompt, project_id=project_id, timeout=180.0
        )
    
        status = run_end.get("status")
        if status == "quota_exhausted":
            verify_quota_exhausted_feedback(events)
            return
    
        if status != "done":
            pytest.fail(
                f"文件副作用测试失败，run_end={status}, run_end_data={run_end}"
            )
    
        expected_path = project_dir / target_file
        # 给文件系统一点写入时间，但通常应在 run_end 前完成
        for _ in range(50):
            if expected_path.exists():
                break
            await asyncio.sleep(0.1)
    
>       assert expected_path.exists(), (
            f"write_file 工具未在磁盘创建文件: {expected_path}"
        )
E       AssertionError: write_file 工具未在磁盘创建文件: /Users/huangjinhuan/Projects/e2e-real-05a5df61/e2e-real-e2e-real-2a10f40f.txt
E       assert False
E        +  where False = <bound method Path.exists of PosixPath('/Users/huangjinhuan/Projects/e2e-real-05a5df61/e2e-real-e2e-real-2a10f40f.txt')>()
E        +    where <bound method Path.exists of PosixPath('/Users/huangjinhuan/Projects/e2e-real-05a5df61/e2e-real-e2e-real-2a10f40f.txt')> = PosixPath('/Users/huangjinhuan/Projects/e2e-real-05a5df61/e2e-real-e2e-real-2a10f40f.txt').exists

tests/e2e/real/test_real_tools.py:298: AssertionError
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/real/test_real_tools.py::TestRealToolExecution::test_real_file_side_effect -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
