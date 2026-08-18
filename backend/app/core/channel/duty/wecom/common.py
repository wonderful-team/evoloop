"""企业微信：共享的 GUI 自动化逻辑（会话定位/联系人查找/消息读取）。

被 read.py / reply.py / scan_all.py 复用。
坐标逻辑经实测：会话列表列 x≈250-320，右侧聊天区从 x≈430 起，底部工具条 y>850。
"""
import asyncio
import json
import logging
import os
import time

from app.infrastructure.drivers.macos import macos_driver

logger = logging.getLogger(__name__)

# 系统横幅/导航文本，排除在联系人之外
BAD_CONTACTS = [
    "当前企业", "未认证", "认证", "星期一", "企业使用",
    "我的企业", "单聊", "群聊", "外部聊天", "内部聊天",
    "标记", "未读", "@我", "分组", "高级功能",
    "文档", "日程", "待办", "会议", "智能表格", "智能总结",
    "工作台", "通讯录", "微盘", "消息",
    "管理企业", "前往认证",
    "还不是你的联系人", "请发送", "申请验证",
]


def is_contact_name(t: str) -> bool:
    """判断 OCR 文本是否像会话联系人名。"""
    t = t.strip()
    if not t or len(t) < 2:
        return False
    if any(k in t for k in BAD_CONTACTS):
        return False
    # 过滤纯数字/数值（含小数点，如 160.0、0.0、坐标数值）
    if t.replace(":", "").replace("-", "").replace("/", "").replace(".", "").replace(" ", "").isdigit():
        return False
    # 过滤消息预览（以问号/感叹号结尾的短句，非联系人名）
    if t[-1] in "？！!?":
        return False
    return True


async def check_wecom_ready() -> tuple[bool, str]:
    """检测企业微信值守环境是否就绪（客户端安装 + 已登录 + 会话列表可读）。

    完全后台探测：按企微进程 pid 读 AX 树，不激活/不切换前台窗口。
    就绪标准：
    1. 企业微信客户端已安装
    2. 进程在运行且 AX 树能读到会话列表（未登录时停在登录页，读不到）

    Returns: (ready, reason)。ready=False 时 reason 说明原因。
    """
    return await _probe_wecom_ready()


async def _probe_wecom_ready() -> tuple[bool, str]:
    """后台探测企业微信就绪状态（不激活/不切换前台窗口）。

    按企微进程 pid 读取 AX 树判断是否已登录——完全在后台完成，
    不打扰用户当前操作。
    """
    # 1. 客户端是否已安装
    import shutil

    candidates = [
        "/Applications/企业微信.app",
        os.path.expanduser("~/Applications/企业微信.app"),
    ]
    installed = any(os.path.isdir(p) for p in candidates) or shutil.which("企业微信") is not None
    if not installed:
        return False, "未检测到企业微信客户端，请先安装"

    # 2. 后台读 AX 树（不激活企微）
    elems = await ax_tree_elements()
    if not elems:
        return False, "企业微信未运行或窗口不可读（请先打开企业微信）"
    texts = [e.get("title", "") for e in elems]
    ready = any(k in t for t in texts for k in ("未读", "单聊", "群聊"))
    if ready:
        return True, "企业微信就绪"
    return False, "企业微信未登录或停在登录页，请先登录"


async def open_wecom():
    """打开并激活企业微信，进入"未读"会话列表（待处理的客户消息）。

    企业微信"消息"页默认可能停在服务号/单聊/其他分组，未读消息（客户新发的
    待处理消息）集中在左侧"未读"分组。值守读消息/回复都基于未读视图，用 AX
    定位左侧导航（比 OCR 可靠，避免点错）。
    """
    await asyncio.to_thread(macos_driver.open_app, "企业微信")
    time.sleep(0.8)
    await _ensure_unread_view()


async def _ensure_unread_view():
    """确保会话列表显示"未读"分组（待处理的客户消息）。"""
    await _click_left_nav("未读")


async def _click_left_nav(name: str) -> bool:
    """点击左侧导航分组（如"单聊""未读"）。返回是否点中。

    用 AX 树定位（比 OCR 可靠，坐标稳定）。找不到返回 False 不点击。
    """
    elems = await ax_tree_elements()
    if not elems:
        return False
    for el in elems:
        if el["role"] != "AXStaticText" or el["title"].strip() != name:
            continue
        x, y = el["x"], el["y"]
        if x < 250:
            await asyncio.to_thread(macos_driver.click, x + 15, y + 8)
            time.sleep(0.5)
            return True
    return False


