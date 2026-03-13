"""
Phase 4 Examples: Multi-round Orchestration

Demonstrates how the RoundOrchestrator manages verification rounds
with interference injection.
"""

import asyncio
from app.core.execution.macro.round_orchestrator import (
    BaselineStrategy,
    ChaosStrategy,
    CoordinateDriftInjector,
    DelayInjector,
    ElementInstabilityInjector,
    InterferenceRegistry,
    NetworkDegradationInjector,
    PopupInterferenceInjector,
    ProgressiveDifficultyStrategy,
    RoundContext,
    RoundOrchestrator,
    StressTestStrategy,
)
from app.core.execution.macro.verification_models import (
    RoundConfig,
    RoundReport,
    VerificationStatus,
    StepExecutionStatus,
)


def example_round_strategies():
    """Example: Different round strategies"""

    print("=" * 60)
    print("Phase 4: Round Strategies")
    print("=" * 60)

    strategies = [
        BaselineStrategy(),
        StressTestStrategy(intensity=0.5),
        ChaosStrategy(intensity=0.8),
        ProgressiveDifficultyStrategy(),
    ]

    base_config = RoundConfig(
        round_name="default",
        timeout_per_step=30
    )

    for i, strategy in enumerate(strategies, 1):
        print(f"\n{i}. {strategy.get_name().upper()}")
        print("-" * 40)

        config = strategy.configure_round(i, base_config)
        print(f"   Round Name: {config.round_name}")
        print(f"   Timeout: {config.timeout_per_step}s")
        print(f"   Interference Types: {config.inject_anomalies or 'None'}")
        print(f"   Environment Overrides: {config.environment_overrides}")


def example_interference_injectors():
    """Example: Interference injectors"""

    print("\n" + "=" * 60)
    print("Phase 4: Interference Injectors")
    print("=" * 60)

    injectors = [
        DelayInjector(),
        NetworkDegradationInjector(),
        ElementInstabilityInjector(),
        PopupInterferenceInjector(),
        CoordinateDriftInjector(),
    ]

    base_step = {
        "step_number": 1,
        "type": "action",
        "event_type": "click",
        "source": "dom",
        "target_selector": "#submit-btn",
        "payload": {
            "selector": "#submit-btn",
            "x": 500,
            "y": 300
        }
    }

    context = RoundContext(
        round_number=2,
        previous_reports=[]
    )

    for injector in injectors:
        print(f"\n{injector.get_name().upper()}")
        print(f"   Description: {injector.get_description()}")
        print(f"   Can Apply: {injector.can_apply(base_step, context)}")

        if injector.can_apply(base_step, context):
            modified = injector.apply(base_step, context, intensity=0.5)
            interference = modified.get("payload", {}).get("injected_interference", {})
            print(f"   Applied: {interference.get('description', 'N/A')}")


def example_orchestrator_usage():
    """Example: Using the orchestrator"""

    print("\n" + "=" * 60)
    print("Phase 4: Round Orchestrator")
    print("=" * 60)

    # Create orchestrator with custom strategies
    orchestrator = RoundOrchestrator(
        strategies=[
            BaselineStrategy(),
            StressTestStrategy(intensity=0.6),
            ChaosStrategy(intensity=0.8)
        ],
        enable_interference=True
    )

    # Sample macro
    macro_script = [
        {
            "step_number": 1,
            "type": "action",
            "event_type": "goto",
            "source": "dom",
            "payload": {"url": "https://example.com"}
        },
        {
            "step_number": 2,
            "type": "action",
            "event_type": "click",
            "source": "dom",
            "target_selector": "#login",
            "payload": {"selector": "#login", "x": 100, "y": 200}
        },
        {
            "step_number": 3,
            "type": "action",
            "event_type": "wait",
            "source": "dom",
            "payload": {"duration_ms": 1000}
        },
    ]

    # Simulate 3 rounds
    base_config = RoundConfig(round_name="default", timeout_per_step=30)
    previous_reports = []

    for round_num in range(1, 4):
        print(f"\n--- Round {round_num} ---")

        config, modified_macro = orchestrator.prepare_round(
            round_number=round_num,
            base_config=base_config,
            macro_script=macro_script,
            previous_reports=previous_reports
        )

        print(f"Round Name: {config.round_name}")
        print(f"Original Steps: {len(macro_script)}")
        print(f"Modified Steps: {len(modified_macro)}")

        # Check for interference
        summary = orchestrator.get_interference_summary(modified_macro)
        print(f"Steps with Interference: {summary['interfered_steps']}")
        print(f"Interference Types: {summary['interference_types']}")

        # Simulate a report
        report = RoundReport(
            round_number=round_num,
            round_name=config.round_name,
            status=VerificationStatus.COMPLETED,
            total_steps=len(modified_macro),
            passed_steps=2,
            adapted_steps=1 if summary['interfered_steps'] > 0 else 0,
            failed_steps=0
        )
        previous_reports.append(report)


