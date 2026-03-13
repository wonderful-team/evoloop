import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState, useCallback, useRef } from "react";
import { Pin, Check, X, Crosshair } from "lucide-react";
import { emit, listen, UnlistenFn } from "@tauri-apps/api/event";
import { getCurrentWindow, LogicalSize, LogicalPosition } from "@tauri-apps/api/window";
import { invoke } from "@tauri-apps/api/core";
import { motion, AnimatePresence } from "framer-motion";
import { LearningService } from "@/client/sdk.gen";

export const Route = createFileRoute("/android-marker-overlay")({
    component: AndroidMarkerOverlay,
});

interface ExtractRegion {
    id: string;
    timestamp: number;
    x: number;
    y: number;
    width: number;
    height: number;
}

interface WindowBounds {
    x: number;
    y: number;
    width: number;
    height: number;
}

function AndroidMarkerOverlay() {
    const [isExtractMode, setIsExtractMode] = useState(false);
    const [isSelecting, setIsSelecting] = useState(false);
    const [extractRegions, setExtractRegions] = useState<ExtractRegion[]>([]);
    const hasDragged = useRef(false);
    const preExtractPosition = useRef<{ x: number, y: number } | null>(null);

    // Selection state
    const [selectionStart, setSelectionStart] = useState({ x: 0, y: 0 });
    const [selectionEnd, setSelectionEnd] = useState({ x: 0, y: 0 });
    const [currentMousePos, setCurrentMousePos] = useState({ x: 0, y: 0 });
    const containerRef = useRef<HTMLDivElement>(null);

    // Mirror window bounds (scrcpy window)
    const [mirrorBounds, setMirrorBounds] = useState<WindowBounds | null>(null);

    // Listen for session info from main window
    const sessionIdRef = useRef<string | null>(null);
    const recordingStartTimeRef = useRef<number | null>(null);
    const threadIdRef = useRef<string | null>(null);
    const deviceIdRef = useRef<string | null>(null);

    useEffect(() => {
        // Ensure the HTML body is transparent so the window transparency works
        document.body.style.background = "transparent";
        document.body.style.overflow = "hidden";
        document.documentElement.style.overflow = "hidden";

        // Move overlay to the top-right corner by default
        const initPosition = async () => {
            try {
                const { currentMonitor } = await import("@tauri-apps/api/window");
                const monitor = await currentMonitor();
                if (monitor) {
                    const win = getCurrentWindow();
                    const x = (monitor.size.width / monitor.scaleFactor) - 100;
                    await win.setPosition(new LogicalPosition(x, 50));
                    await win.show();
                }
            } catch (e) {
                console.log("[AndroidMarkerOverlay] Failed to set initial position", e);
            }
        };
        initPosition();
    }, []);

    // [Scheme C] Setup listener for session info from main window
    useEffect(() => {
        let unlisten: UnlistenFn | undefined;

        const setupListener = async () => {
            unlisten = await listen<{ sessionId: string, recordingStartTime: number | null, threadId: string | null, deviceId?: string | null }>(
                "android-marker-session",
                (event) => {
                    sessionIdRef.current = event.payload.sessionId;
                    recordingStartTimeRef.current = event.payload.recordingStartTime;
                    threadIdRef.current = event.payload.threadId;
                    deviceIdRef.current = event.payload.deviceId || null;
                    console.log("[AndroidMarkerOverlay] Session info received:", event.payload);
                }
            );

            // [FIX] Emit ready event to notify main window that we're listening
            // This handles the race condition where main window emits before we're ready
            await emit("android-marker-ready", {});
            console.log("[AndroidMarkerOverlay] Emitted ready event");
        };

        setupListener();

        return () => {
            if (unlisten) unlisten();
        };
    }, []);

    // Track mouse position for crosshair - relative to the (already resized) window
    const handleMouseMove = useCallback((e: MouseEvent) => {
        if (!isExtractMode) return;

        // Mouse coordinates are already relative to the window (which matches scrcpy bounds)
        const x = e.clientX;
        const y = e.clientY;

        setCurrentMousePos({ x, y });
        if (isSelecting) {
            setSelectionEnd({ x, y });
        }
    }, [isSelecting, isExtractMode]);

    // Handle window dragging or selection
    const handleMouseDown = useCallback(async (e: React.MouseEvent) => {
        if (isExtractMode) {
            e.preventDefault();
            e.stopPropagation();
            setIsSelecting(true);
            // Coordinates are screen-relative because we are full-screen (0,0)
            setSelectionStart({ x: e.clientX, y: e.clientY });
            setSelectionEnd({ x: e.clientX, y: e.clientY });
            return;
        }

        // Use Tauri's native dragging for smooth, jitter-free OS-level window movement
        try {
            const win = getCurrentWindow();
            await win.startDragging();
        } catch (err) {
            console.log("[AndroidMarkerOverlay] Failed to start dragging:", err);
        }
    }, [isExtractMode, mirrorBounds]);

    const handleMouseUp = useCallback(async () => {
        if (isSelecting) {
            setIsSelecting(false);

            // Use mirror bounds for coordinate calculation if available
            const bounds = mirrorBounds;
            if (!bounds) {
                console.error("[AndroidMarkerOverlay] No mirror bounds available");
                return;
            }

            // Coordinates are already screen-relative since we are full-screen
            const x1 = Math.min(selectionStart.x, selectionEnd.x);
            const y1 = Math.min(selectionStart.y, selectionEnd.y);
            const x2 = Math.max(selectionStart.x, selectionEnd.x);
            const y2 = Math.max(selectionStart.y, selectionEnd.y);

            // Clamp to mirror bounds specifically
            const clampedX1 = Math.max(bounds.x, x1);
            const clampedY1 = Math.max(bounds.y, y1);
            const clampedX2 = Math.min(bounds.x + bounds.width, x2);
            const clampedY2 = Math.min(bounds.y + bounds.height, y2);

            const isPointClick = clampedX2 - clampedX1 < 10 || clampedY2 - clampedY1 < 10;
            const startTime = recordingStartTimeRef.current;
            const relativeTimestamp = startTime ? Date.now() - startTime : 0;

            // Calculate relative coordinates (0-1 range) within the mirror window
            const region: ExtractRegion = {
                id: `extract_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
                timestamp: relativeTimestamp,
                x: (clampedX1 - bounds.x) / bounds.width,
                y: (clampedY1 - bounds.y) / bounds.height,
                width: isPointClick ? 0.02 : (clampedX2 - clampedX1) / bounds.width,
                height: isPointClick ? 0.02 : (clampedY2 - clampedY1) / bounds.height,
            };

            setExtractRegions((prev) => [...prev, region]);
            await saveRegionToBackend(region);

            setIsExtractMode(false);
            setMirrorBounds(null); // Clear bounds when exiting
            // Notify main window to resume recording interaction events
            await emit("marking-stopped", {});
            try {
                const win = getCurrentWindow();
                await win.setSize(new LogicalSize(64, 64));
                if (preExtractPosition.current) {
                    await win.setPosition(new LogicalPosition(preExtractPosition.current.x, preExtractPosition.current.y));
                }
            } catch (e) {
                console.log("[AndroidMarkerOverlay] Failed to resize window:", e);
            }

            return;
        }
    }, [isSelecting, selectionStart, selectionEnd, mirrorBounds]);

    const saveRegionToBackend = async (region: ExtractRegion) => {
        const sessionId = sessionIdRef.current;
        const threadId = threadIdRef.current;

        if (!sessionId || !threadId) {
            console.error("[AndroidMarkerOverlay] No session ID or thread ID available");
            return;
        }

        try {
            // [Scheme C] Coordinates are now relative to the mirror window (0-1 range)
            await LearningService.persistDomEvents({
                requestBody: {
                    session_id: sessionId,
                    thread_id: threadId,
                    events: [{
                        timestamp: region.timestamp,
                        event_type: "region_extract",
                        selector: `android://screen/${region.x.toFixed(4)}/${region.y.toFixed(4)}`,
                        target_text: "Android region extraction",
                        coordinates: {
                            x: region.x,
                            y: region.y,
                            width: region.width,
                            height: region.height,
                        },
                    }]
                }
            });

            await emit("android-region-marked", { region });
            console.log("[AndroidMarkerOverlay] Region extract event saved to TraceEvent:", region);
        } catch (error) {
            console.error("[AndroidMarkerOverlay] Failed to save region extract event:", error);
        }
    };

    useEffect(() => {
        window.addEventListener("mousemove", handleMouseMove);
        window.addEventListener("mouseup", handleMouseUp);
        return () => {
            window.removeEventListener("mousemove", handleMouseMove);
            window.removeEventListener("mouseup", handleMouseUp);
        };
    }, [handleMouseMove, handleMouseUp]);

    const handleClick = useCallback(async () => {
        if (hasDragged.current) {
            hasDragged.current = false;
            return;
        }

        if (isExtractMode) {
            setIsExtractMode(false);
            setMirrorBounds(null);
            // Notify main window to resume recording interaction events
            await emit("marking-stopped", {});
            try {
                const win = getCurrentWindow();
                await win.setSize(new LogicalSize(64, 64));
                if (preExtractPosition.current) {
                    await win.setPosition(new LogicalPosition(preExtractPosition.current.x, preExtractPosition.current.y));
                }
            } catch (e) {
                console.log("[AndroidMarkerOverlay] Failed to resize window:", e);
            }
            return;
        }

        // [Scheme C] Get mirror window bounds before expanding
        const deviceId = deviceIdRef.current;
        console.log("[AndroidMarkerOverlay] Device ID from ref:", deviceId);

        if (!deviceId) {
            console.error("[AndroidMarkerOverlay] No device ID available");
            alert("无法获取设备信息，请重新开始录制");
            return;
        }

        try {
            // [Scheme C] Get the scrcpy window bounds for active area detection
            const bounds: WindowBounds = await invoke("get_mirror_window_bounds", { deviceId });
            console.log("[AndroidMarkerOverlay] Got mirror window bounds:", bounds);
            setMirrorBounds(bounds);

            const win = getCurrentWindow();
            const pos = await win.outerPosition();
            preExtractPosition.current = { x: pos.x, y: pos.y };

            // Expand to full screen (more reliable on macOS for stacking/rendering)
            await win.setSize(new LogicalSize(window.screen.width, window.screen.height));
            await win.setPosition(new LogicalPosition(0, 0));
            await win.setAlwaysOnTop(true);
            await win.setIgnoreCursorEvents(false);

            // [FIX] Bring window to front
            await win.setFocus();

            // Notify main window to stop recording interaction events
            await emit("marking-started", {});

            setIsExtractMode(true);
        } catch (e) {
            console.error("[AndroidMarkerOverlay] Failed to expand window:", e);
            alert("无法检测到镜像窗口，或权限不足。请确保 scrcpy 窗口已打开并重启应用。");
        }
    }, [isExtractMode]);

    useEffect(() => {
        const handleKeyDown = async (e: KeyboardEvent) => {
            if (e.key === "Escape" && isExtractMode) {
                setIsExtractMode(false);
                setIsSelecting(false);
                setMirrorBounds(null);
                // Notify main window to resume recording interaction events
                await emit("marking-stopped", {});
                try {
                    const win = getCurrentWindow();
                    await win.setSize(new LogicalSize(64, 64));
                    if (preExtractPosition.current) {
                        await win.setPosition(new LogicalPosition(preExtractPosition.current.x, preExtractPosition.current.y));
                    }
                } catch (err) {
                    console.log("[AndroidMarkerOverlay] Failed to resize window:", err);
                }
            }
        };

        window.addEventListener("keydown", handleKeyDown);
        return () => window.removeEventListener("keydown", handleKeyDown);
    }, [isExtractMode]);

    const selectionStyle = () => {
        if (!isSelecting) return { opacity: 0 };

        const x = Math.min(selectionStart.x, selectionEnd.x);
        const y = Math.min(selectionStart.y, selectionEnd.y);
        const width = Math.abs(selectionEnd.x - selectionStart.x);
        const height = Math.abs(selectionEnd.y - selectionStart.y);

        return {
            left: x,
            top: y,
            width,
            height,
            opacity: 1,
        };
    };

    // Crosshair lines style - relative to mirror window
    const crosshairHStyle = {
        left: 0,
        right: 0,
        top: currentMousePos.y,
        height: 1,
    };
    const crosshairVStyle = {
        top: 0,
        bottom: 0,
        left: currentMousePos.x,
        width: 1,
    };

    // Get window-relative mouse position for the center dot
    const centerDotStyle = {
        left: currentMousePos.x,
        top: currentMousePos.y,
    };

    return (
        <AnimatePresence>
            {isExtractMode ? (
                <motion.div
                    key="android-extract-mode"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    ref={containerRef}
                    className="w-screen h-screen relative cursor-crosshair bg-white/1"
                    onMouseDown={handleMouseDown}
                >
                    {/* Mirror area darkening (optional, only covers the scrcpy bounds) */}
                    {mirrorBounds && (
                        <div
                            className="absolute bg-black/20 pointer-events-none"
                            style={{
                                left: mirrorBounds.x,
                                top: mirrorBounds.y,
                                width: mirrorBounds.width,
                                height: mirrorBounds.height
                            }}
                        />
                    )}

                    {/* Subtle global gradient */}
                    <div className="absolute inset-0 bg-gradient-to-br from-purple-900/5 to-pink-900/5 pointer-events-none" />

                    {/* Crosshair lines following cursor */}
                    {!isSelecting && (
                        <>
                            <div
                                className="absolute bg-purple-400/60 pointer-events-none z-30"
                                style={crosshairHStyle}
                            />
                            <div
                                className="absolute bg-purple-400/60 pointer-events-none z-30"
                                style={crosshairVStyle}
                            />
                            {/* Center dot */}
                            <div
                                className="absolute w-2 h-2 bg-purple-500 rounded-full pointer-events-none z-30 -translate-x-1/2 -translate-y-1/2 shadow-lg shadow-purple-500/50"
                                style={centerDotStyle}
                            />
                        </>
                    )}

                    {/* Scanning background effect */}
                    <div className="absolute inset-0 pointer-events-none overflow-hidden opacity-30">
                        <motion.div
                            animate={{ y: ["-10%", "110%"] }}
                            transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
                            className="w-full h-0.5 bg-gradient-to-r from-transparent via-purple-400 to-transparent blur-sm"
                        />
                    </div>

                    {/* Instruction Pill - More prominent */}
                    <motion.div
                        initial={{ y: -50, opacity: 0 }}
                        animate={{ y: 32, opacity: 1 }}
                        className="absolute left-1/2 -translate-x-1/2 flex items-center gap-3 bg-slate-900/90 backdrop-blur-xl border border-purple-500/30 px-6 py-3 rounded-2xl shadow-2xl z-50 text-white"
                    >
                        <Crosshair className="w-5 h-5 text-purple-400" />
                        <span className="text-sm font-semibold tracking-wide">拖拽选择区域</span>
                        <div className="h-4 w-[1px] bg-white/20 mx-1" />
                        <span className="text-xs text-white/60 font-mono bg-white/10 px-2 py-0.5 rounded">ESC 取消</span>
                    </motion.div>

                    {/* Selection preview - Much more visible */}
                    <motion.div
                        className="absolute border-2 border-purple-500 bg-purple-500/25 z-40 shadow-[0_0_30px_rgba(168,85,247,0.5)] rounded-lg"
                        style={selectionStyle()}
                    >
                        {/* Selection dimensions label */}
                        {isSelecting && (
                            <div className="absolute -top-8 left-0 bg-purple-500 text-white text-xs font-bold px-2 py-1 rounded shadow-lg whitespace-nowrap">
                                {Math.abs(selectionEnd.x - selectionStart.x)} × {Math.abs(selectionEnd.y - selectionStart.y)}
                            </div>
                        )}
                    </motion.div>

                    {/* Corner markers for selection */}
                    {isSelecting && (
                        <>
                            <div className="absolute w-4 h-4 border-l-2 border-t-2 border-purple-500 z-50" style={{ left: Math.min(selectionStart.x, selectionEnd.x) - 2, top: Math.min(selectionStart.y, selectionEnd.y) - 2 }} />
                            <div className="absolute w-4 h-4 border-r-2 border-t-2 border-purple-500 z-50" style={{ left: Math.max(selectionStart.x, selectionEnd.x) - 14, top: Math.min(selectionStart.y, selectionEnd.y) - 2 }} />
                            <div className="absolute w-4 h-4 border-l-2 border-b-2 border-purple-500 z-50" style={{ left: Math.min(selectionStart.x, selectionEnd.x) - 2, top: Math.max(selectionStart.y, selectionEnd.y) - 14 }} />
                            <div className="absolute w-4 h-4 border-r-2 border-b-2 border-purple-500 z-50" style={{ left: Math.max(selectionStart.x, selectionEnd.x) - 14, top: Math.max(selectionStart.y, selectionEnd.y) - 14 }} />
                        </>
                    )}

                    {/* Exit button */}
                    <motion.div
                        whileHover={{ scale: 1.1 }}
                        whileTap={{ scale: 0.9 }}
                        className="absolute bottom-12 right-12 z-50"
                    >
                        <button
                            onClick={handleClick}
                            className="h-14 w-14 rounded-full bg-red-500 text-white shadow-2xl border-2 border-white/30 flex items-center justify-center hover:bg-red-600 transition-colors"
                        >
                            <X className="w-6 h-6" />
                        </button>
                    </motion.div>

                    {/* Stats */}
                    {extractRegions.length > 0 && (
                        <motion.div
                            initial={{ x: 50, opacity: 0 }}
                            animate={{ x: 0, opacity: 1 }}
                            className="absolute top-8 right-8 z-50 bg-slate-900/90 backdrop-blur-xl border border-purple-500/30 rounded-2xl shadow-2xl p-4 text-white"
                        >
                            <div className="flex items-center gap-3">
                                <div className="h-10 w-10 rounded-full bg-purple-500/20 flex items-center justify-center border-2 border-purple-500/40">
                                    <Check className="h-5 w-5 text-purple-400" />
                                </div>
                                <div>
                                    <div className="text-xs text-white/50 uppercase tracking-widest font-bold">Android</div>
                                    <div className="text-xl font-bold">{extractRegions.length} 个区域</div>
                                </div>
                            </div>
                        </motion.div>
                    )}

                    {/* Help text at bottom */}
                    <div className="absolute bottom-8 left-1/2 -translate-x-1/2 text-white/60 text-sm font-medium bg-black/40 backdrop-blur-sm px-4 py-2 rounded-full">
                        按住鼠标拖拽选择区域，松开完成标记
                    </div>
                </motion.div>
            ) : (
                <motion.div
                    key="android-floating-ball"
                    initial={{ scale: 0, opacity: 0 }}
                    animate={{ scale: 1, opacity: 1 }}
                    exit={{ scale: 0, opacity: 0 }}
                    whileHover={{ scale: 1.05 }}
                    className="w-full h-full flex items-center justify-center select-none overflow-visible group"
                    onMouseDown={handleMouseDown}
                    onClick={handleClick}
                >
                    <div
                        className="w-14 h-14 rounded-full flex items-center justify-center relative shadow-2xl transition-all duration-300 active:scale-95 border-2 border-white/50"
                        style={{
                            background: "linear-gradient(135deg, rgba(255,255,255,0.98) 0%, rgba(245,240,255,0.95) 100%)",
                            backdropFilter: "blur(12px)",
                            boxShadow: "0 8px 32px rgba(0,0,0,0.2), 0 0 0 1px rgba(255,255,255,0.5) inset",
                        }}
                    >
                        <Pin className="w-6 h-6 text-slate-700 transition-transform group-hover:rotate-12" />

                        {/* Inner glowing ring */}
                        <div className="absolute inset-0 rounded-full border-2 border-purple-400/30 group-hover:border-purple-400/60 animate-pulse pointer-events-none" />

                        {/* Region count badge */}
                        {extractRegions.length > 0 && (
                            <motion.div
                                initial={{ scale: 0 }}
                                animate={{ scale: 1 }}
                                className="absolute -top-1 -right-1 h-6 w-6 bg-gradient-to-br from-purple-500 to-fuchsia-600 text-white text-[11px] font-bold rounded-full flex items-center justify-center border-2 border-white shadow-lg shadow-purple-500/30"
                            >
                                {extractRegions.length}
                            </motion.div>
                        )}
                    </div>
                </motion.div>
            )}
        </AnimatePresence>
    );
}
