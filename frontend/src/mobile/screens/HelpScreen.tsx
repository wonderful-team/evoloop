import { useState } from "react"
import { Button } from "@/components/ui/button"
import { ChevronLeft, HelpCircle, Command, MessageSquare, Monitor, Zap, ChevronDown, ChevronUp } from "lucide-react"
import { useNavigate } from "@tanstack/react-router"

function QAItem({ question, answer }: { question: string, answer: React.ReactNode }) {
    const [isOpen, setIsOpen] = useState(false)

    return (
        <div className="border-b last:border-0 border-border/50">
            <button
                onClick={() => setIsOpen(!isOpen)}
                className="flex items-center justify-between w-full py-4 text-left font-medium text-sm hover:text-primary transition-colors"
            >
                {question}
                {isOpen ? <ChevronUp className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
            </button>
            {isOpen && (
                <div className="pb-4 text-sm text-muted-foreground leading-relaxed animate-in fade-in slide-in-from-top-1 duration-200">
                    {answer}
                </div>
            )}
        </div>
    )
}

export function HelpScreen() {
    const navigate = useNavigate()

    return (
        <div className="flex flex-col h-full bg-background relative">
            {/* Header */}
            <div className="flex items-center p-4 border-b">
                <Button variant="ghost" size="icon" onClick={() => navigate({ to: '/profile' as any })}>
                    <ChevronLeft className="w-5 h-5" />
                </Button>
                <h1 className="text-lg font-bold ml-2">用户手册</h1>
            </div>

            <div className="p-4 overflow-y-auto pb-20">

                {/* Intro Card */}
                <div className="bg-primary/5 rounded-xl p-5 mb-6 border border-primary/10">
                    <div className="flex items-center gap-3 mb-3">
                        <HelpCircle className="w-6 h-6 text-primary" />
                        <h2 className="text-lg font-semibold">快速入门</h2>
                    </div>
                    <p className="text-sm text-muted-foreground leading-relaxed">
                        EvoLoop 是您的双模智能助手。通过简单的左右滑动，您可以在 <b>云端智能</b> 和 <b>本地设备</b> 之间无缝切换。
                    </p>
                </div>

                <div className="space-y-6">
                    {/* Section 1: Capabilities */}
                    <section>
                        <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-3 pl-1">核心能力</h3>
                        <div className="grid grid-cols-2 gap-3">
                            <div className="bg-card border rounded-lg p-4 flex flex-col gap-2">
                                <MessageSquare className="w-5 h-5 text-blue-500" />
                                <h4 className="font-medium text-sm">云端助手</h4>
                                <p className="text-xs text-muted-foreground">问答、编码、创意</p>
                            </div>
                            <div className="bg-card border rounded-lg p-4 flex flex-col gap-2">
                                <Monitor className="w-5 h-5 text-green-500" />
                                <h4 className="font-medium text-sm">设备控制</h4>
                                <p className="text-xs text-muted-foreground">远程命令、文件访问</p>
                            </div>
                        </div>
                    </section>

                    {/* Section 2: FAQ */}
                    <section>
                        <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-3 pl-1">常见问题</h3>
                        <div className="bg-card border rounded-lg px-4">
                            <QAItem
                                question="如何连接我的电脑？"
                                answer="需要在您的 Mac/Windows 电脑上下载并安装 EvoLoop 客户端，并登录相同的账号。连接成功后，它会自动出现在“Devices”列表中。"
                            />
                            <QAItem
                                question="云端与本地模式的区别？"
                                answer={
                                    <>
                                        <b>云端模式 (Cloud)</b>：与运行在服务器上的 AI 交互，不依赖您的电脑。<br />
                                        <b>本地模式 (Local)</b>：通过 AI 直接操作您的电脑。可以读取本地文件、运行终端命令。
                                    </>
                                }
                            />
                            <QAItem
                                question="支持语音输入吗？"
                                answer="支持。在聊天输入框左侧点击麦克风图标即可开始说话。支持中文和英文指令。"
                            />
                        </div>
                    </section>

                    {/* Section 3: Tips */}
                    <section>
                        <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-3 pl-1">高级技巧</h3>
                        <div className="bg-muted/30 rounded-lg p-4 space-y-3">
                            <div className="flex gap-3">
                                <Zap className="w-4 h-4 text-yellow-500 shrink-0 mt-0.5" />
                                <p className="text-sm">
                                    <span className="font-medium">全局手势</span><br />
                                    在任意界面左右滑动，快速切换 Cloud / Local。
                                </p>
                            </div>
                            <div className="flex gap-3">
                                <Command className="w-4 h-4 text-purple-500 shrink-0 mt-0.5" />
                                <p className="text-sm">
                                    <span className="font-medium">Slash 命令</span><br />
                                    输入 <code>/</code> 呼出命令菜单，快速切换模型或工具 (如 /search, /draw)。
                                </p>
                            </div>
                        </div>
                    </section>

                    <div className="pt-8 text-center">
                        <Button variant="outline" size="sm" onClick={() => {
                            localStorage.removeItem('evoloop_onboarding_seen')
                            window.location.reload()
                        }}>
                            重播新手引导
                        </Button>
                    </div>

                </div>
            </div>
        </div>
    )
}
