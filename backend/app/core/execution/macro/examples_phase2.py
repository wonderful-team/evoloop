"""
Phase 2 Examples: Strategy Adaptation Library

Demonstrates how to use the AdaptationStrategyLibrary for different anomaly types.
"""

import asyncio
from app.core.execution.macro import (
    AdaptationStrategyLibrary,
    AnomalyType,
    AgentMacroValidator,
    VerificationRequest,
    EnvironmentConfig,
)


async def example_quick_fix_coordinate_drift():
    """Example: Quick fix for coordinate drift"""

    library = AdaptationStrategyLibrary(use_llm=False)  # Only quick fixes

    # Original step with coordinates
    step = {
        "step_number": 3,
        "type": "action",
        "event_type": "tap",
        "source": "mobile",
        "target_selector": "登录按钮",
        "payload": {"x": 540, "y": 1200}
    }

    # Simulate detected drift
    anomaly_details = {
        "expected": {"x": 540, "y": 1200},
        "actual": {"x": 560, "y": 1180}  # Actual position found
    }

    # UI state with corrected element
    ui_state = {
        "platform": "android",
        "elements": [
            {"text": "登录按钮", "bounds": {"center_x": 560, "center_y": 1180}}
        ]
    }

    # Get adaptation
    record = await library.adapt(
        step=step,
        anomaly_type=AnomalyType.COORDINATE_DRIFT,
        anomaly_details=anomaly_details,
        ui_state=ui_state
    )

    print("Coordinate Drift Fix:")
    print(f"  Success: {record.success}")
    print(f"  Reasoning: {record.reasoning}")
    print(f"  New coordinates: {record.adapted_strategy.get('payload', {})}")


async def example_quick_fix_element_not_found():
    """Example: Quick fix for element not found"""

    library = AdaptationStrategyLibrary(use_llm=False)

    step = {
        "step_number": 2,
        "type": "action",
        "event_type": "click",
        "source": "dom",
        "target_selector": "#submit-btn",
        "payload": {"selector": "#submit-btn"}
    }

    anomaly_details = {"selector": "#submit-btn"}

    # UI has similar but different element
    ui_state = {
        "platform": "web",
        "elements": [
            {"text": "Submit", "class": "button submit-button", "id": "submit-btn-v2"},
            {"text": "Cancel", "class": "button"}
        ]
    }

    record = await library.adapt(
        step=step,
        anomaly_type=AnomalyType.ELEMENT_NOT_FOUND,
        anomaly_details=anomaly_details,
        ui_state=ui_state
    )

    print("\nElement Not Found Fix:")
    print(f"  Success: {record.success}")
    print(f"  Reasoning: {record.reasoning}")


async def example_llm_deep_adaptation():
    """Example: LLM-powered deep adaptation"""

    library = AdaptationStrategyLibrary(use_llm=True)

    step = {
        "step_number": 5,
        "type": "extract",
        "extract_type": "get_text",
        "key": "price_data",
        "source": "dom",
        "target_selector": ".price-value",
        "payload": {"selector": ".price-value"}
    }

    # Complex anomaly requiring reasoning
    anomaly_details = {
        "expected_selector": ".price-value",
        "found_selectors": [".price", ".current-price", ".discounted-price"],
        "page_changed": True
    }

    ui_state = {
        "platform": "web",
        "url": "https://example.com/product-v2",
        "elements": [
            {"text": "$99.99", "class": "current-price"},
            {"text": "$129.99", "class": "original-price"}
        ]
    }

    # This will use LLM for adaptation
    record = await library.adapt(
        step=step,
        anomaly_type=AnomalyType.STATE_MISMATCH,
        anomaly_details=anomaly_details,
        ui_state=ui_state,
        prefer_llm=True  # Skip quick fix, go straight to LLM
    )

    print("\nLLM Deep Adaptation:")
    print(f"  Success: {record.success}")
    print(f"  Reasoning: {record.reasoning[:200]}...")


async def example_fallback_adaptation():
    """Example: Multiple attempts with fallback"""

    library = AdaptationStrategyLibrary(use_llm=True)

    step = {
        "step_number": 1,
        "type": "action",
        "event_type": "click",
        "source": "dom",
        "target_selector": "#dynamic-btn",
        "payload": {"selector": "#dynamic-btn"}
    }

    anomaly_details = {"selector": "#dynamic-btn", "attempt": 1}
    ui_state = {"platform": "web", "elements": []}

    # Try multiple strategies
    records = await library.adapt_with_fallback(
        step=step,
        anomaly_type=AnomalyType.ELEMENT_NOT_FOUND,
        anomaly_details=anomaly_details,
        ui_state=ui_state,
        max_attempts=3
    )

    print(f"\nFallback Adaptation ({len(records)} attempts):")
    for i, record in enumerate(records, 1):
        print(f"  Attempt {i}: {record.success} - {record.reasoning[:80]}...")


async def example_integration_in_validator():
    """Example: How the validator uses the library internally"""

    # The AgentMacroValidator now automatically uses AdaptationStrategyLibrary
    # Here's how it's configured:

    request = VerificationRequest(
        macro_script=[
            {"step_number": 1, "type": "action", "event_type": "goto",
             "source": "dom", "payload": {"url": "https://example.com"}}
        ],
        target_environment=EnvironmentConfig(platform="web"),
        agent_config={
            "allow_strategy_adaptation": True,  # Enable LLM strategies
            "max_retries_per_step": 3,  # Max adaptation attempts
            "conservative_mode": False
        }
    )

    # The validator will:
    # 1. First try quick fixes (no LLM call, fast)
    # 2. If quick fix fails, escalate to LLM deep adaptation
    # 3. Track all adaptations for macro evolution

    print("\nValidator Integration:")
    print("  - Quick fixes applied automatically for common issues")
    print("  - LLM adaptation triggered when quick fixes fail")
    print("  - All adaptations recorded for macro evolution")


def print_strategy_descriptions():
    """Print descriptions of all available strategies"""

    library = AdaptationStrategyLibrary()

    print("\nAvailable Adaptation Strategies:")
    print("=" * 60)

    for anomaly_type in AnomalyType:
        description = library.get_strategy_description(anomaly_type)
        print(f"\n{anomaly_type.value}:")
        print(f"  {description}")


async def main():
    """Run all examples"""

    print("=" * 60)
    print("Phase 2: Strategy Adaptation Library Examples")
    print("=" * 60)

    # Run examples
    await example_quick_fix_coordinate_drift()
    await example_quick_fix_element_not_found()
    # await example_llm_deep_adaptation()  # Requires LLM
    # await example_fallback_adaptation()  # Requires LLM
    await example_integration_in_validator()

    print_strategy_descriptions()

    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
