// 3D 木头机器人组件 - 精确移植自移动端 WoodenRobot.tsx
// React Native StyleSheet → CSS 内联样式，数值 1:1 对应

import { cn } from "@evoloop/shared/lib/utils"
import { useNavigate } from "@tanstack/react-router"
import { motion } from "framer-motion"
import { ArrowRight, LayoutGrid, ListTodo, Wand2 } from "lucide-react"
import type React from "react"
import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

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
        {/* robotGlow: position:absolute w:140 h:140 borderRadius:70 top:10 */}
        <div
          style={{
            position: "absolute",
            width: 140,
            height: 140,
            borderRadius: 70,
            top: 10,
            backgroundColor: `${primaryColor}1A`,
          }}
        />

        {/* robotBody: alignItems:center */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
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
// ChatWelcome Page
// ─────────────────────────────────────────────

export const ChatWelcome: React.FC = () => {
  const { t } = useTranslation()
  const navigate = useNavigate()

  return (
    <div className="flex flex-col items-center justify-between min-h-[600px] py-20 px-4 max-w-4xl mx-auto text-center h-full">
      {/* Top: Title & Subtitle */}
      <div>
        {/* Title */}
        <h1
          style={{
            fontSize: 24,
            fontWeight: "bold",
            marginTop: 16,
            lineHeight: "32px",
          }}
          className="text-primary text-center"
        >
          EvoLoop AI
        </h1>
        {/* Subtitle */}
        <p
          style={{ fontSize: 16, fontWeight: 250, marginTop: 16 }}
          className="text-muted-foreground text-center"
        >
          {t("chat.welcome.mobileSubtitle")}
        </p>
        {/* Hint — bodySmall(12px) + marginTop:4 + opacity:0.6 + onSurfaceVariant */}
        <p
          style={{ fontSize: 12, marginTop: 12, opacity: 0.6 }}
          className="text-muted-foreground text-center"
        >
          {t("chat.welcome.mobileHint")}
        </p>
      </div>

      {/* Middle: Robot */}
      <motion.div
        initial={{ opacity: 0, scale: 0.85 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 0.2, duration: 0.5 }}
        className="flex-1 flex items-center justify-center py-20"
      >
        <WoodenRobot />
      </motion.div>

      {/* Bottom: Navigation Cards */}
      <motion.div
        className="w-full pt-12"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.4 }}
      >
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 w-full">
          {[
            {
              to: "/projects",
              icon: <LayoutGrid size={16} />,
              label: t("chat.welcome.nav.projects"),
              desc: t("chat.welcome.nav.projectsDesc"),
              color: "text-primary",
            },
            {
              to: "/todos",
              icon: <ListTodo size={16} />,
              label: t("chat.welcome.nav.todos"),
              desc: t("chat.welcome.nav.todosDesc"),
              color: "text-emerald-500",
            },
            {
              to: "/learning",
              icon: <Wand2 size={16} />,
              label: t("chat.welcome.nav.skills"),
              desc: t("chat.welcome.nav.skillsDesc"),
              color: "text-purple-500",
            },
          ].map((nav, idx) => (
            <motion.div
              key={idx}
              whileHover={{ scale: 1.02, y: -2 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => navigate({ to: nav.to as any })}
              className="group cursor-pointer p-3 rounded-xl bg-background border border-border hover:border-primary/20 hover:bg-muted/5 transition-all flex flex-col gap-1.5 text-left"
            >
              <div className="flex items-center gap-2 mb-0.5">
                <div
                  className={cn(
                    "w-7 h-7 rounded-lg bg-muted flex items-center justify-center group-hover:scale-110 transition-transform flex-shrink-0",
                    nav.color,
                  )}
                >
                  {nav.icon}
                </div>
                <h3 className="text-[13px] font-medium uppercase tracking-tight line-clamp-1">
                  {nav.label}
                </h3>
              </div>
              <p className="text-[11px] text-muted-foreground/60 leading-relaxed line-clamp-2">
                {nav.desc}
              </p>
              <div className="flex items-center justify-end mt-auto pt-1">
                <div className="w-5 h-5 rounded-full bg-muted/50 flex items-center justify-center group-hover:bg-primary group-hover:text-white transition-all">
                  <ArrowRight size={10} />
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      </motion.div>
    </div>
  )
}
