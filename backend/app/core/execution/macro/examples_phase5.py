"""
Phase 5 Examples: Integration with MacroService and SkillSynthesizer

Demonstrates how the verification system integrates with existing services.
"""

import asyncio
from app.core.execution.macro.verification_service import (
    MacroServiceIntegration,
    SynthesisIntegration,
    VerificationService,
    quick_verify,
    verify_macro,
)


async def example_simple_verification():
    """Example: Simple verification using high-level API"""

    print("=" * 60)
    print("Phase 5: Simple Verification")
    print("=" * 60)

    # Sample macro
    macro_script = [
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
            "event_type": "input",
            "source": "dom",
            "target_selector": "#password",
            "payload": {"selector": "#password", "text": "password123"}
        },
        {
            "step_number": 4,
            "type": "action",
            "event_type": "click",
            "source": "dom",
            "target_selector": "#login-btn",
            "payload": {"selector": "#login-btn"}
        }
    ]

    # Quick verification (single round)
    result = await VerificationService.verify_and_select_mode(
        macro_script=macro_script,
        platform="web",
        confidence_threshold=0.7
    )

    print(f"\nVerification Result:")
    print(f"  Can Execute: {result['can_execute']}")
    print(f"  Recommended Mode: {result['recommended_mode']}")
    print(f"  Confidence: {result['confidence']:.2%}")
    print(f"  Reason: {result['reason']}")


async def example_full_verification_with_evolution():
    """Example: Full verification with macro evolution"""

    print("\n" + "=" * 60)
    print("Phase 5: Full Verification with Evolution")
    print("=" * 60)

    # Macro with potential issues
    macro_script = [
        {
            "step_number": 1,
            "type": "action",
            "event_type": "tap",
            "source": "mobile",
            "target_selector": "登录按钮",
            "payload": {"x": 540, "y": 1200}  # Coordinate drift likely
        },
        {
            "step_number": 2,
            "type": "action",
            "event_type": "wait",
            "source": "mobile",
            "payload": {"duration_ms": 1000}  # May need longer
        },
        {
            "step_number": 3,
            "type": "extract",
            "extract_type": "dump_ui",
            "key": "ui_state",
            "source": "mobile"
        }
    ]

    # Full verification with 2 rounds
    result = await VerificationService.verify_macro(
        macro_script=macro_script,
        platform="android",
        max_rounds=2,
        auto_evolve=True
    )

    print(f"\nVerification Complete:")
    print(f"  Success: {result['success']}")
    print(f"  Status: {result['status']}")
    print(f"  Execution Mode: {result['execution_mode']}")
    print(f"  Confidence: {result['confidence_score']:.2%}")
    print(f"  Rounds: {result['rounds_completed']}")

    if result.get('evolved_macro'):
        original_count = len(macro_script)
        evolved_count = len(result['evolved_macro'])
        print(f"\n  Macro Evolved: {original_count} -> {evolved_count} steps")

    if result.get('verification_report'):
        report = result['verification_report']
        print(f"\n  Issues Found: {len(report.get('issues', []))}")
        print(f"  Recommendations: {len(report.get('recommendations', []))}")


async def example_convenience_functions():
    """Example: Using convenience functions"""

    print("\n" + "=" * 60)
    print("Phase 5: Convenience Functions")
    print("=" * 60)

    macro_script = [
        {"step_number": 1, "type": "action", "event_type": "goto",
         "source": "dom", "payload": {"url": "https://example.com"}},
        {"step_number": 2, "type": "action", "event_type": "click",
         "source": "dom", "payload": {"selector": "#btn"}},
    ]

    # Using verify_macro convenience function
    print("\n1. Using verify_macro():")
    result = await verify_macro(
        macro_script=macro_script,
        platform="web",
        max_rounds=2
    )
    print(f"   Result: {result['success']}")

    # Using quick_verify convenience function
    print("\n2. Using quick_verify():")
    result = await quick_verify(
        macro_script=macro_script,
        platform="web"
    )
    print(f"   Mode: {result['recommended_mode']}")


async def example_synthesis_integration():
    """Example: Integration with SkillSynthesizer"""

    print("\n" + "=" * 60)
    print("Phase 5: Synthesis Integration")
    print("=" * 60)

    # This is what happens inside WorkflowSynthesizer.verify_macro()

    macro_script = [
        {"step_number": 1, "type": "action", "event_type": "open_app",
         "source": "mobile", "payload": {"package_name": "com.example.app"}},
        {"step_number": 2, "type": "action", "event_type": "tap",
         "source": "mobile", "payload": {"x": 500, "y": 1000}},
        {"step_number": 3, "type": "extract", "extract_type": "dump_ui",
         "key": "ui_state", "source": "mobile"},
    ]

    # SynthesisIntegration.verify_for_synthesis is called by SkillSynthesizer
    result = await SynthesisIntegration.verify_for_synthesis(
        macro_script=macro_script,
        thread_id="synthesis_thread_123",
        project_id=1
    )

    print("\nSynthesis Verification Result:")
    print(f"  Status: {result.get('status')}")

    if result.get('status') == 'success':
        print(f"  Execution Mode: {result.get('execution_mode')}")
        print(f"  Confidence: {result.get('confidence', 0):.2%}")

        if result.get('evolved_macro'):
            print(f"  Evolved Macro: {len(result['evolved_macro'])} steps")
    else:
        print(f"  Error: {result.get('error', 'Unknown error')}")