async def current_chat_and_find(contact: str) -> tuple[str | None, tuple | None]:
    """单次 AX dump 同时返回 (当前会话联系人, 目标联系人位置)。

    回复时避免 current_chat_contact + find_contact 两次独立 dump：
    一次 ax_tree_elements 既检测右侧会话标题，又定位左侧会话列表项。
    """
    elems = await ax_tree_elements()
    if not elems:
        return None, None
    # 当前会话标题：右侧聊天区顶部 (x 560-680, y 0-120)
    current = None
    for el in elems:
        if el["role"] != "AXStaticText" or not el["title"]:
            continue
        if 560 < el["x"] < 680 and 0 < el["y"] < 120 and not el["title"].startswith("@"):
            current = el["title"].strip()
            break
    if current:
        current = current.split("@")[0].split("◎")[0].split("®")[0].strip()
        if current in BAD_CONTACTS or any(k in current for k in ("分钟前", "小时前", "昨天", "刚刚")):
            current = None
    # 目标联系人位置
    target = contact.strip().replace(" ", "")
    pos = None
    for el in elems:
        if el["role"] != "AXStaticText" or not el["title"]:
            continue
        t = el["title"].strip()
        if t.startswith("@"):
            continue
        x, y = el["x"], el["y"]
        if 200 < x < 600 and y > 50 and is_contact_name(t):
            if t.replace(" ", "") == target or t.replace(" ", "").startswith(target):
                pos = (x, y)
                break
    return current, pos


WECOM_BUNDLE_ID = "com.tencent.WeWorkMac"


def _wecom_pid() -> int | None:
    """后台查找企业微信主进程 pid（按 bundle id），不激活/不切换前台。"""
    try:
        import AppKit

        apps = AppKit.NSWorkspace.sharedWorkspace().runningApplications()
        for app in apps:
            if (app.bundleIdentifier() or "") == WECOM_BUNDLE_ID:
                return int(app.processIdentifier())
    except Exception as e:
        logger.warning("[wecom_common] 查找企微 pid 失败: %s", e)
    return None


async def ax_tree_elements() -> list[dict]:
    """读取企业微信完整 AX 树，返回结构化元素列表 [{role, x, y, title}]。

    按企微进程 pid 后台读取（不激活/不切换前台窗口，避免打扰用户）。
    保留 role（AXButton/AXStaticText 等）和精确坐标，用于区分联系人名、
    未读红点（AXButton title=数字）、消息预览。失败返回 []。
    """
    pid = _wecom_pid()
    tree = await asyncio.wait_for(
        asyncio.to_thread(macos_driver.dump_ax_tree, pid), timeout=10
    )
    if not tree or not isinstance(tree, str) or tree.strip() in ("[]", ""):
        return []

    try:
        elems = json.loads(tree)
    except Exception:
        return []
    out = []
    for el in elems:
        if not isinstance(el, dict):
            continue
        title = (el.get("title") or el.get("value") or el.get("name") or "").strip()
        b = el.get("bounds")
        if not isinstance(b, list) or len(b) != 4:
            continue
        out.append({
            "role": el.get("role", ""),
            "x": int(b[0]),
            "y": int(b[1]),
            "title": title,
        })
    return out


async def scan_unread_view() -> list[tuple]:
    """扫描未读视图并返回有未读红点的联系人（最少一次 AX dump）。

    一次 dump 同时：1) 判断是否在未读视图（有无红点）；2) 定位「未读」导航
    坐标。若当前已在未读视图（有红点）→ 直接用这次 dump；否则点击「未读」
    导航切换后重新 dump。避免盲目先切视图再扫的两次浪费。
    """
    elems = await ax_tree_elements()
    if not elems:
        return []
    contacts = _find_unread_from_elems(elems)
    if contacts:
        return contacts
    # 当前不在未读视图：定位「未读」导航并点击切换，再 dump
    nav = None
    for el in elems:
        if el["role"] == "AXStaticText" and el["title"].strip() == "未读" and el["x"] < 250:
            nav = el
            break
    if nav is None:
        return []
    await asyncio.to_thread(macos_driver.click, nav["x"] + 15, nav["y"] + 8)
    time.sleep(0.5)
    elems2 = await ax_tree_elements()
    return _find_unread_from_elems(elems2) if elems2 else []


