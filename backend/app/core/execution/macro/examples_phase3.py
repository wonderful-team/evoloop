"""
Phase 3 Examples: Macro Evolution Engine

Demonstrates how the MacroEvolutionEngine transforms macros
based on verification results and adaptations.
"""

from app.core.execution.macro.evolution_engine import (
    CoordinateDriftTransformer,
    ElementNotFoundTransformer,
    ElementObscuredTransformer,
    EvolutionOptimizer,
    LoadingTimeoutTransformer,
    MacroEvolutionEngine,
    StateMismatchTransformer,
    EvolutionContext,
)
from app.core.execution.macro.verification_models import (
    MacroEvolutionRecord,
    StepResult,
    StepExecutionStatus,
    AnomalyType,
)


def example_coordinate_drift_evolution():
    """Example: Transform coordinate-based steps to be more robust"""

    print("=" * 60)
    print("Phase 3: Coordinate Drift Evolution")
    print("=" * 60)

    # Original step with fixed coordinates
    original_step = {
        "step_number": 3,
        "type": "action",
        "event_type": "tap",
        "source": "mobile",
        "target_selector": "登录按钮",
        "payload": {"x": 540, "y": 1200}
    }

    # Evolution record from verification
    record = MacroEvolutionRecord(
        original_step=original_step,
        evolved_step=original_step,  # Will be transformed
        evolution_reason="Phase 2: coordinate_drift - Updated to use element selector",
        confidence=0.85
    )

    # Create context
    context = EvolutionContext(
        original_macro=[original_step],
        step_results=[],
        evolution_records=[record],
        target_platform="android"
    )

    # Apply transformer
    transformer = CoordinateDriftTransformer()
    evolved_steps = transformer.transform(original_step, record, context)

    print("\nOriginal Step:")
    print(f"  {original_step}")

    print("\nEvolved Step:")
    for step in evolved_steps:
        print(f"  {step}")

    print("\nKey Improvements:")
    print("  - Added retry mechanism (3 retries, 500ms interval)")
    print("  - Added fallback to coordinates if selector fails")
    print("  - Added element existence precondition")


def example_element_not_found_evolution():
    """Example: Add selector chain for element not found issues"""

    print("\n" + "=" * 60)
    print("Phase 3: Element Not Found Evolution")
    print("=" * 60)

    original_step = {
        "step_number": 2,
        "type": "action",
        "event_type": "click",
        "source": "dom",
        "target_selector": "#submit-btn",
        "payload": {"selector": "#submit-btn"}
    }

    record = MacroEvolutionRecord(
        original_step=original_step,
        evolved_step=original_step,
        evolution_reason="Phase 2: element_not_found - Try alternative selectors",
        confidence=0.80
    )

    context = EvolutionContext(
        original_macro=[original_step],
        step_results=[],
        evolution_records=[record],
        target_platform="web"
    )

    transformer = ElementNotFoundTransformer()
    evolved_steps = transformer.transform(original_step, record, context)

    print("\nOriginal Step:")
    print(f"  Selector: #submit-btn")

    print("\nEvolved Step:")
    evolved = evolved_steps[0]
    print(f"  Selector chain: {evolved['payload'].get('selector_chain', [])}")
    print(f"  Scroll to find: {evolved['payload'].get('scroll_to_find', {})}")
    print(f"  Strategy: {evolved['payload'].get('selector_strategy')}")


def example_element_obscured_evolution():
    """Example: Add popup dismissal for obscured elements"""

    print("\n" + "=" * 60)
    print("Phase 3: Element Obscured Evolution")
    print("=" * 60)

    original_step = {
        "step_number": 5,
        "type": "action",
        "event_type": "click",
        "source": "dom",
        "target_selector": "#menu-button",
        "payload": {"selector": "#menu-button"}
    }

    record = MacroEvolutionRecord(
        original_step=original_step,
        evolved_step=original_step,
        evolution_reason="Phase 2: element_obscured - Dismiss popup before clicking",
        confidence=0.90
    )

    context = EvolutionContext(
        original_macro=[original_step],
        step_results=[],
        evolution_records=[record],
        target_platform="web"
    )

    transformer = ElementObscuredTransformer()
    evolved_steps = transformer.transform(original_step, record, context)

    print(f"\nOriginal: 1 step")
    print(f"Evolved: {len(evolved_steps)} steps\n")

    for i, step in enumerate(evolved_steps, 1):
        print(f"Step {i}: {step['event_type']}")
        if 'strategies' in step.get('payload', {}):
            print(f"  Strategies: {len(step['payload']['strategies'])} dismissal methods")


