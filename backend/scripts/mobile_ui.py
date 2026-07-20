#!/usr/bin/env python3
"""HarmonyOS 真机 UI 自动化辅助脚本（基于 hdc uitest）."""

import json
import os
import re
import shlex
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path


HDC = "hdc"
DUMP_PATH = "/data/local/tmp/evoloop_layout.json"
SCREENSHOT_PATH = "/data/local/tmp/evoloop_screen.png"


def run(cmd: str, timeout: int = 30) -> str:
    """执行 hdc shell 命令（使用列表参数避免 shell 引用问题）."""
    parts = shlex.split(cmd)
    full = [HDC, "shell"] + parts
    result = subprocess.run(full, capture_output=True, text=True, timeout=timeout)
    return result.stdout + result.stderr


def dump_layout() -> str:
    """获取当前界面布局 JSON，返回本地文件路径."""
    run(f"uitest dumpLayout -p {DUMP_PATH}")
    local = "/tmp/evoloop_layout.json"
    subprocess.run(f"{HDC} file recv {DUMP_PATH} {local}", shell=True, capture_output=True)
    return local


def parse_bounds(bounds_str: str) -> tuple[int, int, int, int]:
    """解析 [x1,y1][x2,y2] -> (x1,y1,x2,y2)."""
    m = re.findall(r"\[(\d+),(\d+)\]", bounds_str)
    if len(m) != 2:
        raise ValueError(f"Invalid bounds: {bounds_str}")
    return tuple(int(v) for v in m[0] + m[1])


def center(bounds: tuple[int, int, int, int]) -> tuple[int, int]:
    return (bounds[0] + bounds[2]) // 2, (bounds[1] + bounds[3]) // 2


def clean_xml_string(xml_str: str) -> str:
    """过滤 XML 中的非法字符并修复未转义的 HTML/XML 实体."""
    valid_chars = []
    for char in xml_str:
        cp = ord(char)
        # XML 1.0 合法字符范围：#x9 | #xA | #xD | [#x20-#xD7FF] | [#xE000-#xFFFD] | [#x10000-#x10FFFF]
        if cp == 0x9 or cp == 0xA or cp == 0xD or (0x20 <= cp <= 0xD7FF) or (0xE000 <= cp <= 0xFFFD) or (0x10000 <= cp <= 0x10FFFF):
            valid_chars.append(char)
    cleaned = "".join(valid_chars)
    # 修复未转义的 & 符号（不构成实体的单独 & 替换为 &amp;）
    cleaned = re.sub(r'&(?!([a-zA-Z0-9]+|#\d+|#x[a-fA-F0-9]+);)', '&amp;', cleaned)
    return cleaned


def load_nodes() -> list[dict]:
    """扁平化加载所有节点（自动识别 JSON 或 XML，过滤非法字符及处理编码）."""
    path = dump_layout()
    
    # 1. 尝试以二进制读取并用 utf-8 / gbk 混合解码，容忍错误字符
    try:
        with open(path, "rb") as f:
            raw_data = f.read()
        try:
            content = raw_data.decode("utf-8")
        except UnicodeDecodeError:
            content = raw_data.decode("gbk", errors="replace")
    except Exception as e:
        print(f"读取布局文件失败: {e}")
        return []

    content_str = content.strip()
    if not content_str:
        return []

    nodes = []

    # 2. 判断格式并解析
    if content_str.startswith("<"):
        # XML 格式
        try:
            cleaned_xml = clean_xml_string(content_str)
            root = ET.fromstring(cleaned_xml)
            
            def walk_xml(elem, depth=0):
                attrs = dict(elem.attrib)
                # 兼容性处理：Android/XML 通常用 class，JSON 用 type，统一映射为 type
                if "class" in attrs and "type" not in attrs:
                    attrs["type"] = attrs["class"]
                if attrs:
                    attrs["_depth"] = depth
                    nodes.append(attrs)
                for child in elem:
                    walk_xml(child, depth + 1)
            
            walk_xml(root)
        except Exception as e:
            print(f"XML 布局解析失败，尝试强力清洗: {e}")
            try:
                # 极度暴力的 XML 实体及非法字符清洗
                cleaned_xml = re.sub(r'[^\x09\x0A\x0D\x20-\x7E\u00A0-\uD7FF\uE000-\uFFFD]', '', content_str)
                cleaned_xml = re.sub(r'&', '&amp;', cleaned_xml)
                # 恢复可能被双重转义的标准实体
                for ent in ['amp', 'lt', 'gt', 'apos', 'quot']:
                    cleaned_xml = cleaned_xml.replace(f'&amp;{ent};', f'&{ent};')
                root = ET.fromstring(cleaned_xml)
                walk_xml(root)
            except Exception as e2:
                print(f"XML 强力清洗后依然解析失败: {e2}")
    else:
        # JSON 格式
        try:
            # 用正则去除所有非打印控制字符（保留换行、回车、制表符）
            cleaned_json = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', content_str)
            root = json.loads(cleaned_json)
            
            def walk_json(elem, depth=0):
                attrs = elem.get("attributes", {})
                if attrs:
                    attrs["_depth"] = depth
                    nodes.append(attrs)
                for child in elem.get("children", []):
                    walk_json(child, depth + 1)
            
            walk_json(root)
        except Exception as e:
            print(f"JSON 布局解析失败: {e}")

    return nodes