async def example_macroservice_integration():
    """Example: Integration with MacroService"""

    print("\n" + "=" * 60)
    print("Phase 5: MacroService Integration")
    print("=" * 60)

    print("""
MacroServiceIntegration provides pre-flight verification before execution.

Usage:
    result = await MacroServiceIntegration.execute_with_verification(
        thread_id="thread_123",
        macro_script=macro_steps,
        params={"platform": "web"},
        verify_first=True,
        confidence_threshold=0.7
    )

This will:
1. Run quick verification (1 round)
2. Determine execution mode based on confidence
3. If confidence < threshold, add agent supervision flag
4. Execute via MacroService.run()

Example Output:""")

    # Simulated output
    print("""
    [thread_123] Running pre-flight verification
    [thread_123] Verification result: mode=hybrid, confidence=75%
    [thread_123] Executing with hybrid mode (agent supervision on standby)
    [thread_123] Macro execution completed successfully
""")


def example_integration_points():
    """Show all integration points"""

    print("\n" + "=" * 60)
    print("Phase 5: Integration Points Summary")
    print("=" * 60)

    print("""
1. SkillSynthesizer Integration:
   - Location: skill_synthesizer.py:verify_macro()
   - Class: SynthesisIntegration.verify_for_synthesis()
   - Purpose: Verify and evolve macro during skill creation
   - Returns: {status, execution_mode, confidence, evolved_macro}

2. MacroService Integration:
   - Location: MacroService.run() via execute_with_verification()
   - Class: MacroServiceIntegration.execute_with_verification()
   - Purpose: Pre-flight verification before execution
   - Adds: _verification_result, _require_agent_supervision flags

3. Direct Usage:
   - VerificationService.verify_macro() - Full verification
   - VerificationService.verify_and_select_mode() - Quick check
   - VerificationService.evolve_macro() - Just evolution
   - verify_macro() - Convenience function
   - quick_verify() - Single-round check

4. Event Flow:
   ┌─────────────────┐
   │ SkillSynthesizer│
   │   .synthesize() │
   └────────┬────────┘
            │
            ▼
   ┌─────────────────┐
   │  verify_macro() │ ◄── New: Agent-based verification
   │  (Phase 5)      │
   └────────┬────────┘
            │
            ▼
   ┌─────────────────┐
   │   MacroService  │
   │     .run()      │ ◄── Optional: Pre-flight verification
   └─────────────────┘
""")


def print_final_summary():
    """Print final implementation summary"""

    print("\n" + "=" * 60)
    print("Phase 5 Complete: Full Integration")
    print("=" * 60)

    print("""
All 5 Phases Complete:

Phase 1: Core Framework (6 files, ~1,800 lines)
  - AgentMacroValidator - Main orchestrator
  - AnomalyDetector - Detects execution anomalies
  - VerificationWorker - Real environment execution
  - VerificationReporter - Report generation
  - verification_models.py - All data models

Phase 2: Adaptation Library (2 files, ~800 lines)
  - AdaptationStrategyLibrary - Two-tier adaptation
  - QuickFixStrategy - Fast heuristic fixes
  - LLMDeepStrategy - LLM-powered adaptation

Phase 3: Evolution Engine (2 files, ~1,000 lines)
  - MacroEvolutionEngine - Transforms macros
  - StepTransformers - Platform-specific evolution
  - EvolutionOptimizer - Removes redundancies

Phase 4: Multi-round Orchestration (2 files, ~900 lines)
  - RoundOrchestrator - Multi-round management
  - InterferenceInjectors - Simulates real-world issues
  - RoundStrategies - Baseline, Stress, Chaos rounds

Phase 5: Integration Layer (2 files, ~600 lines)
  - VerificationService - High-level API
  - SynthesisIntegration - SkillSynthesizer hook
  - MacroServiceIntegration - MacroService hook

Total: ~5,100 lines across 14 new files
""")


async def main():
    """Run all Phase 5 examples"""

    await example_simple_verification()
    await example_full_verification_with_evolution()
    await example_convenience_functions()
    await example_synthesis_integration()
    example_macroservice_integration()
    example_integration_points()
    print_final_summary()


if __name__ == "__main__":
    asyncio.run(main())
