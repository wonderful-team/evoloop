import { Message } from "../ChatMessageItem";
import { v4 as uuidv4 } from 'uuid';

export const generateMockMessages = (): Message[] => {
  const now = new Date().toISOString();
  const ts = Date.now();

  const createMsg = (role: Message['role'], content: string, extra: Partial<Message> = {}): Message => ({
    id: uuidv4(),
    role,
    content,
    timestamp: new Date(ts - (messages.length * 1000)).toISOString(),
    status: "completed",
    ...extra
  });

  const messages: Message[] = [];

  // 1. Introduction
  messages.push(createMsg("human", "你好，请展示一下你的全能消息块渲染能力，包括复杂的图表、地图、代码和变更集。"));
  
  messages.push(createMsg("ai", "没问题！我将为你演示 EvoLoop Desktop 的全链路标准化消息渲染，包括 15 类核心消息块。", {
    thinking: "用户要求展示全能渲染能力。我需要构造一个包含各种复杂组件的演示序列，包括表格、图形、地图和代码变更。"
  }));

  // 2. Complex Markdown & Mermaid
  messages.push(createMsg("ai", "### 1. 复杂文本与流程图\n\n这是一个超宽表格测试：\n\n| ID | 用户名 | 角色 | 状态 | 最后登录 | 积分 | 级别 | 备注 |\n| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n| 001 | Antigravity | 管理员 | 在线 | 2024-05-10 | 9999 | SSS | 核心开发者 |\n| 002 | TestUser_01 | 贡献者 | 离线 | 2024-05-09 | 1250 | A | 活跃用户 |\n\n以及多种 Mermaid 图表：\n\n```mermaid\ngraph TD\n  A[开始] --> B{解析内容}\n  B -- 文本 --> C[Markdown渲染]\n  B -- 引用 --> D[组件渲染]\n```\n\n```mermaid\npie title 语言分布\n  \"TS\" : 50\n  \"Python\" : 30\n  \"Go\" : 20\n```", {
    status: "completed"
  }));

  // 3. Artifacts (ECharts, Map, HTML, React)
  messages.push(createMsg("ai", "这是我生成的各类可视化 Artifact，采用了标准化引用协议：", {
    references: [
      {
        id: uuidv4(),
        type: "artifact",
        target_id: "art-echarts-bar",
        target_name: "季度增长分析",
        meta_data: {
          artifact_type: "echarts",
          data: {
            title: "月度活跃用户 (MAU)",
            option: {
              tooltip: { trigger: 'axis' },
              xAxis: { type: 'category', data: ['1月', '2月', '3月', '4月', '5月'] },
              yAxis: { type: 'value' },
              series: [{ 
                data: [820, 932, 901, 934, 1290], 
                type: 'line', 
                smooth: true,
                areaStyle: {}
              }]
            }
          }
        }
      },
      {
        id: uuidv4(),
        type: "artifact",
        target_id: "art-map-1",
        target_name: "办公区域分布",
        meta_data: {
          artifact_type: "map",
          data: {
            address: "上海市浦东新区张江路",
            zoom: 14,
            title: "研发中心",
            markers: [
              { position: { lng: 121.58, lat: 31.20 }, title: "总部" },
              { position: { lng: 121.60, lat: 31.22 }, title: "分部" }
            ]
          }
        }
      },
      {
        id: uuidv4(),
        type: "artifact",
        target_id: "art-html-1",
        target_name: "系统健康状态",
        meta_data: {
          artifact_type: "html",
          data: {
            html: `
              <div style="padding: 15px; border-radius: 10px; background: #0f172a; color: white;">
                <div style="display: flex; justify-content: space-between; margin-bottom: 10px;">
                  <span>CPU 负载</span>
                  <span style="color: #10b981;">正常</span>
                </div>
                <div style="height: 8px; background: #1e293b; border-radius: 4px;">
                  <div style="width: 45%; height: 100%; background: #3b82f6; border-radius: 4px;"></div>
                </div>
                <p style="font-size: 10px; color: #94a3b8; margin-top: 10px;">上次检查: 2分钟前</p>
              </div>
            `,
            height: 120
          }
        }
      },
      {
        id: uuidv4(),
        type: "artifact",
        target_id: "art-react-1",
        target_name: "配置编辑器",
        meta_data: {
          artifact_type: "react",
          data: {
            componentName: "ConfigEditor",
            code: "import React from 'react';\n\nexport const ConfigEditor = () => {\n  return (\n    <div className=\"p-4 bg-zinc-900 text-white rounded-lg\">\n      <h2 className=\"text-lg font-bold\">Settings</h2>\n      <div className=\"mt-2 space-y-2\">\n        <label className=\"block text-xs text-zinc-400\">Theme</label>\n        <select className=\"w-full bg-zinc-800 border-zinc-700 rounded p-1\"> \n          <option>Dark</option>\n          <option>Light</option>\n        </select>\n      </div>\n    </div>\n  );\n};",
            dependencies: ["react", "lucide-react"]
          }
        }
      },
      {
        id: uuidv4(),
        type: "artifact",
        target_id: "art-test-1",
        target_name: "单元测试执行报告",
        meta_data: {
          artifact_type: "test_report",
          data: {
            status: "FAIL",
            summary: "执行了 45 个测试用例，其中 42 个通过，3 个失败。主要集中在数据层异步超时问题。",
            root_cause: "数据库连接池未能及时释放，导致并发请求超出系统设定上限抛出 TimeoutError。",
            fix_suggestion: "建议在 db.session.close() 外部使用 context manager (async with) 确保事务执行完毕后立即归还连接。"
          }
        }
      }
    ]
  }));

  // 4. Resources (Mixed types)
  messages.push(createMsg("ai", "同时，我支持多种资源的统一引用和内联展示：", {
    references: [
      { id: uuidv4(), type: "file", target_id: "doc-1", target_name: "架构设计图.pdf" },
      { id: uuidv4(), type: "image", target_id: "https://picsum.photos/400/300?random=1", target_name: "UI Mockup.png" },
      { id: uuidv4(), type: "audio", target_id: "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3", target_name: "客户反馈录音.wav" },
      { id: uuidv4(), type: "message", target_id: "msg-999", target_name: "第三轮对话提到的重构建议" },
      { id: uuidv4(), type: "skill", target_id: "web_search", target_name: "联网搜索技能" }
    ]
  }));

  // 5. Tool Chain & Changesets
  messages.push(createMsg("tool", "Successfully updated agent core", {
    tool_name: "replace_file_content",
    input: { path: "src/core.py", target: "old_logic", replacement: "new_logic" },
    tool_meta: { display_name: "Update Core Logic" }
  }));

  messages.push(createMsg("ai", "我已经完成了代码重构。你可以在下方查看具体的变更详情：", {
    changeset_count: 5,
    changeset_files: [
      { path: "src/main.ts", operation: "EDIT" },
      { path: "src/components/Chat.tsx", operation: "EDIT" },
      { path: "src/utils/debug.ts", operation: "ADD" },
      { path: "legacy/old_file.ts", operation: "DELETE" },
      { path: "docs/readme.md", operation: "EDIT" }
    ],
    references: [
      {
        id: uuidv4(),
        type: "changeset",
        target_id: "run-456",
        target_name: "重构变更集",
        meta_data: {
          count: 5,
          files: [
            { path: "src/main.ts", operation: "EDIT" },
            { path: "src/components/Chat.tsx", operation: "EDIT" },
            { path: "src/utils/debug.ts", operation: "ADD" },
            { path: "legacy/old_file.ts", operation: "DELETE" },
            { path: "docs/readme.md", operation: "EDIT" }
          ]
        }
      }
    ]
  }));

  return messages;
};

export const simulateStreaming = async (onUpdate: (content: string) => void) => {
  const fullText = "### 实时流式输出模拟\n\n正在根据你的要求生成分析报告...\n\n- **核心优势**: 极致的响应速度\n- **渲染能力**: 支持所有的标准组件\n\n```python\ndef analyze_system():\n    print(\"Analyzing metrics...\")\n    return {\"status\": \"ok\", \"latency\": \"12ms\"}\n```\n\n希望这次演示能让你满意！";
  let current = "";
  for (const char of fullText) {
    current += char;
    onUpdate(current);
    await new Promise(r => setTimeout(r, 25));
  }
};