def find_nodes(**kwargs) -> list[dict]:
    """按属性过滤节点."""
    nodes = load_nodes()
    results = []
    for n in nodes:
        ok = True
        for k, v in kwargs.items():
            if n.get(k) != v:
                ok = False
                break
        if ok:
            results.append(n)
    return results


def find_one(**kwargs) -> dict | None:
    """查找单个节点，返回第一个匹配."""
    results = find_nodes(**kwargs)
    return results[0] if results else None


def find_by_text(text: str) -> dict | None:
    """按 text 包含匹配."""
    nodes = load_nodes()
    for n in nodes:
        if text in (n.get("text") or "") or text in (n.get("originalText") or ""):
            return n
    return None


def click_node(node: dict) -> None:
    """点击节点中心."""
    x, y = center(parse_bounds(node["bounds"]))
    run(f"uitest uiInput click {x} {y}")


def click_text(text: str) -> bool:
    """点击包含指定文本的节点."""
    node = find_by_text(text)
    if node:
        click_node(node)
        return True
    return False


def click_input_area() -> bool:
    """点击输入框区域."""
    node = find_one(type="TextArea")
    if node:
        click_node(node)
        return True
    return False


def input_text_at(x: int, y: int, text: str) -> None:
    """在指定坐标输入文本."""
    run(f"uitest uiInput click {x} {y}")
    time.sleep(0.3)
    run(f"uitest uiInput text '{text}'")


def input_text_to_textarea(text: str) -> bool:
    """在 TextArea 输入框中输入文本."""
    node = find_one(type="TextArea")
    if not node:
        return False
    x, y = center(parse_bounds(node["bounds"]))
    input_text_at(x, y, text)
    return True


def screenshot(local_path: str = "/tmp/evoloop_screen.png") -> str:
    """截图并拉取到本地."""
    run(f"uitest screenCap -p {SCREENSHOT_PATH}")
    subprocess.run(f"{HDC} file recv {SCREENSHOT_PATH} {local_path}", shell=True, capture_output=True)
    return local_path


def back() -> None:
    """按返回键."""
    run("uitest uiInput keyEvent Back")


def home() -> None:
    """按 Home 键."""
    run("uitest uiInput keyEvent Home")


def get_current_ability() -> str:
    """获取当前前台 Ability."""
    out = run("aa dump -a")
    for line in out.splitlines():
        if "Mission ID" in line and "com.evoloop.mobile" in line:
            return line.strip()
    return ""


if __name__ == "__main__":
    # 简单测试：打印当前 TextArea 和发送按钮
    nodes = load_nodes()
    print(f"Total nodes: {len(nodes)}")
    ta = find_one(type="TextArea")
    if ta:
        print(f"TextArea: {ta.get('bounds')} hint={ta.get('hint')}")
    send = find_by_text("发送") or find_nodes(type="Custom")[-1]
    if send:
        print(f"Send button candidate: {send.get('bounds')}")
