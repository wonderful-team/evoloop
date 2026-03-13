import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState, useCallback, useRef } from "react";
import { Pin, Check, X, MousePointer2, Crosshair } from "lucide-react";
import { emit, listen, UnlistenFn } from "@tauri-apps/api/event";
import { getCurrentWindow, LogicalSize, LogicalPosition } from "@tauri-apps/api/window";
import { motion, AnimatePresence } from "framer-motion";
import { LearningService } from "@/client/sdk.gen";

export const Route = createFileRoute("/marker-overlay")({
    component: MarkerOverlay,
});

interface ExtractRegion {
    id: string;
    timestamp: number;
    x: number;
    y: number;
    width: number;
    height: number;
}

function MarkerOverlay() {
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

    // Listen for session info from main window
    const sessionIdRef = useRef<string | null>(null);
    const recordingStartTimeRef = useRef<number | null>(null);
    const threadIdRef = useRef<string | null>(null);

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
                console.log("[MarkerOverlay] Failed to set initial position", e);
            }
        };
        initPosition();
    }, []);

    useEffect(() => {
        let unlisten: UnlistenFn | undefined;

        const setupListener = async () => {
            unlisten = await listen<{ sessionId: string, recordingStartTime: number | null, threadId: string | null }>(
                "desktop-marker-session",
                (event) => {
                    sessionIdRef.current = event.payload.sessionId;
                    recordingStartTimeRef.current = event.payload.recordingStartTime;
                    threadIdRef.current = event.payload.threadId;
                    console.log("[MarkerOverlay] Session info received:", event.payload);
                }
            );
        };

        setupListener();

        return () => {
            if (unlisten) unlisten();
        };
    }, []);

    // Track mouse position for crosshair
    const handleMouseMove = useCallback((e: MouseEvent) => {
        setCurrentMousePos({ x: e.clientX, y: e.clientY });
        if (isSelecting) {
            setSelectionEnd({ x: e.clientX, y: e.clientY });
        }
    }, [isSelecting]);

    // Handle window dragging
    const handleMouseDown = useCallback(async (e: React.MouseEvent) => {
        if (isExtractMode) {
            e.preventDefault();
            e.stopPropagation();
            setIsSelecting(true);
            setSelectionStart({ x: e.clientX, y: e.clientY });
            setSelectionEnd({ x: e.clientX, y: e.clientY });
            return;
        }

        // Use Tauri's native dragging for smooth, jitter-free OS-level window movement
        try {
            const win = getCurrentWindow();
            await win.startDragging();
        } catch (err) {
            console.log("[MarkerOverlay] Failed to start dragging:", err);
        }
    }, [isExtractMode]);

    const handleMouseUp = useCallback(async () => {
        if (isSelecting) {
            setIsSelecting(false);

            const screenWidth = window.screen.width;
            const screenHeight = window.screen.height;

            const x1 = Math.min(selectionStart.x, selectionEnd.x);
            const y1 = Math.min(selectionStart.y, selectionEnd.y);
            const x2 = Math.max(selectionStart.x, selectionEnd.x);
            const y2 = Math.max(selectionStart.y, selectionEnd.y);

            const isPointClick = x2 - x1 < 10 || y2 - y1 < 10;
            const startTime = recordingStartTimeRef.current;
            const relativeTimestamp = startTime ? Date.now() - startTime : 0;

            const region: ExtractRegion = {
                id: `extract_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
                timestamp: relativeTimestamp,
                x: x1 / screenWidth,
                y: y1 / screenHeight,
                width: isPointClick ? 0.02 : (x2 - x1) / screenWidth,
                height: isPointClick ? 0.02 : (y2 - y1) / screenHeight,
            };

            setExtractRegions((prev) => [...prev, region]);
            await saveRegionToBackend(region);

            setIsExtractMode(false);
            try {
                const win = getCurrentWindow();
                await win.setSize(new LogicalSize(64, 64));
                if (preExtractPosition.current) {
                    await win.setPosition(new LogicalPosition(preExtractPosition.current.x, preExtractPosition.current.y));
                }
            } catch (e) {
                console.log("[MarkerOverlay] Failed to resize window:", e);
            }

            // Notify main window to resume recording interaction events
            await emit("marking-stopped", {});

            return;
        }
    }, [isSelecting, selectionStart, selectionEnd]);

    const saveRegionToBackend = async (region: ExtractRegion) => {
        const sessionId = sessionIdRef.current;
        const threadId = threadIdRef.current;

        if (!sessionId || !threadId) {
            console.error("[MarkerOverlay] No session ID or thread ID available");
            return;
        }

        try {
            // [Scheme A] Save region_extract event to TraceEvent table instead of annotations
            await LearningService.persistDomEvents({
                requestBody: {
                    session_id: sessionId,
                    thread_id: threadId,
                    events: [{
                        timestamp: region.timestamp,
                        event_type: "region_extract",
                        selector: `screen://${region.x.toFixed(4)}/${region.y.toFixed(4)}`,
                        target_text: "Screen region extraction",
                        coordinates: {
                            x: region.x,
                            y: region.y,
                            width: region.width,
                            height: region.height,
                        },
                    }]
                }
            });

            await emit("desktop-region-marked", { region });
            console.log("[MarkerOverlay] Region extract event saved to TraceEvent:", region);
        } catch (error) {
            console.error("[MarkerOverlay] Failed to save region extract event:", error);
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
            try {
                const win = getCurrentWindow();
                await win.setSize(new LogicalSize(64, 64));
                if (preExtractPosition.current) {
                    await win.setPosition(new LogicalPosition(preExtractPosition.current.x, preExtractPosition.current.y));
                }
            } catch (e) {
                console.log("[MarkerOverlay] Failed to resize window:", e);
            }
            // Notify main window to resume recording interaction events
            await emit("marking-stopped", {});
            return;
        }

        setIsExtractMode(true);
        try {
            const win = getCurrentWindow();
            const pos = await win.outerPosition();
            preExtractPosition.current = { x: pos.x, y: pos.y };

            await win.setSize(new LogicalSize(window.screen.width, window.screen.height));
            await win.setPosition(new LogicalPosition(0, 0));
            await win.setIgnoreCursorEvents(false);

            // [FIX] Bring window to front
            await win.setFocus();

            // Notify main window to stop recording interaction events
            await emit("marking-started", {});
        } catch (e) {
            console.log("[MarkerOverlay] Failed to expand window:", e);
        }
    }, [isExtractMode]);

    useEffect(() => {
        const handleKeyDown = async (e: KeyboardEvent) => {
            if (e.key === "Escape" && isExtractMode) {
                setIsExtractMode(false);
                setIsSelecting(false);
                try {
                    const win = getCurrentWindow();
                    await win.setSize(new LogicalSize(64, 64));
                    if (preExtractPosition.current) {
                        await win.setPosition(new LogicalPosition(preExtractPosition.current.x, preExtractPosition.current.y));
                    }
                } catch (err) {
                    console.log("[MarkerOverlay] Failed to resize window:", err);
                }
                // Notify main window to resume recording interaction events
                await emit("marking-stopped", {});
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

    // Crosshair lines style
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

    return (
        <AnimatePresence>
            {isExtractMode ? (
                <motion.div
                    key="extract-mode"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    ref={containerRef}
                    className="w-screen h-screen relative cursor-crosshair"
                    style={{ backgroundColor: "rgba(0, 0, 0, 0.15)" }}
                    onMouseDown={handleMouseDown}
                >
                    {/* Subtle darkening overlay */}
                    <div className="absolute inset-0 bg-gradient-to-br from-blue-900/10 to-purple-900/10 pointer-events-none" />

                    {/* Crosshair lines following cursor */}
                    {!isSelecting && (
                        <>
                            <div
                                className="absolute bg-blue-400/60 pointer-events-none z-30"
                                style={crosshairHStyle}
                            />
                            <div
                                className="absolute bg-blue-400/60 pointer-events-none z-30"
                                style={crosshairVStyle}
                            />
                            {/* Center dot */}
                            <div
                                className="absolute w-2 h-2 bg-blue-500 rounded-full pointer-events-none z-30 -translate-x-1/2 -translate-y-1/2 shadow-lg shadow-blue-500/50"
                                style={{ left: currentMousePos.x, top: currentMousePos.y }}
                            />
                        </>
                    )}

                    {/* Scanning background effect */}
                    <div className="absolute inset-0 pointer-events-none overflow-hidden opacity-30">
                        <motion.div
                            animate={{ y: ["-10%", "110%"] }}
                            transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
                            className="w-full h-0.5 bg-gradient-to-r from-transparent via-blue-400 to-transparent blur-sm"
                        />
                    </div>

                    {/* Instruction Pill - More prominent */}
                    <motion.div
                        initial={{ y: -50, opacity: 0 }}
                        animate={{ y: 32, opacity: 1 }}
                        className="absolute left-1/2 -translate-x-1/2 flex items-center gap-3 bg-slate-900/90 backdrop-blur-xl border border-blue-500/30 px-6 py-3 rounded-2xl shadow-2xl z-50 text-white"
                    >
                        <Crosshair className="w-5 h-5 text-blue-400" />
                        <span className="text-sm font-semibold tracking-wide">拖拽选择区域</span>
                        <div className="h-4 w-[1px] bg-white/20 mx-1" />
                        <span className="text-xs text-white/60 font-mono bg-white/10 px-2 py-0.5 rounded">ESC 取消</span>
                    </motion.div>

                    {/* Selection preview - Much more visible */}
                    <motion.div
                        className="absolute border-2 border-blue-500 bg-blue-500/25 z-40 shadow-[0_0_30px_rgba(59,130,246,0.5)] rounded-lg"
                        style={selectionStyle()}
                    >
                        {/* Selection dimensions label */}
                        {isSelecting && (
                            <div className="absolute -top-8 left-0 bg-blue-500 text-white text-xs font-bold px-2 py-1 rounded shadow-lg whitespace-nowrap">
                                {Math.abs(selectionEnd.x - selectionStart.x)} × {Math.abs(selectionEnd.y - selectionStart.y)}
                            </div>
                        )}
                    </motion.div>

                    {/* Corner markers for selection */}
                    {isSelecting && (
                        <>
                            <div className="absolute w-4 h-4 border-l-2 border-t-2 border-blue-500 z-50" style={{ left: Math.min(selectionStart.x, selectionEnd.x) - 2, top: Math.min(selectionStart.y, selectionEnd.y) - 2 }} />
                            <div className="absolute w-4 h-4 border-r-2 border-t-2 border-blue-500 z-50" style={{ left: Math.max(selectionStart.x, selectionEnd.x) - 14, top: Math.min(selectionStart.y, selectionEnd.y) - 2 }} />
                            <div className="absolute w-4 h-4 border-l-2 border-b-2 border-blue-500 z-50" style={{ left: Math.min(selectionStart.x, selectionEnd.x) - 2, top: Math.max(selectionStart.y, selectionEnd.y) - 14 }} />
                            <div className="absolute w-4 h-4 border-r-2 border-b-2 border-blue-500 z-50" style={{ left: Math.max(selectionStart.x, selectionEnd.x) - 14, top: Math.max(selectionStart.y, selectionEnd.y) - 14 }} />
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
                            className="absolute top-8 right-8 z-50 bg-slate-900/90 backdrop-blur-xl border border-green-500/30 rounded-2xl shadow-2xl p-4 text-white"
                        >
                            <div className="flex items-center gap-3">
                                <div className="h-10 w-10 rounded-full bg-green-500/20 flex items-center justify-center border-2 border-green-500/40">
                                    <Check className="h-5 w-5 text-green-400" />
                                </div>
                                <div>
                                    <div className="text-xs text-white/50 uppercase tracking-widest font-bold">已标记</div>
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
                    key="floating-ball"
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
                            background: "linear-gradient(135deg, rgba(255,255,255,0.98) 0%, rgba(240,245,255,0.95) 100%)",
                            backdropFilter: "blur(12px)",
                            boxShadow: "0 8px 32px rgba(0,0,0,0.2), 0 0 0 1px rgba(255,255,255,0.5) inset",
                        }}
                    >
                        <Pin className="w-6 h-6 text-slate-700 transition-transform group-hover:rotate-12" />

                        {/* Inner glowing ring */}
                        <div className="absolute inset-0 rounded-full border-2 border-blue-400/30 group-hover:border-blue-400/60 animate-pulse pointer-events-none" />

                        {/* Region count badge */}
                        {extractRegions.length > 0 && (
                            <motion.div
                                initial={{ scale: 0 }}
                                animate={{ scale: 1 }}
                                className="absolute -top-1 -right-1 h-6 w-6 bg-gradient-to-br from-blue-500 to-indigo-600 text-white text-[11px] font-bold rounded-full flex items-center justify-center border-2 border-white shadow-lg shadow-blue-500/30"
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
