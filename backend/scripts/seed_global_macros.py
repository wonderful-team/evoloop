"""内置全局 OS 级宏脚本（L0 语音快速道）。

先清空 macros 表，再插入全部内置全局宏。

设计原则：
  - 只放纯动作类（执行完即止，无需 TTS 回读）
  - 查询类（IP/电量/时间等）走 Agent 路径，不在此列
  - 应用起停用参数化 slot `{app}`，不逐个写独立宏
  - 成对开关尽量用 toggle 或独立但不膨胀

所有宏: project_id=NULL, status="verified", is_active=True,
parameters=[], namespace="preset", risk_tier="ui", requires_confirmation=False.

执行::

    cd evoloop/backend && uv run python scripts/seed_global_macros.py
"""

import asyncio
import os
import sys

sys.path.append(os.getcwd())

# ─── Helper ────────────────────────────────────────────────────────────


def yaml_action(event_type: str, source: str = "desktop", **kw) -> str:
    lines = [
        f"- type: action",
        f"  event_type: {event_type}",
        f"  source: {source}",
    ]
    if kw:
        lines.append("  payload:")
        for k, v in kw.items():
            lines.append(f"    {k}: {v}")
    return "\n".join(lines) + "\n"


def yaml_applescript(script: str) -> str:
    return yaml_action("applescript", script=script)


def yaml_open_app(app_name: str) -> str:
    return yaml_action("open_app", app_name=app_name)


def yaml_open_app_slot() -> str:
    return yaml_action("open_app", app_name="{{ app }}")


def yaml_quit_app_slot() -> str:
    return yaml_applescript('tell application "{{ app }}" to quit')


def yaml_key_press(key: str) -> str:
    return yaml_action("key_press", key=key)


def yaml_keystroke(keystroke: str, using: str | None = None) -> str:
    script = f'tell application "System Events" to keystroke "{keystroke}"'
    if using:
        script += f" using {using}"
    return yaml_applescript(script)


_BROWSERS = ["Google Chrome", "Safari", "Microsoft Edge", "Firefox", "Arc", "Brave Browser", "Opera", "Vivaldi"]


def yaml_browser_keystroke(keystroke: str, using: str | None = None) -> str:
    keystroke_script = f'keystroke "{keystroke}"'
    if using:
        keystroke_script += f" using {using}"
    browsers_str = ", ".join(f'"{b}"' for b in _BROWSERS)
    return yaml_applescript(
        'tell application "System Events"\n'
        f'  set frontApp to name of first process whose frontmost is true\n'
        f'  if frontApp is in {{{browsers_str}}} then\n'
        f'    {keystroke_script}\n'
        f'  end if\n'
        f'end tell'
    )


def yaml_finder_keystroke(keystroke: str, using: str | None = None) -> str:
    keystroke_script = f'keystroke "{keystroke}"'
    if using:
        keystroke_script += f" using {using}"
    return yaml_applescript(
        'tell application "System Events"\n'
        f'  set frontApp to name of first process whose frontmost is true\n'
        f'  if frontApp is "Finder" then\n'
        f'    {keystroke_script}\n'
        f'  end if\n'
        f'end tell'
    )


def yaml_website_script() -> str:
    sites = [
        ("淘宝", "https://www.taobao.com"),
        ("京东", "https://www.jd.com"),
        ("百度", "https://www.baidu.com"),
        ("B站", "https://www.bilibili.com"),
        ("哔哩哔哩", "https://www.bilibili.com"),
        ("微博", "https://www.weibo.com"),
        ("知乎", "https://www.zhihu.com"),
        ("抖音", "https://www.douyin.com"),
        ("小红书", "https://www.xiaohongshu.com"),
        ("闲鱼", "https://www.goofish.com"),
        ("拼多多", "https://www.pinduoduo.com"),
        ("网易云", "https://music.163.com"),
        ("豆瓣", "https://www.douban.com"),
        ("GitHub", "https://github.com"),
        ("腾讯视频", "https://v.qq.com"),
        ("美团", "https://www.meituan.com"),
        ("天猫", "https://www.tmall.com"),
        ("优酷", "https://www.youku.com"),
        ("爱奇艺", "https://www.iqiyi.com"),
        ("Gmail", "https://mail.google.com"),
        ("必应", "https://www.bing.com"),
        ("CSDN", "https://www.csdn.net"),
        ("Stack", "https://stackoverflow.com"),
    ]
    lines = ["on getURL(siteName)"]
    for keyword, url in sites:
        lines.append(f'  if siteName contains "{keyword}" then return "{url}"')
    lines.append('  return "https://www." & siteName & ".com"')
    lines.append("end getURL")
    lines.append('open location getURL("{{ site }}")')
    return yaml_applescript("\n".join(lines))


def yaml_settings_script() -> str:
    panels = [
        ("WiFi", "com.apple.wifi-settings-extension"),
        ("无线", "com.apple.wifi-settings-extension"),
        ("网络", "com.apple.wifi-settings-extension"),
        ("蓝牙", "com.apple.BluetoothSettings"),
        ("声音", "com.apple.preference.sound"),
        ("显示", "com.apple.preference.displays"),
        ("屏幕", "com.apple.preference.displays"),
        ("键盘", "com.apple.preference.keyboard"),
        ("壁纸", "com.apple.preference.wallpaper"),
        ("桌面", "com.apple.preference.wallpaper"),
        ("通用", "com.apple.preference.general"),
        ("通知", "com.apple.preference.notifications"),
        ("隐私", "com.apple.preference.security"),
        ("安全", "com.apple.preference.security"),
        ("电池", "com.apple.preference.battery"),
        ("触控", "com.apple.preference.trackpad"),
        ("鼠标", "com.apple.preference.mouse"),
        ("显示器", "com.apple.preference.displays"),
    ]
    lines = ["on getPrefPane(name)"]
    for keyword, pane in panels:
        lines.append(f'  if name contains "{keyword}" then return "{pane}"')
    lines.append('  return "com.apple.preference.general"')
    lines.append("end getPrefPane")
    lines.append('open location "x-apple.systempreferences:" & getPrefPane("{{ panel }}")')
    return yaml_applescript("\n".join(lines))


# ─── 宏定义 ─────────────────────────────────────────────────────────────

