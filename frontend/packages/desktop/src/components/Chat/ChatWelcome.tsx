// 3D 木头机器人组件 - 精确移植自移动端 WoodenRobot.tsx
// React Native StyleSheet → CSS 内联样式，数值 1:1 对应

import { useNavigate } from "@tanstack/react-router"
import { motion } from "framer-motion"
import { LayoutGrid, Wand2 } from "lucide-react"
import type React from "react"
import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { useHostContextStore } from "@/stores/hostContextStore"

// ─────────────────────────────────────────────
// WoodenRobot — 1:1 port from mobile
// ─────────────────────────────────────────────

interface WoodenRobotProps {
  primaryColor?: string
  mood?: "neutral" | "speaking"
}

function EyeWithBlink({
  primaryColor,
  blinkScaleY,
}: {
  primaryColor: string
  blinkScaleY: number
}) {
  // eyeContainer: width:22, height:22
  // eyeWhite: width:20, height:20, borderRadius:10, bg:#FFF, borderWidth:2, shadow
  // eyeBall: width:13, height:13, borderRadius:6.5
  // eyeShineMain: absolute top:2 right:2 w:5 h:5 r:2.5 bg:#FFF opacity:0.9
  // eyeShineSmall: absolute bottom:2 left:2 w:2.5 h:2.5 r:1.25 bg:#FFF opacity:0.7
  return (
    <div
      style={{
        width: 22,
        height: 22,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <div
        style={{
          width: 20,
          height: 20,
          borderRadius: 10,
          backgroundColor: "#FFFFFF",
          border: `2px solid ${primaryColor}`,
          boxShadow: "0 1px 1px rgba(0,0,0,0.15)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          transform: `scaleY(${blinkScaleY})`,
          transition: "transform 0.08s ease",
        }}
      >
        <div
          style={{
            width: 13,
            height: 13,
            borderRadius: 6.5,
            backgroundColor: primaryColor,
            position: "relative",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <div
            style={{
              position: "absolute",
              top: 2,
              right: 2,
              width: 5,
              height: 5,
              borderRadius: 2.5,
              backgroundColor: "#FFFFFF",
              opacity: 0.9,
            }}
          />
          <div
            style={{
              position: "absolute",
              bottom: 2,
              left: 2,
              width: 2.5,
              height: 2.5,
              borderRadius: 1.25,
              backgroundColor: "#FFFFFF",
              opacity: 0.7,
            }}
          />
        </div>
      </div>
    </div>
  )
}

function EyeOpen({ primaryColor }: { primaryColor: string }) {
  // eyeWhiteLarge: width:24, height:24, borderRadius:12
  // eyeBallLarge: width:16, height:16, borderRadius:8
  // eyeShineMainLarge: top:2 right:3 w:6 h:6 r:3
  // eyeShineSmallLarge: bottom:2 left:3 w:3 h:3 r:1.5
  return (
    <div
      style={{
        width: 22,
        height: 22,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <div
        style={{
          width: 24,
          height: 24,
          borderRadius: 12,
          backgroundColor: "#FFFFFF",
          border: `2px solid ${primaryColor}`,
          boxShadow: "0 1px 1px rgba(0,0,0,0.15)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <div
          style={{
            width: 16,
            height: 16,
            borderRadius: 8,
            backgroundColor: primaryColor,
            position: "relative",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <div
            style={{
              position: "absolute",
              top: 2,
              right: 3,
              width: 6,
              height: 6,
              borderRadius: 3,
              backgroundColor: "#FFFFFF",
              opacity: 0.9,
            }}
          />
          <div
            style={{
              position: "absolute",
              bottom: 2,
              left: 3,
              width: 3,
              height: 3,
              borderRadius: 1.5,
              backgroundColor: "#FFFFFF",
              opacity: 0.7,
            }}
          />
        </div>
      </div>
    </div>
  )
}

export function WoodenRobot({
  primaryColor = "#109C8F",
  mood = "neutral",
}: WoodenRobotProps) {
  // Blink logic (mirrors scheduleBlink / doBlink)
  const [blinkScaleY, setBlinkScaleY] = useState(1)
  const blinkingRef = useRef(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    const doBlink = () => {
      if (blinkingRef.current) return
      blinkingRef.current = true
      setBlinkScaleY(0.1)
      setTimeout(() => {
        setBlinkScaleY(1)
        setTimeout(() => {
          blinkingRef.current = false
        }, 100)
      }, 80)
    }
    const scheduleBlink = () => {
      const delay = 6000 + Math.random() * 8000
      timerRef.current = setTimeout(() => {
        doBlink()
        scheduleBlink()
      }, delay)
    }
    scheduleBlink()
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [])

  const renderExpression = () => {
    if (mood === "speaking") {
      return (
        <>
          {/* eyesRow: flexDirection:row, gap:8, marginBottom:4 */}
          <div
            style={{
              display: "flex",
              flexDirection: "row",
              gap: 8,
              marginBottom: 4,
              alignItems: "center",
            }}
          >
            <EyeOpen primaryColor={primaryColor} />
            <EyeOpen primaryColor={primaryColor} />
          </div>
          {/* mouthSpeaking: w:16 h:8 bg:#6B4423 borderRadius:4 overflow:hidden */}
          <div
            style={{
              width: 16,
              height: 8,
              backgroundColor: "#6B4423",
              borderRadius: 4,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              overflow: "hidden",
            }}
          >
            {/* mouthSpeakingInner: w:8 h:3 bg:#D4A5A5 r:1.5 */}
            <div
              style={{
                width: 8,
                height: 3,
                backgroundColor: "#D4A5A5",
                borderRadius: 1.5,
              }}
            />
          </div>
        </>
      )
    }
    return (
      <>
        {/* eyesRow */}
        <div
          style={{
            display: "flex",
            flexDirection: "row",
            gap: 8,
            marginBottom: 4,
            alignItems: "center",
          }}
        >
          <EyeWithBlink primaryColor={primaryColor} blinkScaleY={blinkScaleY} />
          <EyeWithBlink primaryColor={primaryColor} blinkScaleY={blinkScaleY} />
        </div>
        {/* mouthNeutral: w:16 h:4 borderBottom:2 borderLeft:0.5 borderRight:0.5 borderTop:0
            borderBottomLeftRadius:4 borderBottomRightRadius:4 borderColor:#6B4423 marginTop:3 */}
        <div
          style={{
            width: 16,
            height: 4,
            borderBottom: "2px solid #6B4423",
            borderLeft: "0.5px solid #6B4423",
            borderRight: "0.5px solid #6B4423",
            borderTop: "none",
            borderBottomLeftRadius: 4,
            borderBottomRightRadius: 4,
            marginTop: 3,
          }}
        />
      </>
    )
  }

  return (
    <>
      <style>{`@keyframes robot-float { 0%,100% { transform: translateY(0) } 50% { transform: translateY(-8px) } }`}</style>
      <div
        style={{
          width: 160,
          height: 180,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          position: "relative",
          animation: "robot-float 4s ease-in-out infinite",
        }}
      >
        {/* robotGlow: position:absolute w:148 h:148 borderRadius:74 居中于容器 */}
        <div
          style={{
            position: "absolute",
            width: 148,
            height: 148,
            borderRadius: 74,
            top: 20,
            left: 6,
            backgroundColor: `${primaryColor}1A`,
          }}
        />

        {/* robotBody: alignItems:center — marginTop 下移补偿天线向上伸出造成的视觉偏上 */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            marginTop: 20,
          }}
        >
          {/* robotHead: w:80 h:70 bg:#C4A574 borderRadius:12
            border:3 borderColor:#8B6914 borderBottom:4 borderRight:4
            shadow: 0 3 6 rgba(0,0,0,0.25) elevation:6 zIndex:10 */}
          <div
            style={{
              width: 80,
              height: 70,
              backgroundColor: "#C4A574",
              borderRadius: 12,
              borderTop: "3px solid #8B6914",
              borderLeft: "3px solid #8B6914",
              borderBottom: "4px solid #8B6914",
              borderRight: "4px solid #8B6914",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              position: "relative",
              zIndex: 10,
              boxShadow: "0 3px 6px rgba(0,0,0,0.25)",
            }}
          >
            {/* woodTexture: absoluteFill opacity:0.2 borderRadius:9 */}
            <div
              style={{
                position: "absolute",
                inset: 0,
                opacity: 0.2,
                borderRadius: 9,
                pointerEvents: "none",
              }}
            />

            {/* antenna: position:absolute top:-14 w:4 h:14 bg:#8B7355 border:1 #6B4423 */}
            <div
              style={{
                position: "absolute",
                top: -14,
                width: 4,
                height: 14,
                backgroundColor: "#8B7355",
                border: "1px solid #6B4423",
              }}
            >
              {/* antennaBall: absolute top:-7 left:-4 w:12 h:12 borderRadius:6 */}
              <div
                style={{
                  position: "absolute",
                  top: -7,
                  left: -4,
                  width: 12,
                  height: 12,
                  borderRadius: 6,
                  backgroundColor: primaryColor,
                  boxShadow: "0 1px 2px rgba(0,0,0,0.4)",
                }}
              />
            </div>

            {/* screwTop: absolute top:6 w:8 h:8 borderRadius:4 bg:#6B4423 */}
            <div
              style={{
                position: "absolute",
                top: 6,
                width: 8,
                height: 8,
                borderRadius: 4,
                backgroundColor: "#6B4423",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              {/* screwSlot: w:5 h:2 bg:#3D2914 */}
              <div
                style={{ width: 5, height: 2, backgroundColor: "#3D2914" }}
              />
            </div>

            {/* faceContainer: alignItems:center marginTop:8 */}
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                marginTop: 8,
              }}
            >
              {renderExpression()}
            </div>

            {/* sideScrew left:6 — absolute top:50% marginTop:-3 w:5 h:5 borderRadius:2.5 bg:#6B4423 */}
            <div
              style={{
                position: "absolute",
                top: "50%",
                marginTop: -3,
                left: 6,
                width: 5,
                height: 5,
                borderRadius: 2.5,
                backgroundColor: "#6B4423",
              }}
            />
            <div
              style={{
                position: "absolute",
                top: "50%",
                marginTop: -3,
                right: 6,
                width: 5,
                height: 5,
                borderRadius: 2.5,
                backgroundColor: "#6B4423",
              }}
            />

            {/* cheek — absolute top:58% w:8 h:5 borderRadius:2.5 bg:#D4A5A5 opacity:0.5 */}
            <div
              style={{
                position: "absolute",
                top: "58%",
                left: 6,
                width: 8,
                height: 5,
                borderRadius: 2.5,
                backgroundColor: "#D4A5A5",
                opacity: 0.5,
              }}
            />
            <div
              style={{
                position: "absolute",
                top: "58%",
                right: 6,
                width: 8,
                height: 5,
                borderRadius: 2.5,
                backgroundColor: "#D4A5A5",
                opacity: 0.5,
              }}
            />
          </div>

          {/* robotNeck: marginTop:-2 zIndex:5 */}
          <div style={{ marginTop: -2, zIndex: 5 }}>
            {/* neckRing: w:24 h:6 bg:#8B7355 borderRadius:3 border:1.5 #6B4423 */}
            <div
              style={{
                width: 24,
                height: 6,
                backgroundColor: "#8B7355",
                borderRadius: 3,
                border: "1.5px solid #6B4423",
              }}
            />
          </div>

          {/* torsoWithArms: flexDirection:row alignItems:flex-start marginTop:-8 zIndex:5 */}
          <div
            style={{
              display: "flex",
              flexDirection: "row",
              alignItems: "flex-start",
              justifyContent: "center",
              marginTop: -8,
              zIndex: 5,
            }}
          >
            {/* armLeft: arm + armLeft — marginTop:2, marginRight:-4, rotate(50deg) */}
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                marginTop: 2,
                marginRight: -4,
                transform: "rotate(50deg)",
              }}
            >
              {/* armWood: w:14 h:32 bg:#B8956A borderRadius:7
                border:2 #8B6914 borderBottom:2.5 borderRight:2.5 overflow:hidden */}
              <div
                style={{
                  width: 14,
                  height: 32,
                  backgroundColor: "#B8956A",
                  borderRadius: 7,
                  borderTop: "2px solid #8B6914",
                  borderLeft: "2px solid #8B6914",
                  borderBottom: "2.5px solid #8B6914",
                  borderRight: "2.5px solid #8B6914",
                  position: "relative",
                  overflow: "hidden",
                }}
              >
                {/* armWoodGrain: absoluteFill opacity:0.15 */}
                <div
                  style={{
                    position: "absolute",
                    inset: 0,
                    opacity: 0.15,
                    pointerEvents: "none",
                  }}
                />
              </div>
              {/* hand: w:16 h:10 bg:#A0826D borderRadius:5 border:1.5 #6B4423 marginTop:-3 gap:1 */}
              <div
                style={{
                  width: 16,
                  height: 10,
                  backgroundColor: "#A0826D",
                  borderRadius: 5,
                  border: "1.5px solid #6B4423",
                  marginTop: -3,
                  display: "flex",
                  flexDirection: "row",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 1,
                }}
              >
                {/* finger: w:2.5 h:4 bg:#8B7355 borderRadius:1 border:0.5 #6B4423 */}
                {[0, 1, 2].map((i) => (
                  <div
                    key={i}
                    style={{
                      width: 2.5,
                      height: 4,
                      backgroundColor: "#8B7355",
                      borderRadius: 1,
                      border: "0.5px solid #6B4423",
                    }}
                  />
                ))}
              </div>
            </div>

            {/* robotTorso: w:50 h:42 bg:#B8956A borderRadius:6
              border:2.5 #8B6914 borderBottom:3 borderRight:3
              shadow: 0 3 4 rgba(0,0,0,0.25) elevation:4 zIndex:10 */}
            <div
              style={{
                width: 50,
                height: 42,
                backgroundColor: "#B8956A",
                borderRadius: 6,
                borderTop: "2.5px solid #8B6914",
                borderLeft: "2.5px solid #8B6914",
                borderBottom: "3px solid #8B6914",
                borderRight: "3px solid #8B6914",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                position: "relative",
                zIndex: 10,
                boxShadow: "0 3px 4px rgba(0,0,0,0.25)",
              }}
            >
              {/* chestPanel: w:34 h:28 bg:#A0826D borderRadius:4 border:1.5 #6B4423 */}
              <div
                style={{
                  width: 34,
                  height: 28,
                  backgroundColor: "#A0826D",
                  borderRadius: 4,
                  border: "1.5px solid #6B4423",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <div
                  className="animate-pulse"
                  style={{
                    width: 14,
                    height: 14,
                    borderRadius: 7,
                    backgroundColor: primaryColor,
                  }}
                />
              </div>
              {/* torsoWoodGrain: absoluteFill opacity:0.2 borderRadius:4 */}
              <div
                style={{
                  position: "absolute",
                  inset: 0,
                  opacity: 0.2,
                  borderRadius: 4,
                  pointerEvents: "none",
                }}
              />
            </div>

            {/* armRight: arm + armRight — marginTop:2, marginLeft:-4, rotate(-50deg) */}
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                marginTop: 2,
                marginLeft: -4,
                transform: "rotate(-50deg)",
              }}
            >
              <div
                style={{
                  width: 14,
                  height: 32,
                  backgroundColor: "#B8956A",
                  borderRadius: 7,
                  borderTop: "2px solid #8B6914",
                  borderLeft: "2px solid #8B6914",
                  borderBottom: "2.5px solid #8B6914",
                  borderRight: "2.5px solid #8B6914",
                  position: "relative",
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    position: "absolute",
                    inset: 0,
                    opacity: 0.15,
                    pointerEvents: "none",
                  }}
                />
              </div>
              <div
                style={{
                  width: 16,
                  height: 10,
                  backgroundColor: "#A0826D",
                  borderRadius: 5,
                  border: "1.5px solid #6B4423",
                  marginTop: -3,
                  display: "flex",
                  flexDirection: "row",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 1,
                }}
              >
                {[0, 1, 2].map((i) => (
                  <div
                    key={i}
                    style={{
                      width: 2.5,
                      height: 4,
                      backgroundColor: "#8B7355",
                      borderRadius: 1,
                      border: "0.5px solid #6B4423",
                    }}
                  />
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}

// ─────────────────────────────────────────────
// ChatWelcome Page — Engineering Premium
// 近黑画布 · 发丝线 · mono 眉标 · 吉祥物降级为头像
// ─────────────────────────────────────────────

const WELCOME_NAVS = [
  {
    to: "/projects",
    icon: LayoutGrid,
    labelKey: "chat.welcome.nav.projects",
    descKey: "chat.welcome.nav.projectsDesc",
  },
  {
    to: "/learning",
    icon: Wand2,
    labelKey: "chat.welcome.nav.skills",
    descKey: "chat.welcome.nav.skillsDesc",
  },
]

export const ChatWelcome: React.FC = () => {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const hostContext = useHostContextStore((s) => s.context)
  const hostConnected = useHostContextStore((s) => s.connected)

  const greetingKey = () => {
    const hour = new Date().getHours()
    if (hour >= 6 && hour < 12) return "morning"
    if (hour >= 12 && hour < 18) return "afternoon"
    if (hour >= 18 && hour < 23) return "evening"
    return "night"
  }

  return (
    <div className="relative flex h-full min-h-[520px] flex-col items-center justify-center overflow-hidden px-4 py-12">
      {/* Hero 装饰层：Vercel 式网格 + teal 辉光 */}
      <div className="hero-grid-bg" aria-hidden="true" />
      <div className="hero-glow-soft" aria-hidden="true" />

      <div className="relative z-10 flex flex-col items-center text-center">
        {/* Agent 头像 — 吉祥物降级为圆形徽标 */}
        <motion.div
          initial={{ opacity: 0, scale: 0.85 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
          className="mb-9 flex h-28 w-28 items-center justify-center overflow-hidden rounded-full border border-border bg-card shadow-[0_0_60px_rgba(45,212,191,0.14)]"
        >
          <div style={{ transform: "scale(0.68)" }}>
            <WoodenRobot />
          </div>
        </motion.div>

        {/* 状态徽章 — mono 胶囊 + 呼吸点 */}
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1, duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
          className="mb-6 inline-flex items-center gap-2.5 rounded-full border border-border bg-card px-3.5 py-1.5 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground"
        >
          <span className="relative flex h-1.5 w-1.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-60" />
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-primary shadow-[0_0_8px_var(--primary)]" />
          </span>
          {t("chat.welcome.statusStandby")}
        </motion.div>

        {/* 标题区 */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.18, duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
        >
          <h1 className="hidden text-[32px] font-semibold leading-[1.05] tracking-[-0.035em] text-foreground">
            EvoLoop AI
          </h1>
          <p className="mx-auto mt-4 max-w-md text-[15px] leading-relaxed text-muted-foreground">
            {hostContext
              ? t("chat.welcome.contextSubtitle", {
                  page: hostContext.pageName || hostContext.route,
                })
              : hostConnected
                ? t("chat.welcome.hostConnecting")
                : t(`chat.welcome.subtitle.${greetingKey()}`)}
          </p>
          <p className="mt-2.5 font-mono text-[11px] tracking-[0.04em] text-muted-foreground/50">
            {hostConnected
              ? t("chat.welcome.hostConnected", {
                  route: hostContext?.route ?? "syncing",
                })
              : t("chat.welcome.mobileHint")}
          </p>
        </motion.div>
      </div>

      {/* 导航卡片 — 宿主内嵌时隐藏（纯对话组件，无桌面导航语义） */}
      {!hostConnected && (
        <motion.div
          className="relative z-10 mt-14 w-full max-w-3xl"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3, duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
        >
          <div className="grid w-full grid-cols-1 gap-3.5 sm:grid-cols-2">
            {WELCOME_NAVS.map((nav, idx) => (
              <button
                key={nav.to}
                type="button"
                onClick={() => navigate({ to: nav.to as any })}
                className="group flex flex-col items-start rounded-xl border border-border bg-card p-4 text-left transition-all duration-300 hover:-translate-y-0.5 hover:border-foreground/20 hover:bg-accent/40"
              >
                <div className="flex w-full items-center justify-between">
                  <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-muted text-muted-foreground transition-colors group-hover:border-primary/30 group-hover:text-primary">
                    <nav.icon size={15} />
                  </div>
                  <span className="font-mono text-[10px] tracking-[0.14em] text-muted-foreground/40">
                    {`0${idx + 1}`}
                  </span>
                </div>
                <h3 className="mt-3.5 text-[13px] font-medium tracking-tight text-foreground">
                  {t(nav.labelKey)}
                </h3>
                <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
                  {t(nav.descKey)}
                </p>
              </button>
            ))}
          </div>
        </motion.div>
      )}
    </div>
  )
}