def example_full_macro_evolution():
    """Example: Full macro evolution with multiple issues"""

    print("\n" + "=" * 60)
    print("Phase 3: Full Macro Evolution")
    print("=" * 60)

    # Original macro with various potential issues
    original_macro = [
        {
            "step_number": 1,
            "type": "action",
            "event_type": "goto",
            "source": "dom",
            "payload": {"url": "https://example.com/login"}
        },
        {
            "step_number": 2,
            "type": "action",
            "event_type": "input",
            "source": "dom",
            "target_selector": "#username",
            "payload": {"selector": "#username", "text": "user@example.com"}
        },
        {
            "step_number": 3,
            "type": "action",
            "event_type": "tap",
            "source": "mobile",
            "target_selector": "登录",
            "payload": {"x": 540, "y": 1200}  # Coordinate drift issue
        },
        {
            "step_number": 4,
            "type": "action",
            "event_type": "click",
            "source": "dom",
            "target_selector": "#old-button-id",  # Element changed
            "payload": {"selector": "#old-button-id"}
        },
        {
            "step_number": 5,
            "type": "wait",
            "event_type": "wait",
            "source": "dom",
            "payload": {"duration_ms": 2000}
        }
    ]

    # Evolution records from verification
    evolution_records = [
        MacroEvolutionRecord(
            original_step=original_macro[2],
            evolved_step=original_macro[2],
            evolution_reason="Phase 2: coordinate_drift - Use selector instead",
            confidence=0.85
        ),
        MacroEvolutionRecord(
            original_step=original_macro[3],
            evolved_step=original_macro[3],
            evolution_reason="Phase 2: element_not_found - Add alternative selectors",
            confidence=0.75
        )
    ]

    # Step results
    step_results = [
        StepResult(step_number=1, status=StepExecutionStatus.PASSED),
        StepResult(step_number=2, status=StepExecutionStatus.PASSED),
        StepResult(step_number=3, status=StepExecutionStatus.ADAPTED),
        StepResult(step_number=4, status=StepExecutionStatus.ADAPTED),
        StepResult(step_number=5, status=StepExecutionStatus.PASSED),
    ]

    # Evolve macro
    engine = MacroEvolutionEngine()
    evolved_macro, metadata = engine.evolve(
        original_macro=original_macro,
        evolution_records=evolution_records,
        step_results=step_results,
        target_platform="web"
    )

    print(f"\nOriginal Macro: {len(original_macro)} steps")
    print(f"Evolved Macro: {len(evolved_macro)} steps")
    print(f"Expansion Ratio: {metadata['expansion_ratio']:.2f}x")
    print(f"Modified Steps: {metadata['modified_steps']}")
    print(f"Modification Rate: {metadata['modification_rate']:.1%}")

    print("\nEvolved Macro Structure:")
    for step in evolved_macro:
        step_num = step.get('step_number', '?')
        event_type = step.get('event_type', 'unknown')
        source = step.get('source', 'dom')
        extra = ""

        if 'precondition' in step:
            extra += " [has precondition]"
        if 'fallback' in step:
            extra += " [has fallback]"
        if 'selector_chain' in step.get('payload', {}):
            extra += f" [selector chain: {len(step['payload']['selector_chain'])}]"

        print(f"  Step {step_num}: {event_type} ({source}){extra}")


def example_optimization():
    """Example: Optimize evolved macro by removing redundancies"""

    print("\n" + "=" * 60)
    print("Phase 3: Macro Optimization")
    print("=" * 60)

    # Evolved macro with potential redundancies
    evolved_macro = [
        {"step_number": 1, "type": "action", "event_type": "goto", "payload": {}},
        {"step_number": 2, "type": "action", "event_type": "wait", "payload": {"duration_ms": 1000}},
        {"step_number": 3, "type": "action", "event_type": "wait", "payload": {"duration_ms": 500}},
        {"step_number": 4, "type": "action", "event_type": "wait", "payload": {"duration_ms": 500}},
        {"step_number": 5, "type": "action", "event_type": "click", "payload": {}},
        {"step_number": 6, "type": "verify", "payload": {"expected_state": {"page": "loaded"}}},
        {"step_number": 7, "type": "verify", "payload": {"expected_state": {"page": "loaded"}}},
    ]

    print(f"\nBefore Optimization: {len(evolved_macro)} steps")

    optimizer = EvolutionOptimizer()
    optimized = optimizer.optimize(evolved_macro)

    print(f"After Optimization: {len(optimized)} steps")

    print("\nOptimizations Applied:")
    print("  - Merged consecutive waits (1000 + 500 + 500 = 2000ms)")
    print("  - Removed duplicate verification steps")


def example_fallback_chain():
    """Example: Generate fallback chain for critical steps"""

    print("\n" + "=" * 60)
    print("Phase 3: Fallback Chain Generation")
    print("=" * 60)

    critical_step = {
        "step_number": 1,
        "type": "action",
        "event_type": "open_app",
        "source": "mobile",
        "payload": {"package_name": "com.example.app"}
    }

    engine = MacroEvolutionEngine()
    fallback_chain = engine.generate_fallback_chain(critical_step, max_fallbacks=3)

    print(f"\nGenerated {len(fallback_chain)} fallback levels:\n")

    for i, step in enumerate(fallback_chain):
        print(f"Level {i}:")
        payload = step.get('payload', {})

        if 'max_retries' in payload:
            print(f"  Retries: {payload['max_retries']}")
        if 'use_fuzzy_match' in payload:
            print(f"  Fuzzy match: enabled")
        if 'fallback_type' in step:
            print(f"  Fallback type: {step['fallback_type']}")


def print_evolution_summary():
    """Print summary of all available transformers"""

    print("\n" + "=" * 60)
    print("Phase 3: Available Transformers")
    print("=" * 60)

    transformers = [
        ("CoordinateDriftTransformer", "Transforms coordinate steps to use selectors + fallback"),
        ("ElementNotFoundTransformer", "Adds selector chains and scroll-to-find"),
        ("ElementObscuredTransformer", "Adds popup dismissal sequences"),
        ("LoadingTimeoutTransformer", "Converts fixed waits to conditional waits"),
        ("StateMismatchTransformer", "Adds state verification and recovery"),
    ]

    for name, description in transformers:
        print(f"\n{name}:")
        print(f"  {description}")


if __name__ == "__main__":
    # Run all examples
    example_coordinate_drift_evolution()
    example_element_not_found_evolution()
    example_element_obscured_evolution()
    example_full_macro_evolution()
    example_optimization()
    example_fallback_chain()
    print_evolution_summary()

    print("\n" + "=" * 60)
    print("Phase 3 Examples Complete")
    print("=" * 60)
