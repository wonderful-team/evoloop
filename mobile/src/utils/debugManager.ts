import { useConversationStore } from '@/stores/conversationStore';
import { useDeviceStore } from '@/stores/deviceStore';
import { useAuthStore } from '@/stores/authStore';
import { useHITLStore } from '@/stores/hitlStore';
import { generateUUID } from '@/utils/uuid';
import { ChatMessage, Conversation } from '@/types/conversation';

/**
 * 调试模式数据管理器
 * 旨在通过注入极大量的、类型极其多样的模拟数据来全面覆盖 UI 和逻辑测试
 */
export const debugManager = {
  /**
   * 注入海量模拟数据：包括各种角色、文件操作、思考过程、工具链、附件、状态等
   */
  injectInitialData: () => {
    const { setState: setConversationState } = useConversationStore;
    const { setState: setDeviceState } = useDeviceStore;
    const { setState: setAuthState } = useAuthStore;

    setAuthState({ isLoggedIn: true });
    
    // 不再自动注入模拟设备，避免干扰真实的“链路二”语音对话测试
    /*
    const mockDevice = {
      deviceKey: 'debug-device-full-test',
      name: 'Test Mac Pro (Ultra)',
      status: 'online' as const,
      lastSeen: new Date().toISOString(),
    };
    setDeviceState({ currentDevice: mockDevice });
    */

    const mockConversations: Conversation[] = [

      {
        id: 'full-test-1',
        title: '全面功能压力测试会话',
        status: 'active',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        message_count: 25,
      },
      {
        id: 'conv-empty',
        title: '空会话测试',
        status: 'active',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      }
    ];

    setConversationState({
      conversations: mockConversations,
      currentConversationId: 'full-test-1',
      hasMoreConversations: false,
    });

    const now = Date.now();
    const mockMessages: ChatMessage[] = [
      {
        id: 'mock-wide-table',
        role: 'ai',
        content: '### 1. 超宽表格测试 (验证横向滚动)\n\n| ID | 用户名 | 角色 | 状态 | 最后登录 | 积分 | 级别 | 备注 |\n| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n| 001 | Antigravity | 管理员 | 在线 | 2024-05-10 | 9999 | SSS | 核心开发者 |\n| 002 | TestUser_01 | 贡献者 | 离线 | 2024-05-09 | 1250 | A | 活跃用户 |\n| 003 | Mock_Bot_V2 | 机器人 | 忙碌 | 2024-05-10 | 500 | B | 自动化脚本 |',
        status: 'completed',
        timestamp: now - 360000,
      },
      {
        id: 'mock-mermaid-pie',
        role: 'ai',
        content: '### 2. Mermaid 饼图测试\n\n```mermaid\npie title 编程语言使用占比\n    "TypeScript" : 45\n    "Python" : 30\n    "Go" : 15\n    "Others" : 10\n```',
        status: 'completed',
        timestamp: now - 355000,
      },
      {
        id: 'mock-mermaid-seq',
        role: 'ai',
        content: '### 3. Mermaid 序列图测试\n\n```mermaid\nsequenceDiagram\n    participant U as 用户\n    participant A as AI 助手\n    participant G as 网关\n    U->>A: 发送消息\n    A->>G: 请求工具调用\n    G-->>A: 返回结果\n    A-->>U: 回复内容\n```',
        status: 'completed',
        timestamp: now - 354000,
      },
      {
        id: 'mock-table',
        role: 'ai',
        content: '### 4. 标准 Markdown 表格\n\n| 功能模块 | 优先级 | 状态 | 进度 |\n| :--- | :---: | :---: | ---: |\n| 语音输入 | 高 | 已完成 | 100% |\n| 样式优化 | 中 | 进行中 | 75% |',
        status: 'completed',
        timestamp: now - 350000,
      },
      {
        id: 'mock-echarts-pie',
        role: 'ai',
        content: '### 5. 南丁格尔玫瑰图 (饼图)\n\n```echarts\n{\n  "title": { "text": "资源分配占比", "left": "center" },\n  "tooltip": { "trigger": "item" },\n  "series": [\n    {\n      "name": "访问来源",\n      "type": "pie",\n      "radius": [20, 100],\n      "roseType": "area",\n      "itemStyle": { "borderRadius": 5 },\n      "data": [\n        { "value": 40, "name": "核心计算" },\n        { "value": 38, "name": "存储服务" },\n        { "value": 32, "name": "网络带宽" },\n        { "value": 30, "name": "安全防御" },\n        { "value": 28, "name": "备份系统" }\n      ]\n    }\n  ]\n}\n```',
        status: 'completed',
        timestamp: now - 345000,
      },
      {
        id: 'mock-echarts-bar',
        role: 'ai',
        content: '### 6. 堆叠柱状图\n\n```echarts\n{\n  "title": { "text": "月度负载对比" },\n  "legend": { "data": ["生产环境", "测试环境"], "top": 30 },\n  "xAxis": { "data": ["1月", "2月", "3月", "4月"] },\n  "yAxis": {},\n  "series": [\n    { "name": "生产环境", "type": "bar", "stack": "total", "data": [320, 332, 301, 334] },\n    { "name": "测试环境", "type": "bar", "stack": "total", "data": [220, 182, 191, 234] }\n  ]\n}\n```',
        status: 'completed',
        timestamp: now - 342000,
      },
      {
        id: 'mock-map',
        role: 'ai',
        content: '### 7. 地图组件测试\n\n```map\n{\n  "title": "杭州核心区域",\n  "center": { "lng": 120.15, "lat": 30.28 },\n  "zoom": 14,\n  "markers": [\n    { "position": { "lng": 120.15, "lat": 30.28 }, "title": "西湖文化广场" },\n    { "position": { "lng": 120.12, "lat": 30.27 }, "title": "黄龙体育中心" }\n  ]\n}\n```',
        status: 'completed',
        timestamp: now - 330000,
      },

      {
        id: 'mock-artifact',
        role: 'ai',
        content: '### 7. Artifact 智能快照\n\n我为你生成了一个简单的 React 计数器组件预览：\n\n```artifact\n<div style="padding: 20px; background: #f5f5f5; border-radius: 10px; text-align: center;">\n  <h2 style="color: #6200ee;">计数器演示</h2>\n  <p>这是一个实时渲染的 HTML Artifact</p>\n  <button style="padding: 10px 20px; background: #6200ee; color: white; border: none; border-radius: 5px;">点击增加</button>\n</div>\n```',
        status: 'completed',
        timestamp: now - 320000,
      },
      {
        id: 'mock-code',

        role: 'ai',
        content: '### 3. 代码高亮测试\n\n```typescript\nfunction greet(name: string): string {\n  // 这是一个简单的问候函数\n  return `Hello, ${name}! Welcome to EvoLoop.`;\n}\n\nconsole.log(greet("Developer"));\n```',
        status: 'completed',
        timestamp: now - 330000,
      },

      // 1. 基础对话
      {
        id: 'm1',
        role: 'human',
        content: '你好，这是一个全面测试。我需要你展示你所有的能力。',
        timestamp: now - 300000,
        status: 'completed',
        isComplete: true,
      },
      {
        id: 'm2',
        role: 'ai',
        content: '明白了。我将向你展示我的思考过程、工具调用能力、文件修改能力以及交互式确认功能。',
        thinking: '用户要求展示所有能力。我需要构造一个涉及搜索、读取、修改和确认的任务流。',
        timestamp: now - 290000,
        status: 'completed',
        isComplete: true,
      },

      // 2. 工具链测试 (Shell + Python)
      {
        id: 'm3',
        role: 'tool',
        content: 'ls -R src/',
        tool_name: 'shell_exec',
        tool_meta: { display_name: '列出源码目录 (shell_exec)' },
        timestamp: now - 280000,
        status: 'completed',
      },
      {
        id: 'm4',
        role: 'tool',
        content: 'pip install pandas',
        tool_name: 'shell_exec',
        tool_meta: { display_name: '安装依赖 (pip)' },
        timestamp: now - 270000,
        status: 'completed',
      },
      {
        id: 'm5',
        role: 'ai',
        content: '我正在分析代码结构，并准备进行一些重构。',
        thinking: '目录结构已清晰。src 目录下有多个组件。我准备修改 ChatScreen.tsx 以优化渲染。',
        timestamp: now - 260000,
        status: 'completed',
        isComplete: true,
      },

      // 3. 文件修改与 changeset 徽章
      {
        id: 'm6',
        role: 'tool',
        content: 'sed -i "s/old/new/g" ChatScreen.tsx',
        tool_name: 'shell_exec',
        tool_meta: { display_name: '修改 ChatScreen.tsx' },
        timestamp: now - 250000,
        status: 'completed',
      },
      {
        id: 'm7',
        role: 'ai',
        content: '我已经对关键组件进行了优化，并修复了几个潜在的 Bug。',
        thinking: '优化已完成。通过 changeset 标记告诉用户改动了哪些文件。',
        timestamp: now - 240000,
        status: 'completed',
        isComplete: true,
        changeset_count: 5,
        changeset_files: [
          { path: 'src/screens/ChatScreen.tsx', operation: 'modified' },
          { path: 'src/components/voice/MessageList.tsx', operation: 'modified' },
          { path: 'src/types/conversation.ts', operation: 'added' },
          { path: 'src/utils/debugManager.ts', operation: 'modified' },
          { path: 'src/services/api.ts', operation: 'deleted' },
        ],
        has_file_operations: true,
      },

      // 4. 引用与附件测试
      {
        id: 'm8',
        role: 'human',
        content: '你能看看这个图片里的报错吗？',
        timestamp: now - 230000,
        status: 'completed',
        isComplete: true,
        attachments: [
          {
            id: 'att-1',
            type: 'image',
            name: 'error_screenshot.png',
            url: 'https://placehold.co/600x400/png?text=Error+Screenshot',
          }
        ]
      },
      {
        id: 'm9',
        role: 'ai',
        content: '从截图中看，这是一个类型不匹配错误。我建议检查 `types/conversation.ts`。',
        thinking: '分析图像内容。发现 Property t doesn\'t exist 的报错。这是典型的 context 丢失。',
        timestamp: now - 220000,
        status: 'completed',
        isComplete: true,
      },

      // 5. 各种中间状态测试 (Running, Failed)
      {
        id: 'm10',
        role: 'human',
        content: '帮我运行一个耗时很久的脚本。',
        timestamp: now - 210000,
        status: 'completed',
        isComplete: true,
      },
      {
        id: 'm11',
        role: 'tool',
        content: 'sleep 60 && echo "done"',
        tool_name: 'shell_exec',
        tool_meta: { display_name: '长时间任务' },
        timestamp: now - 200000,
        status: 'running', // 正在运行状态
      },
      {
        id: 'm12',
        role: 'human',
        content: '这条消息发送失败了（模拟）。',
        timestamp: now - 190000,
        status: 'failed', // 发送失败状态
        isComplete: true,
      },

      // 6. 复杂思考过程 (Markdown inside thinking)
      {
        id: 'm13',
        role: 'ai',
        content: '这是我经过深思熟虑后的方案。',
        thinking: '### 分析步骤\n1. **步骤一**: 检查依赖\n2. **步骤二**: 运行测试\n3. **结论**: 方案可行。',
        timestamp: now - 180000,
        status: 'completed',
        isComplete: true,
      },

      // 7. HITL 历史记录 (已经完成的确认)
      {
        id: 'm14',
        role: 'ai',
        content: '你需要确认执行 `rm -rf node_modules` 吗？',
        timestamp: now - 170000,
        status: 'completed',
        isComplete: true,
      },
      {
        id: 'm15',
        role: 'human',
        content: '是的，执行。',
        timestamp: now - 160000,
        status: 'completed',
        isComplete: true,
      },

      // 8. 更多的工具调用（对齐桌面端紧凑样式）
      {
        id: 'm16',
        role: 'tool',
        content: 'git status',
        tool_name: 'git',
        tool_meta: { display_name: '检查 Git 状态' },
        timestamp: now - 150000,
        status: 'completed',
      },
      {
        id: 'm17',
        role: 'tool',
        content: 'git commit -m "refactor"',
        tool_name: 'git',
        tool_meta: { display_name: '提交代码' },
        timestamp: now - 140000,
        status: 'completed',
      },

      // 9. 结尾：当前正在进行的状态
      {
        id: 'm18',
        role: 'human',
        content: '最后，请模拟一个流式响应并以 HITL 结尾。',
        timestamp: now - 130000,
        status: 'completed',
        isComplete: true,
      },
      {
        id: 'm19',
        role: 'ai',
        content: '正在生成最后的测试报告...',
        thinking: '准备结束测试。最后需要抛出一个 HITL 请求来验证全局卡片。',
        timestamp: now - 120000,
        status: 'streaming',
        isComplete: false,
      },

      // 10. 引用与多文件上传测试 (用户)
      {
        id: 'mock-human-complex',
        role: 'human',
        content: '我已经参考了你之前提到的那个架构图，并上传了最新的接口文档和实现代码，请帮我审核一下。',
        timestamp: now - 100000,
        status: 'completed',
        isComplete: true,
        // 引用之前的一条消息
        references: [
          {
            type: 'message',
            id: 'mock-mermaid-seq',
            name: 'Mermaid 序列图测试',
            detail: 'sequenceDiagram\n    participant U as 用户\n    participant A as AI 助手...'
          }
        ],
        // 上传多个文件
        attachments: [
          {
            id: 'att-file-1',
            type: 'file',
            name: 'API_V2_Draft.pdf',
            url: 'https://example.com/files/api_v2.pdf',
          },
          {
            id: 'att-file-2',
            type: 'file',
            name: 'auth_handler.go',
            url: 'https://example.com/files/auth_handler.go',
          }
        ]
      },

      // 11. AI 回复包含文件导出
      {
        id: 'mock-ai-with-file',
        role: 'ai',
        content: '代码逻辑已经审查完毕。我为你生成了一份优化建议报告，以及一个修复后的代码补丁文件，你可以下载查看。',
        thinking: '用户上传了 PDF 和 Go 代码。我分析了 auth_handler.go 中的 race condition，并准备了修复方案。',
        timestamp: now - 90000,
        status: 'completed',
        isComplete: true,
        attachments: [
          {
            id: 'ai-export-1',
            type: 'file',
            name: 'Optimization_Report.md',
            url: 'https://example.com/export/report.md',
          },
          {
            id: 'ai-export-2',
            type: 'file',
            name: 'fix_patch.zip',
            url: 'https://example.com/export/patch.zip',
          }
        ]
      },

      // 12. 混合媒体测试
      {
        id: 'mock-human-media',
        role: 'human',
        content: '这是现场的报错截图，还有我引用的那个模块配置。',
        timestamp: now - 80000,
        status: 'completed',
        isComplete: true,
        attachments: [
          {
            id: 'img-1',
            type: 'image',
            name: 'crash_log.png',
            url: 'https://placehold.co/800x600/000000/FFFFFF/png?text=Crash+Log',
          },
          {
            id: 'ref-1',
            type: 'file',
            name: 'config.json',
            url: 'https://example.com/config.json',
          }
        ],
        references: [
          {
            type: 'file',
            id: 'f-ref-99',
            name: 'MessageContent.tsx',
            detail: '核心渲染逻辑组件'
          }
        ]
      }
    ];

    setConversationState({ messages: mockMessages });
  },

  /**
   * 模拟 AI 流式回复（增强版：包含 Markdown 和思考过程同步出现）
   */
  simulateAIStreaming: async () => {
    const { addMessage } = useConversationStore.getState();
    const streamId = generateUUID();

    addMessage({
      id: streamId,
      role: 'ai',
      content: '',
      thinking: '正在准备一段内容极其丰富的流式测试输出...',
      timestamp: Date.now(),
      isComplete: false,
      status: 'running',
    });

    const fullText = '### 流式输出测试\n这是实时生成的 Markdown 内容：\n- **性能**: 极快\n- **交互**: 顺滑\n- **渲染**: 准确\n\n```javascript\nconsole.log("Hello, Debug!");\n```\n希望你对这次的模拟数据满意。';
    const words = fullText.split('');
    let currentText = '';

    for (let i = 0; i < words.length; i++) {
      currentText += words[i];
      const { messages } = useConversationStore.getState();
      const index = messages.findIndex(m => m.id === streamId);
      if (index !== -1) {
        const updated = [...messages];
        updated[index] = { 
          ...updated[index], 
          content: currentText,
          status: i === words.length - 1 ? 'completed' : 'streaming'
        };
        useConversationStore.setState({ messages: updated });
      }
      await new Promise(resolve => setTimeout(resolve, 20));
    }
  },

  /**
   * 模拟多种类型的 HITL 请求
   */
  simulateHITLRequest: (type: 'approval' | 'choice' | 'text' = 'approval') => {
    const { setCurrentRequest } = useHITLStore.getState();
    const { addMessage } = useConversationStore.getState();
    
    const requestId = generateUUID();
    
    const prompts = {
      approval: '是否批准部署到生产环境？',
      choice: '请选择你想要的主题风格：',
      text: '请输入你的 API Key 以继续：'
    };

    const contexts = {
      approval: 'Target: production.example.com',
      choice: 'Options: Dark, Light, High Contrast',
      text: 'Required for OpenAI service'
    };

    addMessage({
      id: generateUUID(),
      role: 'ai',
      content: `[HITL] 我正在发起一个 ${type} 类型的请求，请在下方卡片中操作。`,
      timestamp: Date.now(),
      isComplete: true,
      status: 'waiting_human',
    });

    setCurrentRequest({
      id: requestId,
      type: type,
      prompt: prompts[type],
      context: contexts[type],
      options: type === 'choice' ? ['Dark', 'Light', 'Solarized'] : undefined,
      risk_level: type === 'approval' ? 'critical' : 'low',
      timestamp: Date.now(),
    });
  },

  /**
   * 清除所有数据
   */
  clearAll: () => {
    const { clearConversations } = useConversationStore.getState();
    const { setCurrentDevice } = useDeviceStore.getState();
    const { setCurrentRequest } = useHITLStore.getState();
    
    clearConversations();
    setCurrentDevice(null);
    setCurrentRequest(null);
  }
};
