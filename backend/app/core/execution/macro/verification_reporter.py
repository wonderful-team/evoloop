"""
VerificationReporter - Report Generation and Visualization

Generates human-readable and machine-parseable verification reports.
Supports multiple output formats: Markdown, JSON, HTML.
"""

import json
import logging
from datetime import datetime

from app.core.execution.macro.models import (
    StepExecutionStatus,
    VerificationResponse,
    VerificationStatus,
)
from app.utils.template import render_template

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
        """Generate Markdown report using template."""
        try:

            # Prepare auxiliary data for template
            round_status_displays = [self._format_status(r.status) for r in self.report.rounds]
            step_emojis = []
            for r in self.report.rounds:
                step_emojis.append([self._status_emoji(s.status) for s in r.step_results])

            evolved_macro_json = ""
            if self.response.evolved_macro:
                evolved_macro_json = json.dumps(self.response.evolved_macro[:3], indent=2, ensure_ascii=False) + "..."

            return render_template(
                "common/report/verification.md.j2",
                timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                status_display=self._format_status(self.response.status),
                execution_mode=self.response.execution_mode.value,
                confidence_score=self.response.confidence_score,
                report=self.report,
                evolution_records=self.response.evolution_records,
                evolved_macro=self.response.evolved_macro,
                evolved_macro_json=evolved_macro_json,
                round_status_displays=round_status_displays,
                step_emojis=step_emojis
            )
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.error(f"Failed to render Verification template: {e}")
            return f"# Verification Report Error\n\nFailed to render report: {e}"

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
            VerificationStatus.COMPLETED: "[COMPLETED]",
            VerificationStatus.PARTIAL_FAILED: "[PARTIAL FAILED]",
            VerificationStatus.FAILED: "[FAILED]",
            VerificationStatus.RUNNING: "[RUNNING]",
            VerificationStatus.PENDING: "[PENDING]",
        }.get(status, str(status))

    def _status_emoji(self, status: StepExecutionStatus) -> str:
        """Get emoji for step status"""
        return {
            StepExecutionStatus.PASSED: "[PASS]",
            StepExecutionStatus.ADAPTED: "[ADAPTED]",
            StepExecutionStatus.FAILED: "[FAIL]",
            StepExecutionStatus.SKIPPED: "[SKIP]",
            StepExecutionStatus.TIMEOUT: "[TIMEOUT]",
            StepExecutionStatus.PENDING: "[PENDING]",
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

    def format_summary(self) -> str:
        """Build console-friendly summary string"""
        lines = [
            "",
            "=" * 60,
            "MACRO VERIFICATION REPORT",
            "=" * 60,
            f"Status: {self._format_status(self.response.status)}",
            f"Execution Mode: {self.response.execution_mode.value}",
            f"Confidence Score: {self.response.confidence_score:.2%}",
            f"Rounds Completed: {self.response.rounds_completed}",
            "-" * 60,
            f"Success Rate: {self.report.summary.overall_success_rate:.2%}",
            f"Adaptation Rate: {self.report.summary.adaptation_rate:.2%}",
            f"Anomalies Detected: {self.report.summary.total_anomalies_detected}",
            "=" * 60,
        ]

        if self.report.issues:
            lines.append("")
            lines.append("Issues Found:")
            for issue in self.report.issues:
                severity = "[CRITICAL]" if issue.severity == "critical" else "[WARNING]"
                lines.append(f"  {severity} {issue.category}: {issue.description}")

        if self.report.recommendations:
            lines.append("")
            lines.append("Recommendations:")
            for rec in self.report.recommendations:
                lines.append(f"  - {rec}")

        lines.append("=" * 60)
        lines.append("")
        return "\n".join(lines)

    def print_summary(self) -> None:
        """Log summary via logger"""
        logger.info(self.format_summary())


def generate_comparison_report(
    original_response: VerificationResponse,
    evolved_response: VerificationResponse
) -> str:
    """
    Generate a comparison report between original and evolved macros.

    Shows improvements made through the evolution process.
    """
    try:
        return render_template("common/report/comparison.md.j2", original=original_response, evolved=evolved_response)
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.error(f"Failed to render comparison report: {e}")
        return f"Comparison complete. Improvements: {len(evolved_response.evolution_records)}"
