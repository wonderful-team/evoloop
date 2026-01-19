import os
from datetime import datetime

from app.i18n.service import i18n


class ReportGenerator:
    """
    Generates structured research reports in Markdown.
    """

    @staticmethod
    def generate_report(topic: str, conclusion: str, logs: list[str], metadata: dict | None = None) -> str:
        """
        Constructs a full research report.
        """
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        meta_info = ""
        if metadata:
            meta_info = "\n".join([f"- **{k}**: {v}" for k, v in metadata.items()])

        # Clean logs (optional)
        # Maybe collapse them or put them in an appendix
        logs_text = "\n\n".join(logs)

        report = i18n.get("prompts.domain_tools.research_report.template",
                          topic=topic,
                          date=date_str,
                          meta_info=meta_info,
                          conclusion=conclusion,
                          logs_text=logs_text)
        return report

    @staticmethod
    def save_report(content: str, filename: str = None) -> str:
        """
        Saves report to disk.
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"research_report_{timestamp}.md"

        # Save to uploads or artifacts dir?
        # Let's say user's CWD
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)

        return os.path.abspath(filename)