def example_progressive_difficulty():
    """Example: Progressive difficulty strategy"""

    print("\n" + "=" * 60)
    print("Phase 4: Progressive Difficulty")
    print("=" * 60)

    strategy = ProgressiveDifficultyStrategy()
    base_config = RoundConfig(round_name="default", timeout_per_step=30)

    print("\nProgressive round configurations:")
    for round_num in range(1, 5):
        config = strategy.configure_round(round_num, base_config)
        intensity = config.environment_overrides.get("interference_intensity", 0)
        print(f"\n  Round {round_num}:")
        print(f"    Name: {config.round_name}")
        print(f"    Intensity: {intensity:.1%}")
        print(f"    Timeout: {config.timeout_per_step}s")
        print(f"    Interference Types: {len(config.inject_anomalies)}")


def example_interference_registry():
    """Example: Using the interference registry"""

    print("\n" + "=" * 60)
    print("Phase 4: Interference Registry")
    print("=" * 60)

    # List available injectors
    available = InterferenceRegistry.list_injectors()
    print(f"\nAvailable Interference Injectors ({len(available)}):")
    for name in available:
        injector = InterferenceRegistry.get_injector(name)
        if injector:
            print(f"  - {name}: {injector.get_description()}")


def example_chaos_round():
    """Example: Chaos round with all interference types"""

    print("\n" + "=" * 60)
    print("Phase 4: Chaos Round")
    print("=" * 60)

    chaos = ChaosStrategy(intensity=0.9)
    base_config = RoundConfig(round_name="default", timeout_per_step=30)

    config = chaos.configure_round(1, base_config)

    print(f"\nChaos Round Configuration:")
    print(f"  Name: {config.round_name}")
    print(f"  Intensity: {config.environment_overrides.get('interference_intensity', 0):.0%}")
    print(f"  Chaos Mode: {config.environment_overrides.get('chaos_mode', False)}")
    print(f"  Timeout Multiplier: 2x ({config.timeout_per_step}s)")
    print(f"\n  All Interference Types Applied:")
    for anomaly in config.inject_anomalies:
        print(f"    - {anomaly}")

    # Create sample macro and apply chaos
    macro = [
        {"step_number": i, "type": "action", "event_type": "click",
         "payload": {"x": 100 * i, "y": 200}}
        for i in range(1, 6)
    ]

    orchestrator = RoundOrchestrator(
        strategies=[chaos],
        enable_interference=True
    )

    context = RoundContext(round_number=1, previous_reports=[])
    modified = orchestrator._apply_interference(
        macro,
        config.inject_anomalies,
        0.9,
        context
    )

    print(f"\n  Sample Macro Transformations:")
    for orig, mod in zip(macro, modified):
        orig_interference = orig.get("payload", {}).get("injected_interference")
        mod_interference = mod.get("payload", {}).get("injected_interference")

        if mod_interference:
            print(f"    Step {orig['step_number']}: {mod_interference['type']}")


def example_integration_with_validator():
    """Example: How validator uses orchestrator"""

    print("\n" + "=" * 60)
    print("Phase 4: Integration with AgentMacroValidator")
    print("=" * 60)

    print("""
The AgentMacroValidator now uses RoundOrchestrator internally:

1. Validator creates orchestrator based on max_rounds:
   - 1 round: Baseline only
   - 2 rounds: Baseline + Stress Test
   - 3+ rounds: Baseline + Stress Test + Chaos

2. For each round:
   - orchestrator.prepare_round() applies interference
   - Validator executes the modified macro
   - orchestrator.should_continue() decides if more rounds needed

3. Interference summary logged after each round

Example:
    validator = AgentMacroValidator(request)
    response = await validator.validate()

    # Internally:
    # Round 1 (baseline): No interference
    # Round 2 (stress):   Delays + element instability
    # Round 3 (chaos):    All interference types
""")


if __name__ == "__main__":
    # Run all examples
    example_round_strategies()
    example_interference_injectors()
    example_orchestrator_usage()
    example_progressive_difficulty()
    example_interference_registry()
    example_chaos_round()
    example_integration_with_validator()

    print("\n" + "=" * 60)
    print("Phase 4 Examples Complete")
    print("=" * 60)
