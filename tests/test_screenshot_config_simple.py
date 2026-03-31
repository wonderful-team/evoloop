#!/usr/bin/env python3
"""
ENABLE_PARTIAL_SCREENSHOT 配置说明
"""

print("=" * 70)
print("🔧 ENABLE_PARTIAL_SCREENSHOT 配置说明")
print("=" * 70)

print("""
📋 配置位置:
   backend/app/core/config.py

📋 配置项:
   ENABLE_PARTIAL_SCREENSHOT: bool = True

📋 作用:
   控制当 AI 调用 desktop_control(action="screenshot") 时的默认截图行为

📋 行为对比:

┌─────────────────────────┬─────────────────────┬─────────────────────┐
│ 配置值                   │ region=None 时行为   │ 效果                │
├─────────────────────────┼─────────────────────┼─────────────────────┤
│ True (默认)             │ 截取当前窗口区域     │ 节省 60-80% Token   │
│ False                   │ 截取全屏            │ 完整屏幕信息        │
└─────────────────────────┴─────────────────────┴─────────────────────┘

📋 代码逻辑 (desktop_controller.py):

   if action == "screenshot":
       if region is None:
           if settings.ENABLE_PARTIAL_SCREENSHOT:
               # 启用：自动获取窗口 bounds
               bounds = app_info.get("bounds")
               region = bounds
           else:
               # 禁用：region 保持 None，截取全屏
               pass
       
       screenshot(region=region)  # region=None 时截取全屏

📋 使用方法:

   1. 在 backend/.env 文件中添加:
      ENABLE_PARTIAL_SCREENSHOT=true   # 启用（默认）
      # 或
      ENABLE_PARTIAL_SCREENSHOT=false  # 禁用

   2. 或通过环境变量:
      export ENABLE_PARTIAL_SCREENSHOT=false

   3. 重启后端服务生效

📋 使用建议:

   ✅ 默认启用 (True):
      - 节省 60-80% OCR Token
      - 减少图片传输时间
      - 适合大多数场景

   ❌ 禁用 (False):
      - 需要完整屏幕上下文
      - 调试坐标问题
      - 某些特殊场景需要全屏

📋 注意:
   - 显式指定 region 时，此配置不影响行为
   - 例如: desktop_control(action="screenshot", region="500,300,200,100")
     始终截取指定区域
""")

print("=" * 70)
print("✅ 配置说明完成")
print("=" * 70)
