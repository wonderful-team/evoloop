"""
VerificationReporter - Report Generation and Visualization

Generates human-readable and machine-parseable verification reports.
Supports multiple output formats: Markdown, JSON, HTML.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.execution.macro.verification_models import (
    AdaptationRecord,
    ExecutionMode,
    MacroEvolutionRecord,
    RoundReport,
    StepExecutionStatus,
    VerificationIssue,
    VerificationReport,
    VerificationResponse,
    VerificationStatus,
)

logger = logging.getLogger(__name__)


class VerificationReporter:
    """
    Reporter for verification results.

    Generates reports in multiple formats for different audiences:
    - Markdown: Human-readable summary
    - JSON: Machine-parseable for automation
    - HTML: Rich visualization with screenshots
    """

    def __init__(self, response: VerificationResponse):
        self.response = response
        self.report = response.verification_report

    def to_markdown(self) -> str:
        """Generate Markdown report"""
        lines = [
            "# Macro Verification Report",
            "",
            f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Status:** {self._format_status(self.response.status)}",
            f"**Execution Mode:** {self.response.execution_mode.value}",
            f"**Confidence Score:** {self.response.confidence_score:.2%}",
            "",
            "## Summary",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Overall Success Rate | {self.report.summary.overall_success_rate:.2%} |",
            f"| Adaptation Rate | {self.report.summary.adaptation_rate:.2%} |",
            f"| Max Round Variance | {self.report.summary.max_round_variance:.2%} |",
            f"| Avg Execution Time | {self.report.summary.average_execution_time_ms}ms |",
            f"| Anomalies Detected | {self.report.summary.total_anomalies_detected} |",
            f"| Adaptations Applied | {self.report.summary.total_adaptations_applied} |",
            "",
        ]

        # Issues section
        if self.report.issues:
            lines.extend([
                "## Issues",
                "",
            ])
            for issue in self.report.issues:
                severity_emoji = "🔴" if issue.severity == "critical" else "⚠️" if issue.severity == "warning" else "ℹ️"
                lines.extend([
                    f"### {severity_emoji} {issue.category}",
                    "",
                    f"**Severity:** {issue.severity}",
                    f"**Description:** {issue.description}",
                ])
                if issue.affected_steps:
                    lines.append(f"**Affected Steps:** {', '.join(map(str, issue.affected_steps))}")
                if issue.suggestion:
                    lines.append(f"**Suggestion:** {issue.suggestion}")
                lines.append("")

        # Round details
        lines.extend([
            "## Round Details",
            "",
        ])

        for round_report in self.report.rounds:
            lines.extend([
                f"### {round_report.round_name} (Round {round_report.round_number})",
                "",
                f"**Status:** {self._format_status(round_report.status)}",
                f"**Total Steps:** {round_report.total_steps}",
                f"- ✅ Passed: {round_report.passed_steps}",
                f"- 🔄 Adapted: {round_report.adapted_steps}",
                f"- ❌ Failed: {round_report.failed_steps}",
                f"- ⏭️ Skipped: {round_report.skipped_steps}",
                "",
            ])

            # Step details table
            if round_report.step_results:
                lines.extend([
                    "| Step | Status | Time (ms) | Adaptations |",
                    "|------|--------|-----------|-------------|",
                ])
                for step in round_report.step_results:
                    status_emoji = self._status_emoji(step.status)
                    lines.append(
                        f"| {step.step_number} | {status_emoji} {step.status.value} | "
                        f"{step.execution_time_ms} | {len(step.adaptations)} |"
                    )
                lines.append("")

        # Evolution records
        if self.response.evolution_records:
            lines.extend([
                "## Macro Evolution",
                "",
                f"**Total Evolutions:** {len(self.response.evolution_records)}",
                "",
            ])
            for i, evo in enumerate(self.response.evolution_records, 1):
                lines.extend([
                    f"### Evolution {i}",
                    "",
                    f"**Reason:** {evo.evolution_reason}",
                    f"**Confidence:** {evo.confidence:.2%}",
                    "",
                ])

        # Recommendations
        if self.report.recommendations:
            lines.extend([
                "## Recommendations",
                "",
            ])
            for rec in self.report.recommendations:
                lines.append(f"- {rec}")
            lines.append("")

        # Evolved macro preview
        if self.response.evolved_macro:
            lines.extend([
                "## Evolved Macro Preview",
                "",
                f"The macro has been evolved with {len(self.response.evolution_records)} improvements.",
                "",
                "```json",
                json.dumps(self.response.evolved_macro[:3], indent=2) + "...",
                "```",
                "",
            ])

        return "\n".join(lines)

    def to_json(self) -> str:
        """Generate JSON report"""
        return json.dumps(
            self.response.model_dump(),
            indent=2,
            default=str,
            ensure_ascii=False
        )

    def to_html(self) -> str:
        """Generate HTML report with rich visualization"""
        # Simplified HTML for now - can be enhanced with templates
        return f"""<!DOCTYPE html>
