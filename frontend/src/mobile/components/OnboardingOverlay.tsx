import { useState, useEffect } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { Button } from "@/components/ui/button"
import { ChevronRight, Check, Monitor, Smartphone, Mic, Image as ImageIcon } from "lucide-react"
import { toast } from "sonner"

export function OnboardingOverlay() {
    const [isVisible, setIsVisible] = useState(false)
    const [currentSlide, setCurrentSlide] = useState(0)

    useEffect(() => {
        const seen = localStorage.getItem('evoloop_onboarding_seen')
        if (!seen) {
            setIsVisible(true)
        }
    }, [])

    const handleComplete = () => {
        localStorage.setItem('evoloop_onboarding_seen', 'true')
        setIsVisible(false)
    }

    const handleNext = () => {
        if (currentSlide < slides.length - 1) {
            setCurrentSlide(prev => prev + 1)
        } else {
            handleComplete()
        }
    }

    const copyDownloadLink = () => {
        navigator.clipboard.writeText("https://develop-assistant.cn/download")
        toast.success("下载链接已复制")
    }

    if (!isVisible) return null

    const slides = [
        // Slide 1: Welcome
        {
            id: 'welcome',
            content: (
                <div className="flex flex-col items-center text-center space-y-6">
                    <div className="w-24 h-24 bg-primary/10 rounded-3xl flex items-center justify-center mb-4">
                        <Smartphone className="w-12 h-12 text-primary" />
                    </div>
                    <h2 className="text-3xl font-bold tracking-tight">EvoLoop AI</h2>
                    <p className="text-muted-foreground text-lg leading-relaxed">
                        您的随身智能助手。<br />
                        无论是编写代码、解答疑惑，<br />
                        还是头脑风暴，在这里随时开始。
                    </p>
                </div>
            )
        },
        // Slide 2: Gesture
        {
            id: 'gesture',
            content: (
                <div className="flex flex-col items-center text-center space-y-6">
                    <div className="relative w-64 h-40 bg-muted/30 rounded-xl border border-border/50 flex items-center justify-center overflow-hidden mb-4">
                        <div className="absolute inset-0 flex">
                            <div className="w-1/2 h-full bg-primary/5 border-r border-dashed border-primary/20 flex items-center justify-center">
                                <span className="text-xs text-muted-foreground font-medium">设备 (Local)</span>
                            </div>
                            <div className="w-1/2 h-full bg-background flex items-center justify-center">
                                <span className="text-xs text-muted-foreground font-medium">云端 (Cloud)</span>
                            </div>
                        </div>
                        <motion.div
                            className="absolute z-10 w-12 h-12 bg-primary/20 rounded-full flex items-center justify-center"
                            animate={{ x: [-40, 40, -40] }}
                            transition={{ repeat: Infinity, duration: 2, ease: "easeInOut" }}
                        >
                            <div className="w-4 h-4 bg-primary rounded-full" />
                        </motion.div>
                    </div>
                    <h2 className="text-2xl font-bold">双重世界</h2>
                    <p className="text-muted-foreground text-lg">
                        EvoLoop 拥有两面。<br />
                        <span className="text-foreground font-semibold">左右滑动</span> 试试看？<br />
                        在云端智能与设备管理间无缝切换。
                    </p>
                </div>
            )
        },
        // Slide 3: Connect
        {
            id: 'connect',
            content: (
                <div className="flex flex-col items-center text-center space-y-6">
                    <div className="w-24 h-24 bg-blue-500/10 rounded-full flex items-center justify-center mb-4 relative">
                        <Monitor className="w-12 h-12 text-blue-500" />
                        <div className="absolute -bottom-2 -right-2 bg-green-500 text-white text-[10px] px-2 py-0.5 rounded-full border-2 border-background">
                            Online
                        </div>
                    </div>
                    <h2 className="text-2xl font-bold">连接您的工作站</h2>
                    <p className="text-muted-foreground">
                        在电脑安装客户端，解锁远程控制能力。<br />
                        远程执行命令、管理文件，尽在掌握。
                    </p>
                    <Button variant="outline" className="mt-4 gap-2" onClick={copyDownloadLink}>
                        develop-assistant.cn/download
                        <Check className="w-4 h-4" />
                    </Button>
                </div>
            )
        },
        // Slide 4: Tips
        {
            id: 'tips',
            content: (
                <div className="flex flex-col items-center text-center space-y-6">
                    <div className="grid grid-cols-2 gap-4 mb-4">
                        <div className="bg-muted/50 p-4 rounded-xl flex flex-col items-center gap-2">
                            <Mic className="w-6 h-6 text-primary" />
                            <span className="text-xs font-medium">语音输入</span>
                        </div>
                        <div className="bg-muted/50 p-4 rounded-xl flex flex-col items-center gap-2">
                            <ImageIcon className="w-6 h-6 text-primary" />
                            <span className="text-xs font-medium">视觉分析</span>
                        </div>
                    </div>
                    <h2 className="text-2xl font-bold">高效技巧</h2>
                    <p className="text-muted-foreground">
                        点击输入框旁的图标，体验更多能力。<br />
                        现在，开始您的 EvoLoop 之旅吧！
                    </p>
                </div>
            )
        }
    ]

    return (
        <AnimatePresence>
            <motion.div
                className="fixed inset-0 z-50 bg-background/95 backdrop-blur-md flex flex-col"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
            >
                {/* Skip Button */}
                <div className="absolute top-safe-top right-4 z-20 pt-4">
                    <Button variant="ghost" size="sm" onClick={handleComplete} className="text-muted-foreground hover:text-foreground">
                        跳过
                    </Button>
                </div>

                {/* Content Area */}
                <div className="flex-1 flex flex-col items-center justify-center p-8 relative overflow-hidden">
                    <div className="max-w-md w-full relative h-[400px] flex items-center justify-center">
                        <AnimatePresence mode="wait">
                            <motion.div
                                key={currentSlide}
                                initial={{ opacity: 0, x: 50 }}
                                animate={{ opacity: 1, x: 0 }}
                                exit={{ opacity: 0, x: -50 }}
                                transition={{ duration: 0.3 }}
                                className="absolute inset-0 flex items-center justify-center"
                            >
                                {slides[currentSlide].content}
                            </motion.div>
                        </AnimatePresence>
                    </div>
                </div>

                {/* Footer Controls */}
                <div className="pb-safe-bottom bg-transparent p-6 flex flex-col gap-6">
                    {/* Dots */}
                    <div className="flex justify-center gap-2">
                        {slides.map((_, index) => (
                            <div
                                key={index}
                                className={`h-2 rounded-full transition-all duration-300 ${index === currentSlide ? "w-8 bg-primary" : "w-2 bg-primary/20"
                                    }`}
                            />
                        ))}
                    </div>

                    {/* Action Button */}
                    <Button
                        size="lg"
                        className="w-full text-lg rounded-full h-14 shadow-lg shadow-primary/20"
                        onClick={handleNext}
                    >
                        {currentSlide === slides.length - 1 ? (
                            "开始体验"
                        ) : (
                            <span className="flex items-center">
                                下一步 <ChevronRight className="ml-2 w-5 h-5" />
                            </span>
                        )}
                    </Button>
                </div>
            </motion.div>
        </AnimatePresence>
    )
}
