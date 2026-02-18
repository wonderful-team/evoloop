import React from "react";
import { useTranslation } from "react-i18next";
import { Command as CommandPrimitive } from "cmdk";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
} from "@evoloop/shared/components/ui/dialog";
import {
    Smartphone,
    Monitor,
    Hourglass,
    MousePointer2,
    Keyboard,
    TouchpadOff,
    Home,
    Undo2,
    Search,
    Repeat,
    GitBranch,
    FolderTree
} from "lucide-react";
import { cn } from "@evoloop/shared/lib/utils";
import type { SkillStep } from "@/types/skill";

// --- Inline Command Components (shadcn/ui style) ---

const Command = React.forwardRef<
    React.ElementRef<typeof CommandPrimitive>,
    React.ComponentPropsWithoutRef<typeof CommandPrimitive>
>(({ className, ...props }, ref) => (
    <CommandPrimitive
        ref={ref}
        className={cn(
            "flex h-full w-full flex-col overflow-hidden rounded-md bg-popover text-popover-foreground",
            className
        )}
        {...props}
    />
))
Command.displayName = CommandPrimitive.displayName

const CommandInput = React.forwardRef<
    React.ElementRef<typeof CommandPrimitive.Input>,
    React.ComponentPropsWithoutRef<typeof CommandPrimitive.Input>
>(({ className, ...props }, ref) => (
    <div className="flex items-center border-b px-3" cmdk-input-wrapper="">
        <Search className="mr-2 h-4 w-4 shrink-0 opacity-50" />
        <CommandPrimitive.Input
            ref={ref}
            className={cn(
                "flex h-11 w-full rounded-md bg-transparent py-3 text-sm outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-50",
                className
            )}
            {...props}
        />
    </div>
))
CommandInput.displayName = CommandPrimitive.Input.displayName

const CommandList = React.forwardRef<
    React.ElementRef<typeof CommandPrimitive.List>,
    React.ComponentPropsWithoutRef<typeof CommandPrimitive.List>
>(({ className, ...props }, ref) => (
    <CommandPrimitive.List
        ref={ref}
        className={cn("max-h-[300px] overflow-y-auto overflow-x-hidden", className)}
        {...props}
    />
))
CommandList.displayName = CommandPrimitive.List.displayName

const CommandEmpty = React.forwardRef<
    React.ElementRef<typeof CommandPrimitive.Empty>,
    React.ComponentPropsWithoutRef<typeof CommandPrimitive.Empty>
>((props, ref) => (
    <CommandPrimitive.Empty
        ref={ref}
        className="py-6 text-center text-sm"
        {...props}
    />
))
CommandEmpty.displayName = CommandPrimitive.Empty.displayName

const CommandGroup = React.forwardRef<
    React.ElementRef<typeof CommandPrimitive.Group>,
    React.ComponentPropsWithoutRef<typeof CommandPrimitive.Group>
>(({ className, ...props }, ref) => (
    <CommandPrimitive.Group
        ref={ref}
        className={cn(
            "overflow-hidden p-1 text-foreground [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-muted-foreground",
            className
        )}
        {...props}
    />
))
CommandGroup.displayName = CommandPrimitive.Group.displayName

const CommandSeparator = React.forwardRef<
    React.ElementRef<typeof CommandPrimitive.Separator>,
    React.ComponentPropsWithoutRef<typeof CommandPrimitive.Separator>
>(({ className, ...props }, ref) => (
    <CommandPrimitive.Separator
        ref={ref}
        className={cn("-mx-1 h-px bg-border", className)}
        {...props}
    />
))
CommandSeparator.displayName = CommandPrimitive.Separator.displayName

const CommandItem = React.forwardRef<
    React.ElementRef<typeof CommandPrimitive.Item>,
    React.ComponentPropsWithoutRef<typeof CommandPrimitive.Item>
>(({ className, ...props }, ref) => (
    <CommandPrimitive.Item
        ref={ref}
        className={cn(
            "relative flex cursor-default select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none aria-selected:bg-accent aria-selected:text-accent-foreground data-[disabled='true']:pointer-events-none data-[disabled='true']:opacity-50",
            className
        )}
        {...props}
    />
))
CommandItem.displayName = CommandPrimitive.Item.displayName