def _find_unread_from_elems(elems: list[dict]) -> list[tuple]:
    """从一次 AX dump 的元素中找出有未读红点的联系人。

    未读红点：AXButton title=数字。红点通常位于联系人列表项右侧/同列，
    其所在行（y 接近）且 x 接近的红点旁即为联系人名。不写死 x 列范围
    （企微窗口布局可左列/中列变化，x 列会漂移），用红点位置就近匹配。
    返回 [(x, y, name, unread_count, preview)]。
    """
    # 1. 找所有未读红点（AXButton title=数字，排除底部工具栏/远离联系人列的）
    #    排除左侧导航栏的角标数字（x<250，如"单聊"分组计数）：那些是分组/会话
    #    导航计数，不是联系人未读红点，误匹配会导致把导航角标当联系人未读，
    #    每轮空扫同一个联系人且永不消除。
    red_dots = []
    for el in elems:
        if el["role"] == "AXButton" and el["title"].strip().isdigit():
            if el["x"] < 250:
                continue
            red_dots.append(el)

    # 2. 收集所有联系人名候选（AXStaticText，排除系统横幅/时间/消息预览）
    #    限制：会话列表列（x<600，排除聊天区时间戳/右侧文本）+ 短文本
    #    （联系人名短，消息预览/回复是长文本，避免被误当联系人名）。
    name_candidates = []
    for el in elems:
        if el["role"] != "AXStaticText" or not el["title"]:
            continue
        x = el["x"]
        # 会话列表列（左侧联系人列表），排除聊天区（x>1000 的时间戳/文本）
        if not (x < 600):
            continue
        t = el["title"].strip()
        if not t or t.startswith("@") or t in BAD_CONTACTS:
            continue
        if any(k in t for k in ("分钟前", "小时前", "昨天", "前天", "刚刚", "天前")):
            continue
        # 联系人名是短文本；消息预览/回复是长文本，排除
        if len(t) > 15:
            continue
        name_candidates.append(el)

    contacts = []
    for dot in red_dots:
        dx, dy = dot["x"], dot["y"]
        # 红点旁的联系人名：y 差 < 30px 且 x 差 < 120px（红点与名同行/相邻列）
        best = None
        for el in name_candidates:
            if abs(el["y"] - dy) < 30 and abs(el["x"] - dx) < 120:
                if best is None or abs(el["y"] - dy) < abs(best["y"] - dy):
                    best = el
        if best is None:
            continue
        name = best["title"].strip()
        # 找预览（联系人名下方 5~40px，同一 x 列）
        preview = ""
        for el in elems:
            if el["role"] != "AXStaticText" or not el["title"]:
                continue
            if best["y"] < el["y"] < best["y"] + 40 and abs(el["x"] - best["x"]) < 30:
                t = el["title"].strip()
                if t and not any(k in t for k in ("分钟前", "小时前", "昨天", "刚刚")):
                    preview = t
                    break
        contacts.append((best["x"], best["y"], name, int(dot["title"]), preview))
    contacts.sort(key=lambda c: c[1])
    return contacts


async def click_contact(pos: tuple) -> None:
    """点击联系人（列表项中间偏右）。"""
    x, y = pos
    await asyncio.to_thread(macos_driver.click, x + 20, y + 8)
    time.sleep(0.4)


async def read_chat_messages_ax() -> list[tuple]:
    """用 AX 树读取当前打开会话的聊天消息，返回 [(x, y, text)] 按位置排序。

    企微 AX 聊天区不暴露气泡方向，客户消息与我方回复的 x 坐标重叠，无法靠
    x 区分发送方（见 read_processed_texts 注释）。因此这里**不做左右过滤**，
    返回聊天区全部消息文本；增量判定交由 read_customer_messages 用 jsonl
    历史去重（唯一事实源），避免把 Agent 自己的回复误读为客户新消息。
    """
    elems = await ax_tree_elements()
    if not elems:
        return []
    msgs = []
    for el in elems:
        if el["role"] != "AXTextArea" or not el["title"]:
            continue
        x, y = el["x"], el["y"]
        t = el["title"].strip()
        if t and len(t) > 1:
            msgs.append((x, y, t))
    msgs.sort(key=lambda m: m[1])
    return msgs


def history_jsonl_path(history_dir: str, contact: str) -> str:
    """联系人对应的 jsonl 历史文件路径（机器判增量的唯一事实源）。"""
    fname = f"{contact.replace(' ', '_').replace('@', '').replace('/', '_')}.jsonl"
    return os.path.join(history_dir, fname)


