"""
Example: Using the Agent-based Macro Verification System

This file demonstrates how to use the new verification system to validate
and evolve macros before deployment.
"""

import asyncio
from app.core.execution.macro import (
    AgentMacroValidator,
    AgentConfig,
    EnvironmentConfig,
    RoundConfig,
    VerificationReporter,
    VerificationRequest,
)


async def example_web_verification():
    """Example: Verify a web automation macro"""

    # Define a sample macro (e.g., login flow)
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
            "target_selector": "#login-button",
            "payload": {"selector": "#login-button"}
        },
        {
            "step_number": 5,
            "type": "extract",
            "extract_type": "get_text",
            "key": "login_result",
            "source": "dom",
            "target_selector": ".welcome-message",
            "payload": {"selector": ".welcome-message"}
        }
    ]

    # Configure the verification
    request = VerificationRequest(
        macro_script=macro_script,
        instructions="Verify login flow macro and handle common issues like popups or slow loading",

        target_environment=EnvironmentConfig(
            platform="web",
            browser_config={
                "headless": False,  # Show browser for verification
                "viewport": {"width": 1920, "height": 1080}
            }
        ),

        # Run 2 rounds: baseline + one with simulated interference
        max_rounds=2,
        round_configs=[
            RoundConfig(
                round_name="baseline",
                timeout_per_step=30,
                environment_overrides={}
            ),
            RoundConfig(
                round_name="with_delays",
                timeout_per_step=45,
                environment_overrides={"simulate_slow_network": True},
                inject_anomalies=["loading_delay"]
            )
        ],

        agent_config=AgentConfig(
            llm_model="gpt-4o",
            max_retries_per_step=3,
            allow_strategy_adaptation=True,
            conservative_mode=False,  # Continue on non-critical failures
            enable_screenshot_analysis=True
        ),

        output_mode="evolved"  # Return evolved macro with fixes
    )

    # Execute verification
    validator = AgentMacroValidator(request)
    response = await validator.validate()

    # Generate and print report
    reporter = VerificationReporter(response)
    reporter.print_summary()

    # Save full report
    with open("verification_report.md", "w") as f:
        f.write(reporter.to_markdown())

    # Check results
    if response.success:
        print(f"✅ Verification passed!")
        print(f"   Recommended execution mode: {response.execution_mode.value}")
        print(f"   Confidence score: {response.confidence_score:.2%}")

        if response.evolved_macro:
            print(f"   Macro evolved with {len(response.evolution_records)} improvements")
            # Use evolved_macro for deployment
    else:
        print(f"❌ Verification failed")
        print(f"   Issues found: {len(response.verification_report.issues)}")
        for issue in response.verification_report.issues:
            print(f"   - {issue.severity}: {issue.description}")

    return response


async def example_mobile_verification():
    """Example: Verify a mobile automation macro"""

    macro_script = [
        {
            "step_number": 1,
            "type": "action",
            "event_type": "open_app",
            "source": "mobile",
            "payload": {"package_name": "com.example.app"}
        },
        {
            "step_number": 2,
            "type": "action",
            "event_type": "wait",
            "source": "mobile",
            "payload": {"duration_ms": 2000}
        },
        {
            "step_number": 3,
            "type": "action",
            "event_type": "tap",
            "source": "mobile",
            "payload": {"x": 540, "y": 1200}  # May drift!
        },
        {
            "step_number": 4,
            "type": "extract",
            "extract_type": "dump_ui",
            "key": "ui_state",
            "source": "mobile"
        }
    ]

    request = VerificationRequest(
        macro_script=macro_script,
        target_environment=EnvironmentConfig(
            platform="android",
            device_id="emulator-5554"  # Specific device
        ),
        max_rounds=2,
        agent_config=AgentConfig(
            allow_strategy_adaptation=True,
            enable_screenshot_analysis=True
        )
    )

    validator = AgentMacroValidator(request)
    response = await validator.validate()

    # The validator will detect coordinate drift and suggest adaptations
    reporter = VerificationReporter(response)
    print(reporter.to_markdown())

    return response


async def example_integration_with_synthesis():
    """Example: Integrate verification with skill synthesis"""

    from app.core.learning.skill_synthesizer import WorkflowSynthesizer

    # After synthesizing a skill
    synthesizer = WorkflowSynthesizer(thread_id="thread_123")
    skill = await synthesizer.synthesize()

    if skill and skill.macro_script:
        # Verify the synthesized macro before saving
        from app.core.execution.macro.verification_models import VerificationRequest

        request = VerificationRequest(
            macro_script=skill.macro_script,
            target_environment=EnvironmentConfig(
                platform="web"  # or skill.inferred_platform
            ),
            max_rounds=1,  # Quick verification for synthesis
            agent_config=AgentConfig(
                allow_strategy_adaptation=True,
                conservative_mode=True  # Be strict during synthesis
            )
        )

        validator = AgentMacroValidator(request)
        response = await validator.validate()

        # Update skill based on verification results
        skill.execution_mode = response.execution_mode.value

        if response.execution_mode.value == "deterministic" and response.success:
            # Macro is stable, can run deterministically
            print(f"✅ Macro verified as deterministic")
        elif response.evolved_macro:
            # Use evolved macro with error handling
            skill.macro_script = response.evolved_macro
            print(f"🔄 Macro evolved with {len(response.evolution_records)} fixes")

        return skill

    return None


if __name__ == "__main__":
    # Run example
    print("=" * 60)
    print("Agent-based Macro Verification - Example Usage")
    print("=" * 60)
    print()

    # Note: These examples require actual browser/mobile controllers
    # Uncomment to run:
    # asyncio.run(example_web_verification())
    # asyncio.run(example_mobile_verification())

    print("Examples defined. Uncomment the asyncio.run() lines to execute.")
    print()
    print("Key features demonstrated:")
    print("  1. Multi-round verification (baseline + interference)")
    print("  2. Anomaly detection and adaptation")
    print("  3. Macro evolution with error handling")
    print("  4. Execution mode determination")
    print("  5. Report generation in multiple formats")
