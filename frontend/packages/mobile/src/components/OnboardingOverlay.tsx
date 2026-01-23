import { AnimatePresence, motion } from "framer-motion"
import {
  Check,
  ChevronRight,
  Image as ImageIcon,
  Mic,
  Monitor,
  Smartphone,
} from "lucide-react"
import { useEffect, useState } from "react"
import { Trans, useTranslation } from "react-i18next"
import { toast } from "sonner"
import { Button } from "@evoloop/shared/components/ui/button"

export function OnboardingOverlay() {
  const { t } = useTranslation()
  const [isVisible, setIsVisible] = useState(false)
  const [currentSlide, setCurrentSlide] = useState(0)

  useEffect(() => {
    const seen = localStorage.getItem("evoloop_onboarding_seen")
    if (!seen) {
      setIsVisible(true)
    }
  }, [])

  const handleComplete = () => {
    localStorage.setItem("evoloop_onboarding_seen", "true")
    setIsVisible(false)
  }

  const [direction, setDirection] = useState(0)

  const variants = {
    enter: (direction: number) => {
      return {
        x: direction > 0 ? 100 : -100,
        opacity: 0,
      }
    },
    center: {
      zIndex: 1,
      x: 0,
      opacity: 1,
    },
    exit: (direction: number) => {
      return {
        zIndex: 0,
        x: direction < 0 ? 100 : -100,
        opacity: 0,
      }
    },
  }

  const swipeConfidenceThreshold = 10000
  const swipePower = (offset: number, velocity: number) => {
    return Math.abs(offset) * velocity
  }

  const handleNext = () => {
    if (currentSlide < slides.length - 1) {
      setDirection(1)
      setCurrentSlide((prev) => prev + 1)
    } else {
      handleComplete()
    }
  }

  const handlePrev = () => {
    if (currentSlide > 0) {
      setDirection(-1)
      setCurrentSlide((prev) => prev - 1)
    }
  }

  const copyDownloadLink = () => {
    navigator.clipboard.writeText("https://develop-assistant.cn/download")
    toast.success(t("devices.linkCopied"))
  }

  if (!isVisible) return null

  const slides = [
    // Slide 1: Welcome
    {
      id: "welcome",
      content: (
        <div className="flex flex-col items-center text-center space-y-6">
          <div className="w-24 h-24 bg-primary/10 rounded-3xl flex items-center justify-center mb-4">
            <Smartphone className="w-12 h-12 text-primary" />
          </div>
          <h2 className="text-3xl font-bold tracking-tight">
            {t("onboarding.slide1.title")}
          </h2>
          <p className="text-muted-foreground text-lg leading-relaxed">
            <Trans
              i18nKey="onboarding.slide1.subtitle"
              components={{ br: <br /> }}
            />
          </p>
        </div>
      ),
    },
    // Slide 2: Gesture
    {
      id: "gesture",
      content: (
        <div className="flex flex-col items-center text-center space-y-6">
          <div className="relative w-64 h-40 bg-muted/30 rounded-xl border border-border/50 flex items-center justify-center overflow-hidden mb-4">
            <div className="absolute inset-0 flex">
              <div className="w-1/2 h-full bg-primary/5 border-r border-dashed border-primary/20 flex items-center justify-center">
                <span className="text-xs text-muted-foreground font-medium">
                  {t("onboarding.slide2.device")}
                </span>
              </div>
              <div className="w-1/2 h-full bg-background flex items-center justify-center">
                <span className="text-xs text-muted-foreground font-medium">
                  {t("onboarding.slide2.cloud")}
                </span>
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
          <h2 className="text-2xl font-bold">{t("onboarding.slide2.title")}</h2>
          <p className="text-muted-foreground text-lg">
            <Trans
              i18nKey="onboarding.slide2.subtitle"
              components={{
                bold: <span className="text-foreground font-semibold" />,
                br: <br />,
              }}
            />
          </p>
        </div>
      ),
    },
    // Slide 3: Connect
    {
      id: "connect",
      content: (
        <div className="flex flex-col items-center text-center space-y-6">
          <div className="w-24 h-24 bg-blue-500/10 rounded-full flex items-center justify-center mb-4 relative">
            <Monitor className="w-12 h-12 text-blue-500" />
            <div className="absolute -bottom-2 -right-2 bg-green-500 text-white text-[10px] px-2 py-0.5 rounded-full border-2 border-background">
              {t("onboarding.slide3.online")}
            </div>
          </div>
          <h2 className="text-2xl font-bold">{t("onboarding.slide3.title")}</h2>
          <p className="text-muted-foreground">
            <Trans
              i18nKey="onboarding.slide3.subtitle"
              components={{ br: <br /> }}
            />
          </p>
          <Button
            variant="outline"
            className="mt-4 gap-2"
            onClick={copyDownloadLink}
          >
            develop-assistant.cn/download
            <Check className="w-4 h-4" />
          </Button>
        </div>
      ),
    },
    // Slide 4: Tips
    {
      id: "tips",
      content: (
        <div className="flex flex-col items-center text-center space-y-6">
          <div className="grid grid-cols-2 gap-4 mb-4">
            <div className="bg-muted/50 p-4 rounded-xl flex flex-col items-center gap-2">
              <Mic className="w-6 h-6 text-primary" />
              <span className="text-xs font-medium">
                {t("onboarding.slide4.voice")}
              </span>
            </div>
            <div className="bg-muted/50 p-4 rounded-xl flex flex-col items-center gap-2">
              <ImageIcon className="w-6 h-6 text-primary" />
              <span className="text-xs font-medium">
                {t("onboarding.slide4.vision")}
              </span>
            </div>
          </div>
          <h2 className="text-2xl font-bold">{t("onboarding.slide4.title")}</h2>
          <p className="text-muted-foreground">
            <Trans
              i18nKey="onboarding.slide4.subtitle"
              components={{ br: <br /> }}
            />
          </p>
        </div>
      ),
    },
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
          <Button
            variant="ghost"
            size="sm"
            onClick={handleComplete}
            className="text-muted-foreground hover:text-foreground"
          >
            {t("onboarding.skip")}
          </Button>
        </div>

        {/* Content Area */}
        <div className="flex-1 flex flex-col items-center justify-center p-8 relative overflow-hidden">
          <div className="max-w-md w-full relative h-[400px] flex items-center justify-center">
            <AnimatePresence initial={false} custom={direction} mode="wait">
              <motion.div
                key={currentSlide}
                custom={direction}
                variants={variants}
                initial="enter"
                animate="center"
                exit="exit"
                transition={{
                  x: { type: "spring", stiffness: 300, damping: 30 },
                  opacity: { duration: 0.2 },
                }}
                drag="x"
                dragConstraints={{ left: 0, right: 0 }}
                dragElastic={1}
                onDragEnd={(_, { offset, velocity }) => {
                  const swipe = swipePower(offset.x, velocity.x)

                  if (swipe < -swipeConfidenceThreshold) {
                    handleNext()
                  } else if (swipe > swipeConfidenceThreshold) {
                    handlePrev()
                  }
                }}
                className="absolute inset-0 flex items-center justify-center cursor-grab active:cursor-grabbing"
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
                className={`h-2 rounded-full transition-all duration-300 ${index === currentSlide ? "w-8 bg-primary" : "w-2 bg-primary/20"}`}
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
              t("onboarding.start")
            ) : (
              <span className="flex items-center">
                {t("onboarding.next")} <ChevronRight className="ml-2 w-5 h-5" />
              </span>
            )}
          </Button>
        </div>
      </motion.div>
    </AnimatePresence>
  )
}