def read_jsonl_records(history_dir: str, contact: str) -> list[dict]:
    """读联系人 jsonl 历史，返回消息记录列表（按 seq 升序）。"""
    fpath = history_jsonl_path(history_dir, contact)
    if not os.path.exists(fpath):
        return []
    records = []
    try:
        with open(fpath, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except (ValueError, TypeError):
                    logger.warning("[wecom_common] 跳过损坏 jsonl 行: %r", line[:60])
    except OSError:
        return []
    return records


def read_processed_texts(history_dir: str, contact: str) -> set[str]:
    """读联系人 jsonl 中已记录的「客户」消息文本集合（增量基准）。

    jsonl 记录了该联系人已读/已处理过的会话消息；企微会话里 jsonl 中
    未出现的客户消息文本即为「新增客户消息」。基准包含 human（客户消息）
    **与 ai（我方回复）** 两类：两者都是「已处理过」的记录，聊天区再次读到
    时都应跳过，只保留 jsonl 中完全没有的全新文本（即客户新消息）。

    注意：企微 AX 聊天区不暴露气泡方向，客户消息与客服回复的 x 坐标
    重叠，无法靠 x 区分；因此增量判定必须以 jsonl 全量文本为唯一事实源，
    否则客服回复会被误判为客户新消息反复处理。
    """
    return {
        r.get("text", "").strip()
        for r in read_jsonl_records(history_dir, contact)
        if r.get("text", "").strip()
    }


def append_history(history_dir: str, contact: str, messages: list[str], role: str = "human") -> None:
    """把新增消息追加写入联系人 jsonl 历史。

    jsonl 每行 {"seq", "ts", "role", "text"}，seq 按现有最后一条递增。
    role 取值：human（客户）/ ai（Agent 回复）。仅服务机器增量判定。
    """
    if not messages:
        return
    os.makedirs(history_dir, exist_ok=True)
    ts = time.strftime("%Y-%m-%d %H:%M:%S")

    # next_seq = 现有最后一条的 seq + 1（只读末行，避免全文件扫描）
    jl_path = history_jsonl_path(history_dir, contact)
    next_seq = 1
    if os.path.exists(jl_path):
        try:
            with open(jl_path, "rb") as f:
                f.seek(0, 2)
                size = f.tell()
                if size:
                    f.seek(max(0, size - 4096))
                    tail = f.read().decode("utf-8", errors="ignore")
                    last_line = tail.strip().splitlines()[-1]
                    last = json.loads(last_line)
                    next_seq = int(last.get("seq", 0)) + 1
        except (ValueError, TypeError, IndexError, OSError):
            pass  # 末行损坏则从 1 重新编号（append 语义下极少发生）
    with open(jl_path, "a", encoding="utf-8") as f:
        for t in messages:
            rec = {"seq": next_seq, "ts": ts, "role": role, "text": t}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            next_seq += 1


_SYSTEM_MESSAGE_MARKS = (
    "撤回了一条消息",
    "你撤回了一条消息",
    "已加入群聊",
    "加入群聊",
    "你已添加",
    "邀请了",
    "拍了拍",
    "退出了群聊",
    "群公告",
    "以下为新成员",
    "撤回后重新编辑",
)


def _is_system_message(text: str) -> bool:
    """判断消息是否为企微系统提示（撤回/入群等非对话消息）。

    系统提示不是客户业务咨询，不应作为「客户新消息」处理。
    """
    return any(m in text for m in _SYSTEM_MESSAGE_MARKS)


async def read_customer_messages(contact: str, history_dir: str, unread_count: int = 0) -> list[str]:
    """点开指定联系人会话，读取并返回「新增的客户消息」列表。

    以企微「未读数」为新增消息数量的可靠信号（未读红点 = 客户新发的待处理
    消息数）。读聊天区消息，按位置（y）排序，**只取底部最新 unread_count 条
    客户消息**，其余历史消息不作为新增处理（避免 jsonl 清空后历史被当新增、
    Agent 重复回复多轮）。排除系统提示（撤回/入群等）。

    注意：读取聊天区需要企微在前台（AX 坐标才准确、点击才生效），故先激活
    企微到前台；操作后**不切回**（值守接管企微，符合语义）。
    """
    await open_wecom()
    current, pos = await current_chat_and_find(contact)
    if current != contact:
        if not pos:
            return []
        await click_contact(pos)
    msgs = await read_chat_messages_ax()
    # 按 y 排序（最新消息在底部，y 最大）
    msgs.sort(key=lambda m: m[1])
    # 过滤系统提示，取客户侧消息
    customer_msgs = []
    for _x, _y, text in msgs:
        t = text.strip()
        if not t:
            continue
        if _is_system_message(t):
            continue
        customer_msgs.append(t)
    # 去重（保持底部最新优先）
    seen = set()
    dedup = []
    for t in reversed(customer_msgs):
        if t not in seen:
            seen.add(t)
            dedup.append(t)
    dedup.reverse()
    # 只取最新 unread_count 条（未读数是新增消息数量信号）
    if unread_count > 0 and len(dedup) > unread_count:
        result = dedup[-unread_count:]
    else:
        result = dedup
    # 【关键】用 jsonl 历史去重：已处理过的文本（含 human 客户消息 + ai
    # 我方回复）都跳过，只保留 jsonl 中完全没有的全新客户消息。企微 AX
    # 聊天区不暴露气泡方向，无法靠 x 区分发送方，若不按 jsonl 全量文本过滤，
    # Agent 自己的回复会被误判为客户新消息反复处理（值守死循环）。
    if result:
        processed = read_processed_texts(history_dir, contact)
        result = [t for t in result if t not in processed]
    if result:
        append_history(history_dir, contact, result, role="human")
    return result