<html>
<head>
    <title>Macro Verification Report</title>
    <style>
        body {{ font-family: system-ui, -apple-system, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #f5f5f5; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
        .status-completed {{ color: #28a745; }}
        .status-failed {{ color: #dc3545; }}
        .status-partial {{ color: #ffc107; }}
        .summary-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin-bottom: 20px; }}
        .summary-card {{ background: #f8f9fa; padding: 15px; border-radius: 6px; }}
        .summary-card h3 {{ margin-top: 0; font-size: 14px; color: #666; }}
        .summary-card .value {{ font-size: 24px; font-weight: bold; }}
        .issue {{ background: #fff3cd; padding: 10px; border-left: 4px solid #ffc107; margin-bottom: 10px; }}
        .issue.critical {{ background: #f8d7da; border-left-color: #dc3545; }}
        table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #f5f5f5; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Macro Verification Report</h1>
        <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <p>Status: <span class="status-{self.response.status.value}">{self._format_status(self.response.status)}</span></p>
        <p>Execution Mode: <strong>{self.response.execution_mode.value}</strong></p>
        <p>Confidence Score: <strong>{self.response.confidence_score:.2%}</strong></p>
    </div>

    <div class="summary-grid">
        <div class="summary-card">
            <h3>Success Rate</h3>
            <div class="value">{self.report.summary.overall_success_rate:.1%}</div>
        </div>
        <div class="summary-card">
            <h3>Adaptation Rate</h3>
            <div class="value">{self.report.summary.adaptation_rate:.1%}</div>
        </div>
        <div class="summary-card">
            <h3>Anomalies</h3>
            <div class="value">{self.report.summary.total_anomalies_detected}</div>
        </div>
    </div>

    <h2>Issues</h2>
    {self._generate_issues_html()}

    <h2>Round Summary</h2>
    {self._generate_rounds_html()}

    <h2>Recommendations</h2>
    <ul>
        {''.join(f'<li>{rec}</li>' for rec in self.report.recommendations)}
    </ul>
</body>
</html>"""

    def _format_status(self, status: VerificationStatus) -> str:
        """Format status for display"""
        return {
            VerificationStatus.COMPLETED: "✅ Completed",
            VerificationStatus.PARTIAL_FAILED: "⚠️ Partially Failed",
            VerificationStatus.FAILED: "❌ Failed",
            VerificationStatus.RUNNING: "⏳ Running",
            VerificationStatus.PENDING: "⏸️ Pending",
        }.get(status, str(status))

    def _status_emoji(self, status: StepExecutionStatus) -> str:
        """Get emoji for step status"""
        return {
            StepExecutionStatus.PASSED: "✅",
            StepExecutionStatus.ADAPTED: "🔄",
            StepExecutionStatus.FAILED: "❌",
            StepExecutionStatus.SKIPPED: "⏭️",
            StepExecutionStatus.TIMEOUT: "⏱️",
            StepExecutionStatus.PENDING: "⏸️",
        }.get(status, "❓")

    def _generate_issues_html(self) -> str:
        """Generate HTML for issues section"""
        if not self.report.issues:
            return "<p>No issues found.</p>"

        issues_html = []
        for issue in self.report.issues:
            css_class = f"issue {issue.severity}"
            issues_html.append(
                f'<div class="{css_class}">'
                f'<strong>{issue.category}</strong>: {issue.description}'
                f'</div>'
            )
        return "\n".join(issues_html)

    def _generate_rounds_html(self) -> str:
        """Generate HTML for rounds section"""
        if not self.report.rounds:
            return "<p>No rounds executed.</p>"

        rows = []
        for round_report in self.report.rounds:
            rows.append(
                f"<tr>"
                f"<td>{round_report.round_number}</td>"
                f"<td>{round_report.round_name}</td>"
                f"<td>{round_report.passed_steps}</td>"
                f"<td>{round_report.adapted_steps}</td>"
                f"<td>{round_report.failed_steps}</td>"
                f"</tr>"
            )

        return f"""<table>
    <tr>
        <th>Round</th>
        <th>Name</th>
        <th>Passed</th>
        <th>Adapted</th>
        <th>Failed</th>
    </tr>
    {''.join(rows)}
</table>"""

    def print_summary(self) -> None:
        """Print console-friendly summary"""
        print("\n" + "=" * 60)
        print("MACRO VERIFICATION REPORT")
        print("=" * 60)
        print(f"Status: {self._format_status(self.response.status)}")
        print(f"Execution Mode: {self.response.execution_mode.value}")
        print(f"Confidence Score: {self.response.confidence_score:.2%}")
        print(f"Rounds Completed: {self.response.rounds_completed}")
        print("-" * 60)
        print(f"Success Rate: {self.report.summary.overall_success_rate:.2%}")
        print(f"Adaptation Rate: {self.report.summary.adaptation_rate:.2%}")
        print(f"Anomalies Detected: {self.report.summary.total_anomalies_detected}")
        print("=" * 60)

        if self.report.issues:
            print("\nIssues Found:")
            for issue in self.report.issues:
                severity = "[CRITICAL]" if issue.severity == "critical" else "[WARNING]"
                print(f"  {severity} {issue.category}: {issue.description}")

        if self.report.recommendations:
            print("\nRecommendations:")
            for rec in self.report.recommendations:
                print(f"  • {rec}")

        print("=" * 60 + "\n")


def generate_comparison_report(
    original_response: VerificationResponse,
    evolved_response: VerificationResponse
) -> str:
    """
    Generate a comparison report between original and evolved macros.

    Shows improvements made through the evolution process.
    """
    lines = [
        "# Macro Evolution Comparison",
        "",
        "## Before vs After",
        "",
        "| Metric | Original | Evolved | Improvement |",
        "|--------|----------|---------|-------------|",
        f"| Success Rate | {original_response.verification_report.summary.overall_success_rate:.2%} | "
        f"{evolved_response.verification_report.summary.overall_success_rate:.2%} | "
        f"+{(evolved_response.verification_report.summary.overall_success_rate - original_response.verification_report.summary.overall_success_rate):.2%} |",
        f"| Adaptation Rate | {original_response.verification_report.summary.adaptation_rate:.2%} | "
        f"{evolved_response.verification_report.summary.adaptation_rate:.2%} | "
        f"{(original_response.verification_report.summary.adaptation_rate - evolved_response.verification_report.summary.adaptation_rate):+.2%} |",
        f"| Confidence Score | {original_response.confidence_score:.2%} | "
        f"{evolved_response.confidence_score:.2%} | "
        f"+{(evolved_response.confidence_score - original_response.confidence_score):.2%} |",
        f"| Anomalies | {original_response.verification_report.summary.total_anomalies_detected} | "
        f"{evolved_response.verification_report.summary.total_anomalies_detected} | "
        f"{(evolved_response.verification_report.summary.total_anomalies_detected - original_response.verification_report.summary.total_anomalies_detected):+d} |",
        "",
        "## Evolution Summary",
        "",
        f"The macro was evolved with **{len(evolved_response.evolution_records)}** improvements.",
        "",
        "### Key Changes:",
    ]

    for evo in evolved_response.evolution_records:
        lines.append(f"- {evo.evolution_reason} (confidence: {evo.confidence:.2%})")

    lines.append("")

    return "\n".join(lines)
