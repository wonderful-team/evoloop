import { Message } from "../ChatMessageItem";

export const generateMockMessages = (): Message[] => {
  const now = Date.now();

  const mockMessages: Message[] = [
    {
      id: 'mock-wide-table',
      role: 'ai',
      content: '### 1. 超宽表格测试 (验证横向滚动)\n\n| ID | 用户名 | 角色 | 状态 | 最后登录 | 积分 | 级别 | 备注 |\n| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n| 001 | Antigravity | 管理员 | 在线 | 2024-05-10 | 9999 | SSS | 核心开发者 |\n| 002 | TestUser_01 | 贡献者 | 离线 | 2024-05-09 | 1250 | A | 活跃用户 |\n| 003 | Mock_Bot_V2 | 机器人 | 忙碌 | 2024-05-10 | 500 | B | 自动化脚本 |',
      status: 'completed',
      timestamp: new Date(now - 360000).toISOString(),
    },
    {
      id: 'mock-mermaid-pie',
      role: 'ai',
      content: '### 2. Mermaid 饼图测试\n\n```mermaid\npie title 编程语言使用占比\n    "TypeScript" : 45\n    "Python" : 30\n    "Go" : 15\n    "Others" : 10\n```',
      status: 'completed',
      timestamp: new Date(now - 355000).toISOString(),
    },
    {
      id: 'mock-mermaid-seq',
      role: 'ai',
      content: '### 3. Mermaid 序列图测试\n\n```mermaid\nsequenceDiagram\n    participant U as 用户\n    participant A as AI 助手\n    participant G as 网关\n    U->>A: 发送消息\n    A->>G: 请求工具调用\n    G-->>A: 返回结果\n    A-->>U: 回复内容\n```',
      status: 'completed',
      timestamp: new Date(now - 354000).toISOString(),
    },
    {
      id: 'mock-table',
      role: 'ai',
      content: '### 4. 标准 Markdown 表格\n\n| 功能模块 | 优先级 | 状态 | 进度 |\n| :--- | :---: | :---: | ---: |\n| 语音输入 | 高 | 已完成 | 100% |\n| 样式优化 | 中 | 进行中 | 75% |',
      status: 'completed',
      timestamp: new Date(now - 350000).toISOString(),
    },
    {
      id: 'mock-echarts-pie',
      role: 'ai',
      content: '### 5. 南丁格尔玫瑰图 (饼图)\n\n下方是标准化交互式 ECharts 交付物展示：',
      status: 'completed',
      timestamp: new Date(now - 345000).toISOString(),
      references: [
        {
          id: 'art-echarts-pie-ref',
          type: 'artifact',
          target_id: 'echarts-rose',
          target_name: '资源分配占比',
          meta_data: {
            artifact_type: 'echarts',
            data: {
              title: '资源分配占比',
              option: {
                tooltip: { trigger: "item" },
                series: [
                  {
                    name: "访问来源",
                    type: "pie",
                    radius: [20, 100],
                    roseType: "area",
                    itemStyle: { borderRadius: 5 },
                    data: [
                      { value: 40, name: "核心计算" },
                      { value: 38, name: "存储服务" },
                      { value: 32, name: "网络带宽" },
                      { value: 30, name: "安全防御" },
                      { value: 28, name: "备份系统" }
                    ]
                  }
                ]
              }
            }
          }
        }
      ]
    },
    {
      id: 'mock-echarts-bar',
      role: 'ai',
      content: '### 6. 堆叠柱状图演示\n\n下方是标准化交互式堆叠柱状图卡片：',
      status: 'completed',
      timestamp: new Date(now - 342000).toISOString(),
      references: [
        {
          id: 'art-echarts-bar-ref',
          type: 'artifact',
          target_id: 'echarts-bar',
          target_name: '月度负载对比',
          meta_data: {
            artifact_type: 'echarts',
            data: {
              title: '月度负载对比',
              option: {
                legend: { data: ["生产环境", "测试环境"], top: 30 },
                xAxis: { data: ["1月", "2月", "3月", "4月"] },
                yAxis: {},
                series: [
                  { name: "生产环境", type: "bar", stack: "total", data: [320, 332, 301, 334] },
                  { name: "测试环境", type: "bar", stack: "total", data: [220, 182, 191, 234] }
                ]
              }
            }
          }
        }
      ]
    },
    {
      id: 'mock-map',
      role: 'ai',
      content: '### 7. 地图组件测试\n\n下方是标准化交互式地图卡片：',
      status: 'completed',
      timestamp: new Date(now - 330000).toISOString(),
      references: [
        {
          id: 'art-map-ref',
          type: 'artifact',
          target_id: 'map-hangzhou',
          target_name: '杭州核心区域',
          meta_data: {
            artifact_type: 'map',
            data: {
              title: "杭州核心区域",
              address: "浙江省杭州市西湖文化广场",
              zoom: 14,
              markers: [
                { position: { lng: 120.15, lat: 30.28 }, title: "西湖文化广场" },
                { position: { lng: 120.12, lat: 30.27 }, title: "黄龙体育中心" }
              ]
            }
          }
        }
      ]
    },
    {
      id: 'mock-artifact',
      role: 'ai',
      content: '### 8. Artifact 智能快照\n\n我为你生成了一个简单的 HTML/React 计数器组件预览：',
      status: 'completed',
      timestamp: new Date(now - 320000).toISOString(),
      references: [
        {
          id: 'art-html-ref',
          type: 'artifact',
          target_id: 'html-counter',
          target_name: '计数器演示界面',
          meta_data: {
            artifact_type: 'html',
            data: {
              html: `<div style="padding: 20px; background: #f5f5f5; border-radius: 10px; text-align: center; color: #333;"><h2 style="color: #6200ee; margin-top:0;">计数器演示</h2><p>这是一个实时渲染的 HTML Artifact</p><button style="padding: 10px 20px; background: #6200ee; color: white; border: none; border-radius: 5px; font-weight: bold; cursor: pointer;">点击增加</button></div>`,
              height: 160
            }
          }
        }
      ]
    },
    {
      id: 'mock-code',
      role: 'ai',
      content: '### 9. 代码高亮测试\n\n```typescript\nfunction greet(name: string): string {\n  // 这是一个简单的问候函数\n  return `Hello, ${name}! Welcome to EvoLoop.`;\n}\n\nconsole.log(greet("Developer"));\n```',
      status: 'completed',
      timestamp: new Date(now - 315000).toISOString(),
    },

    // 1. 基础对话
    {
      id: 'm1',
      role: 'human',
      content: '你好，这是一个全面测试。我需要你展示你所有的能力。',
      timestamp: new Date(now - 300000).toISOString(),
      status: 'completed',
    },
    {
      id: 'm2',
      role: 'ai',
      content: '明白了。我将向你展示我的思考过程、工具调用能力、文件修改能力以及交互式确认功能。',
      thinking: '用户要求展示所有能力。我需要构造一个涉及搜索、读取、修改和确认的任务流。',
      timestamp: new Date(now - 290000).toISOString(),
      status: 'completed',
    },

    // 2. 工具链测试 (Shell + Python)
    {
      id: 'm3',
      role: 'tool',
      content: 'ls -R src/',
      tool_name: 'shell_exec',
      tool_meta: { display_name: '列出源码目录 (shell_exec)' },
      timestamp: new Date(now - 280000).toISOString(),
      status: 'completed',
    },
    {
      id: 'm4',
      role: 'tool',
      content: 'pip install pandas',
      tool_name: 'shell_exec',
      tool_meta: { display_name: '安装依赖 (pip)' },
      timestamp: new Date(now - 270000).toISOString(),
      status: 'completed',
    },
    {
      id: 'm5',
      role: 'ai',
      content: '我正在分析代码结构，并准备进行一些重构。',
      thinking: '目录结构已清晰。src 目录下有多个组件。我准备修改 ChatScreen.tsx 以优化渲染。',
      timestamp: new Date(now - 260000).toISOString(),
      status: 'completed',
    },

    // 3. 文件修改与 changeset 徽章
    {
      id: 'm6',
      role: 'tool',
      content: 'sed -i "s/old/new/g" ChatScreen.tsx',
      tool_name: 'shell_exec',
      tool_meta: { display_name: '修改 ChatScreen.tsx' },
      timestamp: new Date(now - 250000).toISOString(),
      status: 'completed',
    },
    {
      id: 'm7',
      role: 'ai',
      content: '我已经对关键组件进行了优化，并修复了几个潜在的 Bug。',
      thinking: '优化已完成。通过 changeset 标记告诉用户改动了哪些文件。',
      timestamp: new Date(now - 240000).toISOString(),
      status: 'completed',
      changeset_count: 5,
      changeset_files: [
        { path: 'src/screens/ChatScreen.tsx', operation: 'modified' },
        { path: 'src/components/voice/MessageList.tsx', operation: 'modified' },
        { path: 'src/types/conversation.ts', operation: 'added' },
        { path: 'src/utils/debugManager.ts', operation: 'modified' },
        { path: 'src/services/api.ts', operation: 'deleted' },
      ],
      has_file_operations: true,
      references: [
        {
          id: 'cs-ref-1',
          type: 'changeset',
          target_id: 'cs-5',
          target_name: '组件重构补丁快照 (5个文件改动)'
        }
      ]
    },

    // 4. 引用与附件测试
    {
      id: 'm8',
      role: 'human',
      content: '你能看看这个图片里的报错吗？',
      timestamp: new Date(now - 230000).toISOString(),
      status: 'completed',
      attachments: [
        {
          id: 'att-1',
          type: 'image',
          name: 'error_screenshot.png',
          url: 'https://placehold.co/600x400/2563eb/ffffff/png?text=Error+Screenshot',
        }
      ]
    },
    {
      id: 'm9',
      role: 'ai',
      content: '从截图中看，这是一个类型不匹配错误。我建议检查 `types/conversation.ts`。',
      thinking: '分析图像内容。发现 Property t doesn\'t exist 的报错。这是典型的 context 丢失。',
      timestamp: new Date(now - 220000).toISOString(),
      status: 'completed',
    },

    // 5. 各种中间状态测试 (Running, Failed)
    {
      id: 'm10',
      role: 'human',
      content: '帮我运行一个耗时很久的脚本。',
      timestamp: new Date(now - 210000).toISOString(),
      status: 'completed',
    },
    {
      id: 'm11',
      role: 'tool',
      content: 'sleep 60 && echo "done"',
      tool_name: 'shell_exec',
      tool_meta: { display_name: '长时间运行任务' },
      timestamp: new Date(now - 200000).toISOString(),
      status: 'running',
    },
    {
      id: 'm12',
      role: 'human',
      content: '这条消息发送失败了（模拟网络异常）。',
      timestamp: new Date(now - 190000).toISOString(),
      status: 'failed',
    },

    // 6. 复杂思考过程
    {
      id: 'm13',
      role: 'ai',
      content: '这是我经过深思熟虑后的方案。',
      thinking: '### 分析步骤\n1. **步骤一**: 检查依赖\n2. **步骤二**: 运行单元测试\n3. **结论**: 方案可行，准备部署。',
      timestamp: new Date(now - 180000).toISOString(),
      status: 'completed',
    },

    // 7. HITL 历史记录
    {
      id: 'm14',
      role: 'ai',
      content: '你需要确认执行 `rm -rf node_modules` 吗？',
      timestamp: new Date(now - 170000).toISOString(),
      status: 'completed',
    },
    {
      id: 'm15',
      role: 'human',
      content: '是的，执行强制清理。',
      timestamp: new Date(now - 160000).toISOString(),
      status: 'completed',
    },

    // 8. 更多的工具调用
    {
      id: 'm16',
      role: 'tool',
      content: 'git status',
      tool_name: 'git',
      tool_meta: { display_name: '检查 Git 状态' },
      timestamp: new Date(now - 150000).toISOString(),
      status: 'completed',
    },
    {
      id: 'm17',
      role: 'tool',
      content: 'git commit -m "refactor: sync cross-platform architecture"',
      tool_name: 'git',
      tool_meta: { display_name: '提交重构代码' },
      timestamp: new Date(now - 140000).toISOString(),
      status: 'completed',
    },

    // 9. 结尾：当前正在进行的状态
    {
      id: 'm18',
      role: 'human',
      content: '最后，请模拟一个流式响应并以 HITL 结尾。',
      timestamp: new Date(now - 130000).toISOString(),
      status: 'completed',
    },
    {
      id: 'm19',
      role: 'ai',
      content: '正在生成最后的测试报告与多模态快照...',
      thinking: '准备结束测试。最后需要抛出一个 HITL 请求来验证全局卡片。',
      timestamp: new Date(now - 120000).toISOString(),
      status: 'streaming',
    },

    // 10. 引用与多文件上传测试 (用户复杂多模态输入)
    {
      id: 'mock-human-complex',
      role: 'human',
      content: '我已经参考了你之前提到的那个架构图，并上传了最新的接口文档和实现代码，请帮我审核一下。',
      timestamp: new Date(now - 100000).toISOString(),
      status: 'completed',
      references: [
        {
          type: 'message',
          id: 'mock-mermaid-seq',
          target_id: 'mock-mermaid-seq',
          target_name: '引用消息: Mermaid 序列图测试',
          detail: 'sequenceDiagram\n    participant U as 用户\n    participant A as AI 助手...'
        },
        {
          type: 'skill',
          id: 'skill-1',
          target_id: 'mcp-code-audit',
          target_name: '已挂载技能: 深度代码审查'
        }
      ],
      attachments: [
        {
          id: 'att-file-1',
          type: 'file',
          name: 'API_V2_Draft.pdf',
          url: 'https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf',
        },
        {
          id: 'att-file-2',
          type: 'file',
          name: 'auth_handler.go',
          url: 'https://raw.githubusercontent.com/golang/go/master/README.md',
        }
      ]
    },

    // 11. AI 回复包含文件导出
    {
      id: 'mock-ai-with-file',
      role: 'ai',
      content: '代码逻辑已经审查完毕。我为你生成了一份优化建议报告，以及一个修复后的代码补丁文件，你可以直接下载或在新标签页查看。',
      thinking: '用户上传了 PDF 和 Go 代码。我分析了 auth_handler.go 中的并发问题，并准备了完整的修复报告。',
      timestamp: new Date(now - 90000).toISOString(),
      status: 'completed',
      attachments: [
        {
          id: 'ai-export-1',
          type: 'file',
          name: 'Optimization_Report.md',
          url: 'https://raw.githubusercontent.com/markdown-it/markdown-it/master/README.md',
        },
        {
          id: 'ai-export-2',
          type: 'file',
          name: 'fix_patch.zip',
          url: 'https://github.com/favicon.ico',
        }
      ]
    },

    // 12. 混合媒体测试
    {
      id: 'mock-human-media',
      role: 'human',
      content: '这是现场的报错截图，还有我引用的那个模块配置。',
      timestamp: new Date(now - 80000).toISOString(),
      status: 'completed',
      attachments: [
        {
          id: 'img-1',
          type: 'image',
          name: 'crash_log.png',
          url: 'https://picsum.photos/800/600?random=88',
        },
        {
          id: 'att-config',
          type: 'file',
          name: 'config.json',
          url: 'https://raw.githubusercontent.com/prettier/prettier/main/package.json',
        }
      ],
      references: [
        {
          type: 'file',
          id: 'f-ref-99',
          target_id: 'MessageContent.tsx',
          target_name: '参考文件: MessageContent.tsx (核心渲染组件)',
          detail: '核心渲染逻辑组件'
        }
      ]
    }
  ];

  return mockMessages;
};

export const simulateStreaming = async (onUpdate: (content: string) => void) => {
  const fullText = "### 实时多模态流式响应模拟\n\n正在根据你的多模态上下文生成智能诊断...\n\n- **解析速度**: 极致的响应速度 (毫秒级分发)\n- **协议对齐**: 完美分离 References 引用容器与 Attachments 附件卡片\n\n```typescript\nexport function verifyParity() {\n    console.log(\"All 5 categories & 21 forms successfully verified!\");\n    return { status: \"PASSED\", crossPlatform: true };\n}\n```\n\n希望这次全景重构与对齐演示能给你带来极致的体验！";
  let current = "";
  for (const char of fullText) {
    current += char;
    onUpdate(current);
    await new Promise(r => setTimeout(r, 20));
  }
};