MACROS = [
    # ═══════════════════════════════════════════════════════════════════
    # 🔊 音量控制 (7)
    # ═══════════════════════════════════════════════════════════════════
    {
        "name": "静音",
        "description": "静音系统音量",
        "trigger_patterns": [
            "静音", "别出声", "不要声音", "安静",
            "把声音关了", "关掉声音", "没声音了",
            "不想听到声音", "不要吵", "声音关了",
        ],
        "macro_script": yaml_applescript("set volume with output muted"),
    },
    {
        "name": "取消静音",
        "description": "取消静音",
        "trigger_patterns": [
            "取消静音", "恢复声音", "打开声音", "不静音了",
            "声音回来", "恢复音量", "解除静音",
            "把声音打开", "重新出声", "取消静音模式",
        ],
        "macro_script": yaml_applescript("set volume without output muted"),
    },
    {
        "name": "音量增大",
        "description": "音量调大 10%",
        "trigger_patterns": [
            "音量大一点", "调高音量", "大声一点", "声音大一点", "调大音量",
            "声音调大", "音量再大一些", "再大声点", "把声音调大",
            "大点声", "提高音量", "加大音量", "声音再大一点",
        ],
        "macro_script": yaml_applescript(
            "set volume output volume ((output volume of (get volume settings)) + 10)"
        ),
    },
    {
        "name": "音量减小",
        "description": "音量调小 10%",
        "trigger_patterns": [
            "音量小一点", "调低音量", "小声一点", "声音小一点", "调小音量",
            "声音调小", "音量再小一些", "小声点", "把声音调小",
            "声音太大了", "关小点", "降低音量", "减小音量", "声音太大了关小点",
        ],
        "macro_script": yaml_applescript(
            "set volume output volume ((output volume of (get volume settings)) - 10)"
        ),
    },
    {
        "name": "最大音量",
        "description": "音量调到最大",
        "trigger_patterns": [
            "音量最大", "最大声", "声音调到最大", "最大音量",
            "音量满格", "声音拉到最大", "开到最大",
            "把音量拉满", "声音最大", "最大声儿",
        ],
        "macro_script": yaml_applescript("set volume output volume 100"),
    },
    {
        "name": "一半音量",
        "description": "音量调到一半",
        "trigger_patterns": [
            "音量一半", "音量中等", "声音一半",
            "声音调到一半", "音量适中", "不大不小",
            "中等音量", "一半就行", "调到一半",
        ],
        "macro_script": yaml_applescript("set volume output volume 50"),
    },
    {
        "name": "最小音量",
        "description": "音量调到最小",
        "trigger_patterns": [
            "音量最小", "最小声", "声音最小",
            "声音调到最小", "音量调到最低",
            "几乎没声", "一点点声音", "最小声儿",
        ],
        "macro_script": yaml_applescript("set volume output volume 0"),
    },
    # ═══════════════════════════════════════════════════════════════════
    # ▶️ 播放控制 (7)
    # ═══════════════════════════════════════════════════════════════════
    {
        "name": "播放暂停",
        "description": "播放或暂停当前媒体",
        "trigger_patterns": [
            "暂停", "继续播放", "开始播放", "继续", "接着放",
            "停一下", "别放了", "先停", "暂停播放",
            "放一下", "播起来", "开始放", "别播了", "先暂停",
        ],
        "macro_script": yaml_applescript('tell application "System Events" to key code 16'),
    },
    {
        "name": "下一曲",
        "description": "下一首 / 下一曲",
        "trigger_patterns": [
            "下一首", "下一曲", "切歌", "换一首", "下首歌",
            "换歌", "切一下", "下一支",
            "换一首听听", "听下一首", "跳过", "跳过去",
        ],
        "macro_script": yaml_applescript('tell application "System Events" to key code 17'),
    },
    {
        "name": "上一曲",
        "description": "上一首 / 上一曲",
        "trigger_patterns": [
            "上一首", "上一曲", "回上一首", "上一首歌",
            "返回上一首", "倒回去", "上一支",
            "回上一曲", "放上一首", "回到上一首",
        ],
        "macro_script": yaml_applescript('tell application "System Events" to key code 15'),
    },
    {
        "name": "快进",
        "description": "视频/音频向前快进几秒",
        "trigger_patterns": [
            "快进", "往前跳", "跳过去", "快进一下",
            "往后跳", "往前走一点", "跳过这段",
            "快进几秒", "往前快进",
        ],
        "macro_script": yaml_applescript('tell application "System Events" to key code 124'),
    },
    {
        "name": "快退",
        "description": "视频/音频向后退回几秒",
        "trigger_patterns": [
            "快退", "往后退", "倒回去", "后退一下",
            "回退几秒", "退回去", "倒回一点",
            "退回几秒", "往回倒",
        ],
        "macro_script": yaml_applescript('tell application "System Events" to key code 123'),
    },
    {
        "name": "加速播放",
        "description": "视频倍速加快播放",
        "trigger_patterns": [
            "加速", "加速播放", "倍速", "加快速度",
            "放快一点", "速度快一点", "提速",
            "加个速", "倍速播放",
        ],
        "macro_script": yaml_applescript(
            'tell application "System Events" to keystroke "." using shift down'
        ),
    },
    {
        "name": "减速播放",
        "description": "视频倍速减慢播放",
        "trigger_patterns": [
            "减速", "减速播放", "减慢速度", "放慢一点",
            "速度慢一点", "慢放", "慢一点",
            "速度降一点", "放慢速度",
        ],
        "macro_script": yaml_applescript(
            'tell application "System Events" to keystroke "," using shift down'
        ),
    },
    {
        "name": "跳转到时间",
        "description": "在 QuickTime Player 中跳转到指定时间位置",
        "trigger_patterns": [
            "跳到{time}", "跳到{time}处",
            "调到{time}", "调到{time}处",
            "跳到{time}位置", "调到{time}位置",
        ],
        "parameters": [{"name": "time", "type": "str"}],
        "macro_script": yaml_action("applescript", script=(  # noqa: E501
            "on parseTime(timeStr)\n"
            "  set totalSeconds to 0\n"
            '  set text item delimiters of AppleScript to {"小时", "时"}\n'
            "  set parts to text items of timeStr\n"
            "  if (count of parts) > 1 then\n"
            "    try\n"
            "      set totalSeconds to totalSeconds + ((item 1 of parts) as integer) * 3600\n"
            "    end try\n"
            "    set timeStr to item 2 of parts\n"
            "  end if\n"
            '  set text item delimiters of AppleScript to {"分", "分钟"}\n'
            "  set parts to text items of timeStr\n"
            "  if (count of parts) > 1 then\n"
            "    try\n"
            "      set totalSeconds to totalSeconds + ((item 1 of parts) as integer) * 60\n"
            "    end try\n"
            "    set timeStr to item 2 of parts\n"
            "  end if\n"
            '  set text item delimiters of AppleScript to {"秒"}\n'
            "  set parts to text items of timeStr\n"
            "  if (count of parts) > 1 then\n"
            "    try\n"
            "      set totalSeconds to totalSeconds + ((item 1 of parts) as integer)\n"
            "    end try\n"
            "  end if\n"
            '  set text item delimiters of AppleScript to {""}\n'
            "  if totalSeconds is 0 then\n"
            "    try\n"
            "      set totalSeconds to timeStr as number\n"
            "      if totalSeconds < 100 then set totalSeconds to totalSeconds * 60\n"
            "    end try\n"
            "  end if\n"
            "  return totalSeconds\n"
            "end parseTime\n"
            'set targetSeconds to parseTime("{{ time }}")\n'
            "if targetSeconds > 0 then\n"
            '  tell application "QuickTime Player"\n'
            "    if exists document 1 then\n"
            "      set current time of document 1 to targetSeconds\n"
            "    end if\n"
            "  end tell\n"
            "end if"
        )),
    },
    # ═══════════════════════════════════════════════════════════════════
    # 🖥️ 系统操作 (5)
    # ═══════════════════════════════════════════════════════════════════
    {
        "name": "锁屏",
        "description": "锁定屏幕",
        "trigger_patterns": [
            "锁屏", "锁定屏幕", "锁电脑", "锁一下",
            "把电脑锁了", "锁定", "帮我锁屏",
            "把屏幕锁住", "锁住电脑", "离开锁屏",
        ],
        "macro_script": yaml_applescript(
            'do shell script "/System/Library/CoreServices/Menu\\\\ Extras/User.menu/Contents/Resources/CGSession -suspend"'
        ),
    },
    {
        "name": "息屏",
        "description": "关闭显示器",
        "trigger_patterns": [
            "息屏", "关屏幕", "关闭显示器",
            "把屏幕关了", "关掉屏幕", "屏幕息掉",
            "让屏幕休息", "关了显示器", "息一下屏",
        ],
        "macro_script": yaml_applescript("do shell script \"pmset displaysleepnow\""),
    },
    {
        "name": "深色模式",
        "description": "切换深色/浅色模式",
        "trigger_patterns": [
            "切换深色模式", "暗色模式", "夜间模式", "切换外观模式",
            "深色模式", "换成暗色", "换深色",
            "改暗色模式", "切深色", "深色切换",
            "浅色模式", "换成浅色", "切回浅色",
        ],
        "macro_script": yaml_applescript(
            'tell application "System Events" to tell appearance preferences to set dark mode to not dark mode'
        ),
    },
    {
        "name": "清空废纸篓",
        "description": "清空回收站",
        "trigger_patterns": [
            "清空废纸篓", "清倒废纸篓", "清空垃圾桶",
            "清理回收站", "把废纸篓清一下", "垃圾桶清一下",
            "清一下回收站", "废纸篓满了", "帮我清空废纸篓",
        ],
        "macro_script": yaml_applescript('tell application "Finder" to empty trash'),
    },
    {
        "name": "弹出磁盘",
        "description": "弹出所有外置磁盘",
        "trigger_patterns": [
            "弹出磁盘", "弹出U盘", "推出外置盘", "弹出所有磁盘",
            "把U盘弹出来", "推出磁盘", "安全弹出",
            "退出磁盘", "弹出外接设备", "弹出来",
        ],
        "macro_script": yaml_applescript(
            'tell application "Finder" to eject (every disk whose ejectable is true)'
        ),
    },
    # ═══════════════════════════════════════════════════════════════════
    # 📸 截图 (4)
    # ═══════════════════════════════════════════════════════════════════
    {
        "name": "截屏",
        "description": "全屏截图到桌面",
        "trigger_patterns": [
            "截图", "截屏", "屏幕截图", "截个图", "截一下屏",
            "帮我截个图", "截屏保存", "拍张截图",
            "给我截张图", "截一下屏幕", "抓个图",
        ],
        "macro_script": yaml_action("screenshot"),
    },
    {
        "name": "区域截屏",
        "description": "交互选择区域截图",
        "trigger_patterns": [
            "区域截图", "截取选定区域", "选区截图", "截一块",
            "帮我截一块区域", "选区域截屏", "截图一块地方",
            "截选中的区域", "框选截图", "截个区域",
        ],
        "macro_script": yaml_applescript(
            "do shell script \"screencapture -i ~/Desktop/screenshot_$(date +%Y%m%d_%H%M%S).png\""
        ),
    },
    {
        "name": "截屏到剪贴板",
        "description": "全屏截图并复制到剪贴板",
        "trigger_patterns": [
            "截图复制", "截图到剪贴板", "截图不保存", "截图放剪贴板",
            "截图拷贝", "截完直接复制", "截图放到粘贴板",
            "截图不存文件", "截图到粘贴板",
        ],
        "macro_script": yaml_applescript("do shell script \"screencapture -c\""),
    },
    {
        "name": "定时截屏",
        "description": "5 秒后截图",
        "trigger_patterns": [
            "定时截图", "延时截图", "倒计时截图", "稍后截图",
            "等会儿再截", "五秒后截图", "晚点帮我截图",
            "过一会儿截图", "延时截屏", "延迟截图",
        ],
        "macro_script": yaml_applescript(
            "do shell script \"screencapture -T 5 ~/Desktop/timed_$(date +%Y%m%d_%H%M%S).png\""
        ),
    },
    # ═══════════════════════════════════════════════════════════════════
    # 🗔 窗口管理 (6)
    # ═══════════════════════════════════════════════════════════════════
    {
        "name": "隐藏窗口",
        "description": "隐藏当前应用的所有窗口",
        "trigger_patterns": [
            "隐藏", "隐藏窗口", "隐藏当前", "先藏起来",
            "把窗口藏了", "藏起来", "把这个藏了",
            "收起来", "隐藏掉", "先收起来",
        ],
        "macro_script": yaml_keystroke("h", using="command down"),
    },
    {
        "name": "隐藏其他",
        "description": "隐藏其他应用的窗口，只保留当前",
        "trigger_patterns": [
            "隐藏其他", "只保留当前", "隐藏其他窗口",
            "只看当前", "别的都隐藏", "其他都藏了",
            "只看这个", "把其他的隐藏", "只留当前窗口",
        ],
        "macro_script": yaml_keystroke("h", using="{option down, command down}"),
    },
    {
        "name": "最小化",
        "description": "最小化当前窗口",
        "trigger_patterns": [
            "最小化", "最小化窗口", "收起窗口",
            "收到任务栏", "缩下去", "把窗口最小化",
            "收到下面", "缩到最小",
        ],
        "macro_script": yaml_keystroke("m", using="command down"),
    },
    {
        "name": "全屏",
        "description": "当前窗口全屏/退出全屏",
        "trigger_patterns": [
            "全屏", "最大化", "全屏窗口", "最大化窗口", "全屏显示",
            "全屏模式", "全屏看", "放大到全屏",
            "铺满屏幕", "退出全屏", "不要全屏了",
        ],
        "macro_script": yaml_keystroke("f", using="{command down, control down}"),
    },
    {
        "name": "关闭窗口",
        "description": "关闭当前窗口",
        "trigger_patterns": [
            "关闭窗口", "关掉当前", "关闭当前窗口", "把窗口关掉",
            "把这个关了", "关了这个", "叉掉",
            "关闭这个页面", "结束当前窗口", "关掉",
        ],
        "macro_script": yaml_keystroke("w", using="command down"),
    },
    {
        "name": "强制退出",
        "description": "打开强制退出应用程序窗口",
        "trigger_patterns": [
            "强制退出", "结束任务", "强退", "强制关闭",
            "程序卡死了", "卡住了", "没反应了",
            "强制结束", "关不掉", "卡死了帮我关了",
        ],
        "macro_script": yaml_applescript(
            'tell application "System Events" to keystroke (key code 53) using {option down, command down}'
        ),
    },
    # ═══════════════════════════════════════════════════════════════════
    # 📋 通用编辑 (7)
    # ═══════════════════════════════════════════════════════════════════
    {
        "name": "撤销",
        "description": "撤销上一步操作",
        "trigger_patterns": [
            "撤销", "撤回", "回退", "取消上一步",
            "撤销刚才的操作", "后退一步", "撤回去",
            "取消刚才的", "返回上一步", "不做了撤销",
        ],
        "macro_script": yaml_keystroke("z", using="command down"),
    },
    {
        "name": "重做",
        "description": "重做已撤销的操作",
        "trigger_patterns": [
            "重做", "恢复撤销", "重新做",
            "撤销撤回", "把撤销的恢复", "再做一次",
            "恢复操作", "重新来",
        ],
        "macro_script": yaml_keystroke("z", using="{shift down, command down}"),
    },
    {
        "name": "剪切",
        "description": "剪切选中内容到剪贴板",
        "trigger_patterns": [
            "剪切", "剪下", "剪掉",
            "剪切选中", "剪了", "剪走",
            "剪切掉", "把这段剪了",
        ],
        "macro_script": yaml_keystroke("x", using="command down"),
    },
    {
        "name": "复制",
        "description": "复制选中内容到剪贴板",
        "trigger_patterns": [
            "复制", "拷贝", "复制选中",
            "复制一下", "复制这个", "抄下来",
            "拷贝一下", "把这个复制了",
        ],
        "macro_script": yaml_keystroke("c", using="command down"),
    },
    {
        "name": "粘贴",
        "description": "粘贴剪贴板内容",
        "trigger_patterns": [
            "粘贴", "粘贴出来", "贴出来",
            "粘一下", "粘出来", "贴上去",
            "把内容贴出来",
        ],
        "macro_script": yaml_keystroke("v", using="command down"),
    },
    {
        "name": "全选",
        "description": "全选当前内容",
        "trigger_patterns": [
            "全选", "选中全部", "全部选中",
            "全选了", "全部选上", "把全部选了",
            "选中所有",
        ],
        "macro_script": yaml_keystroke("a", using="command down"),
    },
    {
        "name": "保存",
        "description": "保存当前文档",
        "trigger_patterns": [
            "保存", "存档", "存盘", "保存文件", "保存一下",
            "先存一下", "存了", "存起来", "保存当前",
        ],
        "macro_script": yaml_keystroke("s", using="command down"),
    },
    # ═══════════════════════════════════════════════════════════════════
    # 🌐 浏览器 (6)
    # ═══════════════════════════════════════════════════════════════════
    {
        "name": "新建标签页",
        "description": "在浏览器中新建标签页",
        "trigger_patterns": [
            "新建标签页", "新建标签", "打开新标签", "新开一页", "新标签",
            "再开一个标签页", "新开一个页面", "打开一个新的标签",
            "加一个页面", "多开一个标签",
        ],
        "macro_script": yaml_browser_keystroke("t", using="command down"),
    },
    {
        "name": "关闭标签页",
        "description": "关闭当前浏览器标签页",
        "trigger_patterns": [
            "关闭标签页", "关闭标签", "关掉标签页", "关掉标签",
            "关掉这一页", "把这个标签关了", "关一下这个页面",
            "把当前页关掉", "关了这个标签",
        ],
        "macro_script": yaml_browser_keystroke("w", using="command down"),
    },
    {
        "name": "恢复标签页",
        "description": "恢复刚刚关闭的标签页",
        "trigger_patterns": [
            "恢复标签", "打开刚关的", "恢复刚关的标签", "不小心关了",
            "把刚才关的打开", "恢复上一个标签", "找回刚关的页面",
            "刚关的那个找回来",
        ],
        "macro_script": yaml_browser_keystroke("t", using="{shift down, command down}"),
    },
    {
        "name": "刷新",
        "description": "刷新当前页面",
        "trigger_patterns": [
            "刷新", "重新加载", "刷新页面", "刷新一下", "重新载入",
            "刷新当前页", "重载页面", "刷新看看",
            "页面不动了刷新一下",
        ],
        "macro_script": yaml_keystroke("r", using="command down"),
    },
    {
        "name": "后退",
        "description": "浏览器后退到上一页",
        "trigger_patterns": [
            "后退", "返回", "上一页", "后退一页",
            "往前一页", "回到上一页", "后退一下",
            "返回前一个页面", "回上一页",
        ],
        "macro_script": yaml_applescript(
            'tell application "System Events" to keystroke "[" using command down'
        ),
    },
    {
        "name": "前进",
        "description": "浏览器前进到下一页",
        "trigger_patterns": [
            "前进", "向前", "往前", "前进一页",
            "往后一页", "前进一下", "向前一页",
        ],
        "macro_script": yaml_applescript(
            'tell application "System Events" to keystroke "]" using command down'
        ),
    },
    # ═══════════════════════════════════════════════════════════════════
    # 🤖 应用打开/退出 (2个参数化宏)
    # ═══════════════════════════════════════════════════════════════════
    {
        "name": "打开应用",
        "description": "打开指定的应用",
        "trigger_patterns": [
            "打开{app}", "启动{app}", "开一下{app}",
            "帮我打开{app}", "把{app}打开",
            "帮我启动{app}", "运行{app}", "我要用{app}",
        ],
        "parameters": [{"name": "app", "type": "app"}],
        "macro_script": yaml_open_app_slot(),
    },
    {
        "name": "退出应用",
        "description": "退出指定的应用",
        "trigger_patterns": [
            "退出{app}", "关闭{app}", "关掉{app}",
            "把{app}退出了", "帮我关掉{app}",
            "退出{app}程序", "把{app}结束了", "关一下{app}",
        ],
        "parameters": [{"name": "app", "type": "app"}],
        "macro_script": yaml_quit_app_slot(),
    },
    # ═══════════════════════════════════════════════════════════════════
    # 📁 文件操作 (3)
    # ═══════════════════════════════════════════════════════════════════
    {
        "name": "新建文件夹",
        "description": "在 Finder 中新建文件夹",
        "trigger_patterns": [
            "新建文件夹", "创建文件夹", "新建目录",
            "新文件夹", "建个文件夹", "创建新文件夹",
            "新目录", "新建一个文件夹",
        ],
        "macro_script": yaml_finder_keystroke("n", using="{shift down, command down}"),
    },
    {
        "name": "移到废纸篓",
        "description": "将选中文件移到废纸篓",
        "trigger_patterns": [
            "移到废纸篓", "删除选中", "丢垃圾桶", "删掉选中的",
            "扔到废纸篓", "删了", "删掉这个",
            "把它删了", "丢到垃圾桶",
        ],
        "macro_script": yaml_applescript(
            'tell application "System Events"\n'
            "  set frontApp to name of first process whose frontmost is true\n"
            '  if frontApp is "Finder" then\n'
            "    key code 51 using command down\n"
            "  end if\n"
            "end tell"
        ),
    },
    {
        "name": "压缩",
        "description": "压缩选中的文件或文件夹",
        "trigger_patterns": [
            "压缩", "压缩文件", "打包", "压缩选中",
            "打个包", "zip压缩", "做成压缩包",
            "压缩一下", "打个zip包", "压缩这些文件",
        ],
        "macro_script": yaml_applescript(
            'tell application "Finder" to set selectedItems to selection\n'
            'if selectedItems is {} then return\n'
            'set itemPath to POSIX path of (item 1 of selectedItems as alias)\n'
            'do shell script "zip -r " & quoted form of (itemPath & ".zip") & " " & quoted form of itemPath'
        ),
    },
    # ═══════════════════════════════════════════════════════════════════
    # 🔌 开关控制 (6)
    # ═══════════════════════════════════════════════════════════════════
    {
        "name": "打开 WiFi",
        "description": "打开无线网络",
        "trigger_patterns": [
            "打开WiFi", "开启WiFi", "连接WiFi", "打开无线", "启用WiFi",
            "连上WiFi", "把WiFi打开", "WiFi打开", "联网", "需要上网",
        ],
        "macro_script": yaml_applescript("do shell script \"networksetup -setairportpower en0 on\" with administrator privileges"),
    },
    {
        "name": "关闭 WiFi",
        "description": "关闭无线网络",
        "trigger_patterns": [
            "关闭WiFi", "断开WiFi", "关掉WiFi", "断开无线", "关闭无线",
            "把WiFi关了", "WiFi断开", "不联网了", "断网一下",
        ],
        "macro_script": yaml_applescript("do shell script \"networksetup -setairportpower en0 off\" with administrator privileges"),
    },
    {
        "name": "打开蓝牙",
        "description": "打开蓝牙",
        "trigger_patterns": [
            "打开蓝牙", "开启蓝牙", "连蓝牙",
            "把蓝牙打开", "蓝牙开了", "打开蓝牙功能",
            "启用蓝牙",
        ],
        "macro_script": yaml_applescript("do shell script \"blueutil -p 1\""),
    },
    {
        "name": "关闭蓝牙",
        "description": "关闭蓝牙",
        "trigger_patterns": [
            "关闭蓝牙", "关掉蓝牙", "把蓝牙关了",
            "蓝牙断开", "蓝牙关一下", "关掉蓝牙功能",
            "停用蓝牙",
        ],
        "macro_script": yaml_applescript("do shell script \"blueutil -p 0\""),
    },
    {
        "name": "打开勿扰",
        "description": "打开勿扰模式",
        "trigger_patterns": [
            "打开勿扰", "勿扰模式", "专注模式", "开启勿扰",
            "不要打扰我", "别吵我", "免打扰",
            "工作模式", "不要推送", "勿扰打开",
        ],
        "macro_script": yaml_applescript(
            'tell application "System Events" to tell expose preferences to set dontDisturb to true'
        ),
    },
    {
        "name": "关闭勿扰",
        "description": "关闭勿扰模式",
        "trigger_patterns": [
            "关闭勿扰", "关闭勿扰模式", "退出专注", "退出勿扰",
            "恢复通知", "打开通知", "勿扰关掉",
            "取消勿扰", "可以打扰了",
        ],
        "macro_script": yaml_applescript(
            'tell application "System Events" to tell expose preferences to set dontDisturb to false'
        ),
    },
    # ═══════════════════════════════════════════════════════════════════
    # 📺 播放选中文件 (1)
    # ═══════════════════════════════════════════════════════════════════
    {
        "name": "播放选中文件",
        "description": "在 Finder 中播放选中的视频/音频文件",
        "trigger_patterns": [
            "播放这个视频", "播放这个文件", "播放选中的",
            "放一下这个", "打开播放", "播放选中",
            "把这个播了", "放这个视频", "放这个",
        ],
        "macro_script": yaml_applescript(
            'tell application "Finder"\n'
            '  set sel to selection\n'
            '  if sel is not {} then\n'
            '    open (item 1 of sel)\n'
            '  end if\n'
            'end tell'
        ),
    },
    # ♿ 辅助功能 (3)
    # ═══════════════════════════════════════════════════════════════════
    {
        "name": "朗读",
        "description": "朗读选中的文本内容",
        "trigger_patterns": [
            "朗读", "朗读选中", "读出来", "读一下", "念出来",
            "帮我读", "读给我听", "把这个读了",
            "帮我读一下", "朗读这一段",
        ],
        "macro_script": yaml_applescript(
            'tell application "System Events" to keystroke "o" using {option down, command down}'
        ),
    },
    {
        "name": "放大",
        "description": "放大显示画面",
        "trigger_patterns": [
            "放大", "放大画面", "放大屏幕", "画面放大",
            "看不清楚", "大一点", "放大一些",
            "字太小了放大点", "看得不清楚", "屏幕放大",
        ],
        "macro_script": yaml_applescript(
            'tell application "System Events" to keystroke "=" using {option down, command down}'
        ),
    },
    {
        "name": "缩小",
        "description": "缩小显示画面",
        "trigger_patterns": [
            "缩小", "缩小画面", "缩小屏幕", "画面缩小",
            "小一点", "缩小一些", "屏幕缩小",
            "太大了缩小点", "缩一点",
        ],
        "macro_script": yaml_applescript(
            'tell application "System Events" to keystroke "-" using {option down, command down}'
        ),
    },
    # ═══════════════════════════════════════════════════════════════════
    # 🌐 网站直达 (1 个参数化宏)
    # ═══════════════════════════════════════════════════════════════════
    {
        "name": "打开网站",
        "description": "在默认浏览器中打开指定网站",
        "trigger_patterns": [
            "打开{site}", "上{site}看看", "去{site}",
            "打开{site}网站", "访问{site}", "帮我打开{site}",
        ],
        "parameters": [{"name": "site", "type": "str"}],
        "macro_script": yaml_website_script(),
    },
    # ═══════════════════════════════════════════════════════════════════
    # 🔍 搜索 (1 个参数化宏)
    # ═══════════════════════════════════════════════════════════════════
    {
        "name": "搜索",
        "description": "在 Google 中搜索指定内容",
        "trigger_patterns": [
            "搜索{query}", "搜一下{query}", "查一下{query}",
            "百度一下{query}", "帮我搜{query}", "查查{query}",
        ],
        "parameters": [{"name": "query", "type": "str"}],
        "macro_script": yaml_applescript(
            'set rawQuery to "{{ query }}"\n'
            "set encodedQuery to do shell script \"python3 -c 'import urllib.parse; print(urllib.parse.quote(input()))' <<< \" & quoted form of rawQuery\n"
            'open location "https://www.google.com/search?q=" & encodedQuery'
        ),
    },
    # ═══════════════════════════════════════════════════════════════════
    # 🔋 系统电源 (4)
    # ═══════════════════════════════════════════════════════════════════
    {
        "name": "关机",
        "description": "关闭电脑",
        "trigger_patterns": [
            "关机", "关闭电脑", "把电脑关了",
            "帮我关机", "电脑关机", "关机了",
        ],
        "macro_script": yaml_applescript(
            'tell application "System Events" to shut down'
        ),
    },
    {
        "name": "重启",
        "description": "重新启动电脑",
        "trigger_patterns": [
            "重启", "重新启动", "重开机",
            "重启一下", "重新开机",
        ],
        "macro_script": yaml_applescript(
            'tell application "System Events" to restart'
        ),
    },
    {
        "name": "睡眠",
        "description": "让电脑进入睡眠状态",
        "trigger_patterns": [
            "睡眠", "让电脑休息", "休眠",
            "睡一下", "休息一下",
        ],
        "macro_script": yaml_applescript(
            'tell application "System Events" to sleep'
        ),
    },
    {
        "name": "注销",
        "description": "注销当前用户",
        "trigger_patterns": [
            "注销", "退出登录", "切换用户",
            "注销当前用户",
        ],
        "macro_script": yaml_applescript(
            'tell application "System Events" to log out'
        ),
    },
    # ═══════════════════════════════════════════════════════════════════
    # 🗔 桌面导航 (3)
    # ═══════════════════════════════════════════════════════════════════
    {
        "name": "显示桌面",
        "description": "隐藏所有窗口，显示桌面",
        "trigger_patterns": [
            "显示桌面", "回到桌面", "我要看桌面",
            "把窗口都藏了", "看桌面",
        ],
        "macro_script": yaml_applescript(
            'tell application "System Events"\n'
            "  set proc to name of every process whose visible is true\n"
            "  repeat with p in proc\n"
            '    if p is not "Finder" then\n'
            "      set visible of process p to false\n"
            "    end if\n"
            "  end repeat\n"
            "end tell"
        ),
    },
    {
        "name": "打开下载文件夹",
        "description": "打开下载文件夹",
        "trigger_patterns": [
            "打开下载", "去下载文件夹", "打开下载目录",
            "去下载", "下载文件夹", "下载目录",
        ],
        "macro_script": yaml_applescript('do shell script "open ~/Downloads"'),
    },
    {
        "name": "打开最近文件",
        "description": "在 Finder 中显示最近使用的文件",
        "trigger_patterns": [
            "打开最近", "最近文件", "最近使用",
            "最近打开", "最近文档", "刚用过的文件",
        ],
        "macro_script": yaml_applescript(
            'tell application "System Events" to keystroke "f" using {shift down, command down}'
        ),
    },
    # ═══════════════════════════════════════════════════════════════════
    # 🎵 音乐播放 (3)
    # ═══════════════════════════════════════════════════════════════════
    {
        "name": "播放音乐",
        "description": "打开 Apple Music 并播放音乐",
        "trigger_patterns": [
            "来点音乐", "放首歌", "播放音乐",
            "放点音乐", "听歌", "放音乐",
            "我想听歌", "播首歌听听",
        ],
        "macro_script": yaml_applescript(
            'tell application "Music"\n'
            "  activate\n"
            "  play\n"
            "end tell"
        ),
    },
    {
        "name": "单曲循环",
        "description": "将音乐播放模式设为单曲循环",
        "trigger_patterns": [
            "单曲循环", "循环播放", "单曲重复",
            "重复播放", "就放这一首",
        ],
        "macro_script": yaml_applescript(
            'tell application "Music"\n'
            "  set song repeat to one\n"
            "end tell"
        ),
    },
    {
        "name": "随机播放",
        "description": "将音乐播放模式设为随机播放",
        "trigger_patterns": [
            "随机播放", "乱序播放", "打乱播放",
            "随机听", "随便放", "随机模式",
        ],
        "macro_script": yaml_applescript(
            'tell application "Music"\n'
            "  set shuffle enabled to true\n"
            "end tell"
        ),
    },
    # ═══════════════════════════════════════════════════════════════════
    # ⚙️ 系统设置 (1 个参数化宏)
    # ═══════════════════════════════════════════════════════════════════
    {
        "name": "打开系统设置",
        "description": "打开系统设置的指定面板",
        "trigger_patterns": [
            "打开{panel}设置", "打开{panel}",
            "设置{panel}", "进{panel}设置",
        ],
        "parameters": [{"name": "panel", "type": "str"}],
        "macro_script": yaml_settings_script(),
    },
    # ═══════════════════════════════════════════════════════════════════
    # 🗓️ 日期时间 (1)
    # ═══════════════════════════════════════════════════════════════════
    {
        "name": "报时",
        "description": "播报当前日期、时间和星期",
        "trigger_patterns": [
            "今天几号", "现在几点", "几点了", "什么时间",
            "当前时间", "当前日期", "今天星期几",
            "报时", "告诉我时间", "现在时间",
            "几点钟了", "今天多少号",
        ],
        "macro_script": yaml_applescript(
            'say do shell script "date \\"+现在是%Y年%m月%d日 %A %H点%M分\\\""'
        ),
    },
    # ═══════════════════════════════════════════════════════════════════
    # 📂 打开系统文件夹 (1 个参数化宏)
    # ═══════════════════════════════════════════════════════════════════
    {
        "name": "打开系统文件夹",
        "description": "打开指定的系统文件夹",
        "trigger_patterns": [
            "打开{dir}文件夹", "打开{dir}目录",
            "去{dir}文件夹", "打开{dir}",
        ],
        "parameters": [{"name": "dir", "type": "str"}],
        "macro_script": yaml_applescript(
            'on getFolder(name)\n'
            '  if name contains "桌面" then return POSIX path of (path to desktop folder)\n'
            '  if name contains "下载" then return POSIX path of (path to downloads folder)\n'
            '  if name contains "文稿" or name contains "文档" then return POSIX path of (path to documents folder)\n'
            '  if name contains "图片" or name contains "照片" then return POSIX path of (path to pictures folder)\n'
            '  if name contains "音乐" then return POSIX path of (path to music folder)\n'
            '  if name contains "影片" or name contains "视频" or name contains "电影" then return POSIX path of (path to movies folder)\n'
            '  if name contains "应用" or name contains "程序" then return "/Applications"\n'
            '  if name contains "工具" or name contains "实用" then return "/Applications/Utilities"\n'
            '  if name contains "下载" then return POSIX path of (path to downloads folder)\n'
            '  return POSIX path of (path to home folder)\n'
            'end getFolder\n'
            'do shell script "open \\"" & getFolder("{{ dir }}") & "\\""'
        ),
    },
    # ═══════════════════════════════════════════════════════════════════
    # 🔀 切换到应用 (1 个参数化宏)
    # ═══════════════════════════════════════════════════════════════════
    {
        "name": "切换到应用",
        "description": "切换到指定的应用（已运行则激活，未运行则打开）",
        "trigger_patterns": [
            "切换到{app}", "去{app}看看",
            "切到{app}", "转去{app}",
        ],
        "parameters": [{"name": "app", "type": "app"}],
        "macro_script": yaml_open_app_slot(),
    },
    # ═══════════════════════════════════════════════════════════════════
    # 🧊 全部最小化 (1)
    # ═══════════════════════════════════════════════════════════════════
    {
        "name": "全部最小化",
        "description": "收起所有应用的窗口",
        "trigger_patterns": [
            "全部最小化", "全都收起来", "全部收起来",
            "所有窗口都收起来", "全收了",
        ],
        "macro_script": yaml_keystroke("m", using="{option down, command down}"),
    },
    # ═══════════════════════════════════════════════════════════════════
    # 🆕 新建窗口 (1)
    # ═══════════════════════════════════════════════════════════════════
    {
        "name": "新建窗口",
        "description": "新建一个窗口或文档",
        "trigger_patterns": [
            "新建窗口", "新开一个窗口", "新建一个",
            "开个新窗口", "再来一个",
        ],
        "macro_script": yaml_keystroke("n", using="command down"),
    },
    # ═══════════════════════════════════════════════════════════════════
    # 🚫 关闭其他应用 (1)
    # ═══════════════════════════════════════════════════════════════════
    {
        "name": "关闭其他应用",
        "description": "退出除当前应用外的所有应用",
        "trigger_patterns": [
            "关闭其他应用", "把其他的关了", "只留着这个",
            "其他都退出", "只留当前", "其他都关掉",
        ],
        "macro_script": yaml_applescript(
            'tell application "System Events"\n'
            "  set frontApp to first process whose frontmost is true\n"
            "  set frontName to name of frontApp\n"
            "  set allProcs to name of every process whose background only is false\n"
            "  repeat with p in allProcs\n"
            '    if p is not frontName and p is not "Finder" then\n'
            "      try\n"
            "        do shell script \"killall \\\"\" & p & \"\\\"\"\n"
            "      end try\n"
            "    end if\n"
            "  end repeat\n"
            "end tell"
        ),
    },
    # ═══════════════════════════════════════════════════════════════════
    # 🧹 清空剪贴板 (1)
    # ═══════════════════════════════════════════════════════════════════
    {
        "name": "清空剪贴板",
        "description": "清空剪贴板内容",
        "trigger_patterns": [
            "清空剪贴板", "清除剪贴板", "清空刚复制的",
            "清除复制的", "清空粘贴板",
        ],
        "macro_script": yaml_applescript("set the clipboard to \"\""),
    },
    # ═══════════════════════════════════════════════════════════════════
    # ⏰ 倒计时 (1 个参数化宏)
    # ═══════════════════════════════════════════════════════════════════
    {
        "name": "倒计时",
        "description": "在指定分钟后用语音提醒",
        "trigger_patterns": [
            "倒计时{minutes}分钟", "计时{minutes}分钟",
            "定时{minutes}分钟", "闹钟{minutes}分钟",
        ],
        "parameters": [{"name": "minutes", "type": "str"}],
        "macro_script": yaml_applescript(
            "set mins to " + "{{ minutes }}" + "\n"
            'do shell script "(sleep $((' + "{{ minutes }}" + ' * 60)) && say \\"时间到了\\") &"\n'
            'say "好的" & (' + "{{ minutes }}" + ' as string) & "分钟"'
        ),
    },
    # ═══════════════════════════════════════════════════════════════════
    # 📄 页面导航 (4)
    # ═══════════════════════════════════════════════════════════════════
    {
        "name": "上一页",
        "description": "向前翻一页（Page Up）",
        "trigger_patterns": [
            "上一页", "往前翻", "翻到上一页", "上一屏",
            "往前翻一页", "往前一页",
        ],
        "macro_script": yaml_applescript(
            'tell application "System Events" to key code 116'
        ),
    },
    {
        "name": "下一页",
        "description": "向后翻一页（Page Down）",
        "trigger_patterns": [
            "下一页", "往后翻", "翻到下一页", "下一屏",
            "往后翻一页", "往下一屏",
        ],
        "macro_script": yaml_applescript(
            'tell application "System Events" to key code 121'
        ),
    },
    {
        "name": "回到顶部",
        "description": "滚动到页面顶部",
        "trigger_patterns": [
            "回到顶部", "滚到最上面", "去最上面",
            "回到开头", "到开头", "到顶部",
            "看最上面",
        ],
        "macro_script": yaml_applescript(
            'tell application "System Events" to key code 126 using command down'
        ),
    },
    {
        "name": "滚到底部",
        "description": "滚动到页面底部",
        "trigger_patterns": [
            "滚到底部", "去最下面", "到结尾",
            "到最后", "到底部", "去看最后",
            "到最下面",
        ],
        "macro_script": yaml_applescript(
            'tell application "System Events" to key code 125 using command down'
        ),
    },
    # ═══════════════════════════════════════════════════════════════════
    # 🚪 退出当前应用 (1)
    # ═══════════════════════════════════════════════════════════════════
    {
        "name": "退出当前应用",
        "description": "退出当前前台应用",
        "trigger_patterns": [
            "退出当前应用", "退出程序", "关闭程序",
            "退出这个", "结束当前应用", "关掉这个程序",
        ],
        "macro_script": yaml_applescript(
            'tell application "System Events"\n'
            "  set frontApp to name of first process whose frontmost is true\n"
            '  if frontApp is not "Finder" then\n'
            "    tell process frontApp to quit\n"
            "  end if\n"
            "end tell"
        ),
    },
    # ═══════════════════════════════════════════════════════════════════
    # 🖨️ 打印 (1)
    # ═══════════════════════════════════════════════════════════════════
    {
        "name": "打印",
        "description": "打印当前文档或页面",
        "trigger_patterns": [
            "打印这个", "帮我打印", "打印一下",
            "打印", "打印当前", "打印出来",
        ],
        "macro_script": yaml_keystroke("p", using="command down"),
    },
    # ═══════════════════════════════════════════════════════════════════
    # 🖼️ 上下张 (2)
    # ═══════════════════════════════════════════════════════════════════
    {
        "name": "上一张",
        "description": "浏览上一张图片/文件",
        "trigger_patterns": [
            "上一张", "看上一张", "前一张",
            "上一个", "往前一张",
        ],
        "macro_script": yaml_applescript(
            'tell application "System Events" to key code 123'
        ),
    },
    {
        "name": "下一张",
        "description": "浏览下一张图片/文件",
        "trigger_patterns": [
            "下一张", "看下一张", "后一张",
            "下一个", "往后一张", "再来一张",
        ],
        "macro_script": yaml_applescript(
            'tell application "System Events" to key code 124'
        ),
    },
]

TOTAL = len(MACROS)


# ─── 执行 ──────────────────────────────────────────────────────────────


async def seed():
    from app.infrastructure.database.resource_manager import db_resource_manager
    await db_resource_manager.initialize(create_tables=False)

    from app.infrastructure.database.sql.database import session_scope, engine
    from app.models.macro import Macro
    from app.utils.time import utcnow
    from sqlalchemy import text

    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM macros"))

    async with session_scope() as session:
        inserted = 0
        for data in MACROS:
            macro = Macro(
                name=data["name"],
                description=data["description"],
                trigger_patterns=data["trigger_patterns"],
                parameters=data.get("parameters", []),
                macro_script=data["macro_script"],
                risk_tier="ui",
                requires_confirmation=False,
                allow_self_healing=False,
                status="verified",
                is_active=True,
                namespace="preset",
                project_id=None,
                member_id=0,
                created_at=utcnow(),
            )
            session.add(macro)
            inserted += 1

        await session.commit()
        print(f"\n✅ 全局宏已全部内置: {inserted} 条")


if __name__ == "__main__":
    asyncio.run(seed())
