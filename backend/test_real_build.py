#!/usr/bin/env python3
"""
真实项目构建测试 - 使用 EvoLoop 前端项目测试后台任务

测试场景:
1. 执行 npm run build (真实构建，预计 30-60 秒)
2. 后台模式运行
3. 定期查询进度
4. 验证输出捕获

运行: cd /Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend && python3 test_real_build.py
"""

import asyncio
import os
import signal
import sys
import time
from collections import deque
from datetime import datetime
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

# 直接导入核心模块（绕过 LangChain 依赖）
from app.core.tools.background import task_manager, TaskType, TaskStatus


class Colors:
    """终端颜色"""
    GREEN = '\033[92m'
    BLUE = '\033[94m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'


def print_header(text):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}\n")


def print_success(text):
    print(f"{Colors.GREEN}✅ {text}{Colors.END}")


def print_info(text):
    print(f"{Colors.CYAN}ℹ️  {text}{Colors.END}")


def print_warning(text):
    print(f"{Colors.YELLOW}⚠️  {text}{Colors.END}")


def print_error(text):
    print(f"{Colors.RED}❌ {text}{Colors.END}")


async def run_npm_build_background():
    """
    在后台执行 npm run build
    """
    print_header("真实项目构建测试")
    
    # 项目路径
    frontend_dir = Path("/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/frontend")
    
    if not frontend_dir.exists():
        print_error(f"项目目录不存在: {frontend_dir}")
        return False
    
    print_info(f"项目目录: {frontend_dir}")
    print_info(f"构建命令: npm run build")
    print()
    
    # 创建后台任务
    task = await task_manager.create_task(
        task_type=TaskType.BUILD,
        title="npm run build (EvoLoop Frontend)",
        tool_name="execute_command",
        thread_id="test-real-build",
        timeout_seconds=300,  # 5分钟超时
    )
    
    print_success(f"后台任务创建: {task.task_id}")
    print_info(f"开始时间: {datetime.now().strftime('%H:%M:%S')}")
    print()
    
    # 启动构建进程
    cmd = "npm run build 2>&1"
    
    try:
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,  # 合并 stderr 到 stdout
            cwd=str(frontend_dir),
            preexec_fn=os.setsid,
        )
        
        # 标记任务开始
        await task_manager.start_task(task.task_id, process.pid)
        print_success(f"构建进程启动 (PID: {process.pid})")
        print()
        
        # 设置取消回调
        def cancel_callback():
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                print_warning("发送 SIGTERM 终止信号")
            except ProcessLookupError:
                pass
        
        task.set_cancel_callback(cancel_callback)
        
        # 启动输出读取任务
        read_task = asyncio.create_task(
            read_build_output(process, task.task_id)
        )
        
        # 启动进度监控任务
        monitor_task = asyncio.create_task(
            monitor_build_progress(task.task_id)
        )
        
        # 等待构建完成
        try:
            exit_code = await asyncio.wait_for(process.wait(), timeout=300)
            
            # 等待输出读取完成
            await asyncio.wait_for(read_task, timeout=5.0)
            
            # 停止监控
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass
            
            # 更新任务状态
            if exit_code == 0:
                await task_manager.complete_task(task.task_id, result={"exit_code": 0})
            else:
                await task_manager.fail_task(
                    task.task_id, 
                    error=f"Build failed with exit code {exit_code}"
                )
            
            print()
            print_header("构建结果")
            
            if exit_code == 0:
                print_success(f"构建成功！({task.elapsed_seconds}秒)")
            else:
                print_error(f"构建失败！退出码: {exit_code}")
            
            # 显示最后输出
            final_task = task_manager.get_task(task.task_id)
            if final_task:
                print()
                print(f"{Colors.BOLD}最后 30 行输出:{Colors.END}")
                print("-" * 60)
                output = final_task.get_recent_output(30)
                # 只显示关键信息
                lines = output.split('\n')
                for line in lines[-30:]:  # 只显示最后30行
                    if line.strip():
                        print(f"  {line}")
                print("-" * 60)
                
                # 统计信息
                print()
                print_info(f"总耗时: {final_task.elapsed_seconds}秒")
                print_info(f"输出行数: {len(final_task.output_buffer)}")
                print_info(f"进程ID: {final_task.process_id}")
                print_info(f"任务状态: {final_task.status.value}")
            
            return exit_code == 0
            
        except asyncio.TimeoutError:
            print_error("构建超时 (5分钟)")
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except:
                pass
            await task_manager.timeout_task(task.task_id)
            return False
            
    except Exception as e:
        print_error(f"执行错误: {e}")
        await task_manager.fail_task(task.task_id, error=str(e))
        return False


