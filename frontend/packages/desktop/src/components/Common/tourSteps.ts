import type { TourStep } from "@/components/Common/SpotlightTour"

/**
 * Desktop Onboarding Tour Steps
 * These steps guide new users through the core EvoLoop features
 */
export const desktopTourSteps: TourStep[] = [
    // Step 1: Welcome - Logo
    {
        target: '[data-tour="sidebar-logo"]',
        titleKey: "tour.step1.title",
        contentKey: "tour.step1.content",
        placement: "right",
        spotlightPadding: 12,
    },
    // Step 2: Chat - Main interaction
    {
        target: '[data-tour="sidebar-chat"]',
        titleKey: "tour.step2.title",
        contentKey: "tour.step2.content",
        placement: "right",
        spotlightPadding: 8,
    },
    // Step 3: Projects - Code management
    {
        target: '[data-tour="sidebar-projects"]',
        titleKey: "tour.step3.title",
        contentKey: "tour.step3.content",
        placement: "right",
        spotlightPadding: 8,
    },
    // Step 4: MCP - Extensions
    {
        target: '[data-tour="sidebar-mcp"]',
        titleKey: "tour.step4.title",
        contentKey: "tour.step4.content",
        placement: "right",
        spotlightPadding: 8,
    },
    // Step 5: Settings - Configuration
    {
        target: '[data-tour="sidebar-settings"]',
        titleKey: "tour.step5.title",
        contentKey: "tour.step5.content",
        placement: "right",
        spotlightPadding: 8,
    },
    // Step 6: Chat Interface - Sidebar
    {
        target: '[data-tour="chat-sidebar"]',
        titleKey: "tour.step6.title",
        contentKey: "tour.step6.content",
        placement: "right",
        spotlightPadding: 8,
    },
    // Step 7: Chat Interface - Message Area
    {
        target: '[data-tour="chat-messages"]',
        titleKey: "tour.step7.title",
        contentKey: "tour.step7.content",
        placement: "bottom",
        spotlightPadding: 12,
    },
    // Step 8: Chat Interface - Context Panel
    {
        target: '[data-tour="chat-context"]',
        titleKey: "tour.step8.title",
        contentKey: "tour.step8.content",
        placement: "left",
        spotlightPadding: 8,
    },
    // Step 9: Chat Input - Action area
    {
        target: '[data-tour="chat-input"]',
        titleKey: "tour.step9.title",
        contentKey: "tour.step9.content",
        placement: "top",
        spotlightPadding: 12,
    },
]