// --- Component Implementation ---

interface StepActionSelectorProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onSelect: (step: SkillStep) => void;
}

interface ActionDefinition {
    id: string;
    icon: React.ReactNode;
    label: string;
    description: string;
    baseStep: SkillStep;
}

export const StepActionSelector: React.FC<StepActionSelectorProps> = ({
    open,
    onOpenChange,
    onSelect,
}) => {
    const { t } = useTranslation();

    const actions: Record<string, ActionDefinition[]> = {
        mobile: [
            {
                id: "mobile_tap",
                icon: <MousePointer2 className="h-4 w-4" />,
                label: t("learning.actions.mobile.tap", "Tap"),
                description: t("learning.actions.mobile.tapDesc", "Tap at specific coordinates"),
                baseStep: {
                    action: "mobile_control",
                    args: { action: "tap", x: 500, y: 1000 }
                }
            },
            {
                id: "mobile_text",
                icon: <Keyboard className="h-4 w-4" />,
                label: t("learning.actions.mobile.input_text", "Input Text"),
                description: t("learning.actions.mobile.textDesc", "Type text into a field"),
                baseStep: {
                    action: "mobile_control",
                    args: { action: "input_text", text: "" }
                }
            },
            {
                id: "mobile_swipe",
                icon: <TouchpadOff className="h-4 w-4" />,
                label: t("learning.actions.mobile.swipe", "Swipe"),
                description: t("learning.actions.mobile.swipeDesc", "Swipe gestures"),
                baseStep: {
                    action: "mobile_control",
                    args: { action: "swipe", x1: 500, y1: 1500, x2: 500, y2: 500, duration: 500 }
                }
            },
            {
                id: "mobile_home",
                icon: <Home className="h-4 w-4" />,
                label: t("learning.actions.mobile.home", "Home"),
                description: t("learning.actions.mobile.homeDesc", "Go to home screen"),
                baseStep: {
                    action: "mobile_control",
                    args: { action: "press_key", keycode: "home" }
                }
            },
            {
                id: "mobile_back",
                icon: <Undo2 className="h-4 w-4" />,
                label: t("learning.actions.mobile.back", "Back"),
                description: t("learning.actions.mobile.backDesc", "Go back"),
                baseStep: {
                    action: "mobile_control",
                    args: { action: "press_key", keycode: "back" }
                }
            },
            {
                id: "mobile_open_app",
                icon: <Smartphone className="h-4 w-4" />,
                label: t("learning.actions.mobile.open_app", "Open App"),
                description: t("learning.actions.mobile.openAppDesc", "Open an app by package name"),
                baseStep: {
                    action: "mobile_control",
                    args: { action: "open_app", text: "com.example.app" }
                }
            },
            {
                id: "mobile_key_press",
                icon: <Keyboard className="h-4 w-4" />,
                label: t("learning.actions.mobile.press_key", "Press Key"),
                description: t("learning.actions.mobile.pressKeyDesc", "Press a physical button"),
                baseStep: {
                    action: "mobile_control",
                    args: { action: "press_key", keycode: "enter" }
                }
            },
            {
                id: "mobile_screenshot",
                icon: <Monitor className="h-4 w-4" />,
                label: t("learning.actions.mobile.screenshot", "Screenshot"),
                description: t("learning.actions.mobile.screenshotDesc", "Capture screen"),
                baseStep: {
                    action: "mobile_control",
                    args: { action: "screenshot" }
                }
            }
        ],
        desktop: [
            {
                id: "desktop_click",
                icon: <MousePointer2 className="h-4 w-4" />,
                label: t("learning.actions.desktop.click", "Click"),
                description: t("learning.actions.desktop.clickDesc", "Mouse click"),
                baseStep: {
                    action: "desktop_control",
                    args: { action: "click", x: 0, y: 0 }
                }
            },
            {
                id: "desktop_double_click",
                icon: <MousePointer2 className="h-4 w-4" />,
                label: t("learning.actions.desktop.double_click", "Double Click"),
                description: t("learning.actions.desktop.doubleClickDesc", "Mouse double click"),
                baseStep: {
                    action: "desktop_control",
                    args: { action: "double_click", x: 0, y: 0 }
                }
            },
            {
                id: "desktop_type",
                icon: <Keyboard className="h-4 w-4" />,
                label: t("learning.actions.desktop.type_text", "Type Text"),
                description: t("learning.actions.desktop.typeDesc", "Keyboard input"),
                baseStep: {
                    action: "desktop_control",
                    args: { action: "type_text", text: "" }
                }
            },
            {
                id: "desktop_key_press",
                icon: <Keyboard className="h-4 w-4" />,
                label: t("learning.actions.desktop.key_press", "Key Press"),
                description: t("learning.actions.desktop.keyPressDesc", "Press a keyboard key"),
                baseStep: {
                    action: "desktop_control",
                    args: { action: "key_press", key: "enter" }
                }
            },
            {
                id: "desktop_open_app",
                icon: <Monitor className="h-4 w-4" />,
                label: t("learning.actions.desktop.open_app", "Open App"),
                description: t("learning.actions.desktop.openAppDesc", "Open an application"),
                baseStep: {
                    action: "desktop_control",
                    args: { action: "open_app", app_name: "Safari" }
                }
            },
            {
                id: "desktop_screenshot",
                icon: <Monitor className="h-4 w-4" />,
                label: t("learning.actions.desktop.screenshot", "Screenshot"),
                description: t("learning.actions.desktop.screenshotDesc", "Capture screen"),
                baseStep: {
                    action: "desktop_control",
                    args: { action: "screenshot" }
                }
            }
        ],
        logic: [
            {
                id: "wait",
                icon: <Hourglass className="h-4 w-4" />,
                label: t("learning.actions.wait", "Wait"),
                description: t("learning.actions.waitDesc", "Pause execution"),
                baseStep: {
                    action: "wait",
                    args: { duration: 1000 }
                }
            },
            {
                id: "loop",
                icon: <Repeat className="h-4 w-4" />,
                label: t("learning.actions.loop", "Loop"),
                description: t("learning.actions.loopDesc", "Repeat steps multiple times"),
                baseStep: {
                    action: "loop",
                    args: { count: 3 },
                    children: []
                }
            },
            {
                id: "condition",
                icon: <GitBranch className="h-4 w-4" />,
                label: t("learning.actions.condition", "Condition"),
                description: t("learning.actions.conditionDesc", "If/Else branching logic"),
                baseStep: {
                    action: "condition",
                    args: { if: "True" },
                    children: []
                }
            },
            {
                id: "group",
                icon: <FolderTree className="h-4 w-4" />,
                label: t("learning.actions.group", "Group"),
                description: t("learning.actions.groupDesc", "Container for steps"),
                baseStep: {
                    action: "group",
                    args: {},
                    children: []
                }
            },
            {
                id: "instruction",
                icon: <Search className="h-4 w-4" />,
                label: t("learning.actions.instruction", "Instruction"),
                description: t("learning.actions.instructionDesc", "Natural language instruction"),
                baseStep: {
                    action: "natural_language_instruction",
                    args: { instruction: "Describe what to do..." }
                }
            }
        ]
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="p-0 gap-0 max-w-[500px] bg-background shadow-2xl border-border">
                <DialogHeader className="p-4 pb-2 border-b">
                    <DialogTitle className="text-sm font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
                        <Search className="h-4 w-4 text-primary" />
                        {t("learning.selector.title", "Select Action")}
                    </DialogTitle>
                </DialogHeader>
                <Command className="rounded-xl border-0">
                    <CommandInput
                        placeholder={t("learning.selector.searchPlaceholder", "Search implementation actions...")}
                        className="border-0 focus:ring-0 text-sm h-11"
                    />
                    <CommandList className="max-h-[400px] overflow-y-auto custom-scrollbar p-2">
                        <CommandEmpty className="py-6 text-center text-xs text-muted-foreground">
                            {t("learning.selector.noResults", "No actions found.")}
                        </CommandEmpty>

                        <div className="space-y-1">
                            <div className="px-2 py-1.5 text-[10px] font-bold uppercase text-muted-foreground/50 tracking-wider flex items-center gap-1.5">
                                <Smartphone className="h-3 w-3" />
                                {t("learning.categories.mobile", "Mobile Interaction")}
                            </div>
                            <CommandGroup>
                                {actions.mobile.map((action) => (
                                    <CommandItem
                                        key={action.id}
                                        value={action.label + " " + action.description}
                                        onSelect={() => {
                                            onSelect(action.baseStep);
                                            onOpenChange(false);
                                        }}
                                        className="flex items-center gap-3 p-2 rounded-lg cursor-pointer aria-selected:bg-primary/10 aria-selected:text-primary transition-all group"
                                    >
                                        <div className="flex h-8 w-8 items-center justify-center rounded-md border bg-background text-muted-foreground group-aria-selected:border-primary/20 group-aria-selected:text-primary transition-colors">
                                            {action.icon}
                                        </div>
                                        <div className="flex flex-col gap-0.5">
                                            <span className="text-xs font-bold">{action.label}</span>
                                            <span className="text-[10px] text-muted-foreground group-aria-selected:text-primary/70">{action.description}</span>
                                        </div>
                                    </CommandItem>
                                ))}
                            </CommandGroup>
                        </div>

                        <CommandSeparator className="my-2" />

                        <div className="space-y-1">
                            <div className="px-2 py-1.5 text-[10px] font-bold uppercase text-muted-foreground/50 tracking-wider flex items-center gap-1.5">
                                <Monitor className="h-3 w-3" />
                                {t("learning.categories.desktop", "Desktop Interaction")}
                            </div>
                            <CommandGroup>
                                {actions.desktop.map((action) => (
                                    <CommandItem
                                        key={action.id}
                                        value={action.label + " " + action.description}
                                        onSelect={() => {
                                            onSelect(action.baseStep);
                                            onOpenChange(false);
                                        }}
                                        className="flex items-center gap-3 p-2 rounded-lg cursor-pointer aria-selected:bg-primary/10 aria-selected:text-primary transition-all group"
                                    >
                                        <div className="flex h-8 w-8 items-center justify-center rounded-md border bg-background text-muted-foreground group-aria-selected:border-primary/20 group-aria-selected:text-primary transition-colors">
                                            {action.icon}
                                        </div>
                                        <div className="flex flex-col gap-0.5">
                                            <span className="text-xs font-bold">{action.label}</span>
                                            <span className="text-[10px] text-muted-foreground group-aria-selected:text-primary/70">{action.description}</span>
                                        </div>
                                    </CommandItem>
                                ))}
                            </CommandGroup>
                        </div>

                        <CommandSeparator className="my-2" />

                        <div className="space-y-1">
                            <div className="px-2 py-1.5 text-[10px] font-bold uppercase text-muted-foreground/50 tracking-wider flex items-center gap-1.5">
                                <Hourglass className="h-3 w-3" />
                                {t("learning.categories.logic", "Logic Control")}
                            </div>
                            <CommandGroup>
                                {actions.logic.map((action) => (
                                    <CommandItem
                                        key={action.id}
                                        value={action.label + " " + action.description}
                                        onSelect={() => {
                                            onSelect(action.baseStep);
                                            onOpenChange(false);
                                        }}
                                        className="flex items-center gap-3 p-2 rounded-lg cursor-pointer aria-selected:bg-primary/10 aria-selected:text-primary transition-all group"
                                    >
                                        <div className="flex h-8 w-8 items-center justify-center rounded-md border bg-background text-muted-foreground group-aria-selected:border-primary/20 group-aria-selected:text-primary transition-colors">
                                            {action.icon}
                                        </div>
                                        <div className="flex flex-col gap-0.5">
                                            <span className="text-xs font-bold">{action.label}</span>
                                            <span className="text-[10px] text-muted-foreground group-aria-selected:text-primary/70">{action.description}</span>
                                        </div>
                                    </CommandItem>
                                ))}
                            </CommandGroup>
                        </div>
                    </CommandList>
                </Command>
            </DialogContent>
        </Dialog>
    );
};