async def read_build_output(process, task_id):
    """读取构建输出"""
    try:
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            
            decoded = line.decode('utf-8', errors='replace').rstrip()
            if decoded:
                task_manager.append_output(task_id, decoded)
    except Exception as e:
        print_error(f"读取输出错误: {e}")


async def monitor_build_progress(task_id):
    """监控构建进度"""
    try:
        last_line_count = 0
        check_count = 0
        
        while True:
            await asyncio.sleep(3)  # 每3秒检查一次
            check_count += 1
            
            task = task_manager.get_task(task_id)
            if not task or task.is_completed:
                break
            
            current_lines = len(task.output_buffer)
            new_lines = current_lines - last_line_count
            last_line_count = current_lines
            
            # 显示进度
            elapsed = task.elapsed_seconds
            recent = task.get_recent_output(5)  # 最近5行
            
            print(f"\n{Colors.YELLOW}[{elapsed}s] 构建中... (+{new_lines} 行){Colors.END}")
            
            # 显示关键输出
            for line in recent.split('\n'):
                if any(keyword in line for keyword in ['Building', 'Compiling', 'dist/', 'error', 'warning', '✓', '✔']):
                    print(f"  {Colors.CYAN}> {line[:80]}{Colors.END}")
            
            # 长时间运行的提示
            if elapsed > 60 and check_count % 5 == 0:
                print(f"  {Colors.YELLOW}... 构建仍在进行，已运行 {elapsed} 秒 ...{Colors.END}")
                
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print_error(f"监控错误: {e}")


async def test_cancel_functionality():
    """测试取消功能"""
    print_header("测试取消功能")
    
    # 创建一个长时间任务
    task = await task_manager.create_task(
        task_type=TaskType.COMMAND,
        title="Sleep 60s (for cancel test)",
        tool_name="execute_command",
        thread_id="test-cancel",
        timeout_seconds=60,
    )
    
    # 启动 sleep 进程
    process = await asyncio.create_subprocess_shell(
        "sleep 60",
        preexec_fn=os.setsid,
    )
    
    await task_manager.start_task(task.task_id, process.pid)
    print_success(f"任务启动 (PID: {process.pid})")
    
    # 等待1秒
    await asyncio.sleep(1)
    
    # 取消任务
    print_info("取消任务...")
    success = await task_manager.cancel_task(task.task_id)
    
    if success:
        print_success("任务已取消")
        # 等待进程退出
        try:
            await asyncio.wait_for(process.wait(), timeout=2.0)
            print_info(f"进程退出码: {process.returncode}")
        except:
            pass
    else:
        print_error("取消失败")
    
    return success


async def main():
    """主测试流程"""
    start_time = time.time()
    
    try:
        # 测试1: 真实构建
        build_success = await run_npm_build_background()
        
        print()
        print("-" * 60)
        
        # 测试2: 取消功能
        cancel_success = await test_cancel_functionality()
        
        # 总结
        print_header("测试总结")
        
        if build_success:
            print_success("✓ 真实构建测试通过")
        else:
            print_error("✗ 真实构建测试失败")
        
        if cancel_success:
            print_success("✓ 取消功能测试通过")
        else:
            print_error("✗ 取消功能测试失败")
        
        total_time = time.time() - start_time
        print()
        print_info(f"总测试时间: {total_time:.1f}秒")
        
        # 任务统计
        stats = task_manager.get_stats()
        print()
        print_info("任务管理器统计:")
        for key, value in stats.items():
            print(f"  - {key}: {value}")
        
        return build_success and cancel_success
        
    except KeyboardInterrupt:
        print()
        print_warning("测试被用户中断")
        return False
    except Exception as e:
        print_error(f"测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print(f"{Colors.BOLD}EvoLoop 后台任务真实测试{Colors.END}")
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    success = asyncio.run(main())
    
    sys.exit(0 if success else 1)
