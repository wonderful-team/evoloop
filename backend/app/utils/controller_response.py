"""
Controller Response Utility

Provides standardized response formatting for environment controllers.
Eliminates repetitive render_template calls for report/response.prompt.j2
"""

from typing import Any

from app.utils.detect import detect_language
from app.utils.template import render_template


class ControllerResponse:
    """
    Utility class for generating standardized controller responses.
    
    This class eliminates repetitive render_template calls across mobile,
    browser, and desktop controllers by providing convenient static methods
    for common response patterns.
    
    Usage:
        from app.utils.controller_response import ControllerResponse
        
        # Success responses
        return ControllerResponse.success("Action completed")
        return ControllerResponse.success("Tapped element", details=element_info)
        
        # Error responses
        return ControllerResponse.error("Failed to tap")
        return ControllerResponse.not_found("button1")
        return ControllerResponse.missing_param("element_name")
        
        # Custom responses
        return ControllerResponse.render(success=True, message="Custom", details=...)
    """

    @staticmethod
    def render(
        success: bool,
        message: str,
        details: str | None = None,
        note: str | None = None,
        **extra_vars
    ) -> str:
        """
        Render a standard response template with given parameters.
        
        Args:
            success: Whether the operation succeeded
            message: Primary response message
            details: Optional detailed information
            note: Optional additional note
            **extra_vars: Additional template variables
            
        Returns:
            Rendered response string
        """
        return render_template(
            "common/report/response.prompt.j2",
            success=success,
            message=message,
            details=details,
            note=note,
            **extra_vars
        )

    @staticmethod
    def success(message: str, details: str | None = None, note: str | None = None) -> str:
        """Render a success response."""
        return ControllerResponse.render(
            success=True, message=message, details=details, note=note
        )

    @staticmethod
    def error(message: str, details: str | None = None, note: str | None = None) -> str:
        """Render an error response."""
        return ControllerResponse.render(
            success=False, message=message, details=details, note=note
        )

    @staticmethod
    def not_found(item_name: str, item_type: str = "element") -> str:
        """Render a 'not found' error response."""
        return ControllerResponse.error(f"{item_type} '{item_name}' not found")

    @staticmethod
    def missing_param(param_name: str) -> str:
        """Render a 'missing parameter' error response."""
        return ControllerResponse.error(f"Missing required parameter: '{param_name}'")

    @staticmethod
    def invalid_param(param_name: str, reason: str | None = None) -> str:
        """Render an 'invalid parameter' error response."""
        msg = f"Invalid parameter: '{param_name}'"
        if reason:
            msg += f" ({reason})"
        return ControllerResponse.error(msg)

    @staticmethod
    def action_result(
        action: str,
        target: str | None = None,
        success: bool = True,
        details: str | None = None,
        note: str | None = None,
    ) -> str:
        """
        Render an action result response.
        
        Args:
            action: The action performed (e.g., "tap", "swipe", "input")
            target: The target element/location
            success: Whether the action succeeded
            details: Optional details
            note: Optional additional note or warning
        """
        if target:
            message = f"Action: {action} on '{target}'"
        else:
            message = f"Action: {action}"

        return ControllerResponse.render(
            success=success, message=message, details=details, note=note
        )

    @staticmethod
    def navigation_result(
        url: str,
        success: bool = True,
        title: str | None = None,
        details: str | None = None
    ) -> str:
        """Render a navigation result response."""
        message = f"Navigated to: {url}"
        if title:
            note = f"Page title: {title}"
        else:
            note = None

        return ControllerResponse.render(
            success=success, message=message, details=details, note=note
        )

    @staticmethod
    def input_result(
        field_name: str,
        value: str | None = None,
        success: bool = True,
        details: str | None = None
    ) -> str:
        """Render an input action result response."""
        if value:
            message = f"Input '{value}' into '{field_name}'"
        else:
            message = f"Cleared input in '{field_name}'"

        return ControllerResponse.render(
            success=success, message=message, details=details
        )

    @staticmethod
    def swipe_result(
        direction: str,
        start: tuple | None = None,
        end: tuple | None = None,
        success: bool = True
    ) -> str:
        """Render a swipe gesture result response."""
        message = f"Swiped {direction}"
        if start and end:
            details = f"From ({start[0]}, {start[1]}) to ({end[0]}, {end[1]})"
        else:
            details = None

        return ControllerResponse.render(
            success=success, message=message, details=details
        )

    @staticmethod
    def tap_result(
        x: int,
        y: int,
        element_name: str | None = None,
        success: bool = True,
        details: str | None = None
    ) -> str:
        """Render a tap action result response."""
        if element_name:
            message = f"Tapped at ({x}, {y}) (resolved from '{element_name}')"
        else:
            message = f"Tapped at ({x}, {y})"

        return ControllerResponse.render(
            success=success, message=message, details=details
        )

    @staticmethod
    def screenshot_result(
        success: bool = True,
        filename: str | None = None,
        error: str | None = None
    ) -> str:
        """Render a screenshot capture result response."""
        if success:
            message = "Screenshot captured"
            note = f"Saved as: {filename}" if filename else None
            return ControllerResponse.success(message=message, note=note)
        else:
            message = "Failed to capture screenshot"
            return ControllerResponse.error(message=message, details=error)

    @staticmethod
    def screenshot_analysis(
        analysis_text: str,
        prompt_used: str | None = None
    ) -> str:
        """Render a screenshot analysis response."""
        details = analysis_text
        note = f"Analysis prompt: {prompt_used}" if prompt_used else None
        return ControllerResponse.success(
            message="Screenshot analysis completed",
            details=details,
            note=note
        )

    @staticmethod
    def connection_result(
        device_id: str,
        connected: bool = True,
        error: str | None = None
    ) -> str:
        """Render a device connection result response."""
        if connected:
            return ControllerResponse.success(f"Connected to device: {device_id}")
        else:
            return ControllerResponse.error(
                f"Failed to connect to device: {device_id}",
                details=error
            )


class PerceptionsFormatter:
    """
    Utility class for formatting perception/display outputs.
    
    Centralizes formatting logic for vision/perceptions.prompt.j2 template
    to eliminate repetitive manual list building across the codebase.
    
    Usage:
        from app.utils.controller_response import PerceptionsFormatter
        
        # Format wiki pages
        return PerceptionsFormatter.wiki_pages(pages)
        
        # Format links
        return PerceptionsFormatter.links(links_raw)
        
        # Format Android devices
        return PerceptionsFormatter.android_devices(devices)
    """

    @staticmethod
    def wiki_pages(pages: list) -> str:
        """Format wiki pages list for display."""
        if not pages:
            return render_template("core/vision/perceptions.prompt.j2", type="wiki_pages", items=[])
        items = [f"{p.title} (slug: {p.slug})" for p in pages]
        return render_template("core/vision/perceptions.prompt.j2", type="wiki_pages", items=items)

    @staticmethod
    def links(links_raw: list) -> str:
        """Format web links for display."""
        return render_template("core/vision/perceptions.prompt.j2", type="links", items=links_raw)

    @staticmethod
    def android_devices(devices: list) -> str:
        """Format Android device list for display."""
        if not devices:
            return render_template("core/vision/perceptions.prompt.j2", type="android_devices", items=[])
        items = [f"{d['serial']} ({d['status']}) {d['info']}" for d in devices]
        return render_template("core/vision/perceptions.prompt.j2", type="android_devices", items=items)

    @staticmethod
    def cookies(cookies_list: list) -> str:
        """Format browser cookies for display."""
        return render_template("core/vision/perceptions.prompt.j2", type="cookies", items=cookies_list)

    @staticmethod
    def tools_used(tools_used: set | list) -> str:
        """Format tool usage summary for display."""
        if not tools_used:
            return render_template("core/vision/perceptions.prompt.j2", type="tools_used", items=[])
        return render_template("core/vision/perceptions.prompt.j2", type="tools_used", items=sorted(tools_used))

    @staticmethod
    def ui_elements(elements: list, max_items: int = 50) -> str:
        """Format UI elements for display."""
        return render_template("core/vision/perceptions.prompt.j2", type="ui_elements", items=elements, max_items=max_items)


class SystemToolsFormatter:
    """
    Utility class for formatting system tools outputs.
    
    Centralizes formatting for events/system_tools.prompt.j2 template
    used by checkpoint tools, scheduler, and system utilities.
    
    Usage:
        from app.utils.controller_response import SystemToolsFormatter
        
        # Format checkpoints
        return SystemToolsFormatter.checkpoints(checkpoint_list)
        
        # Format autonomous tasks
        return SystemToolsFormatter.autonomous_tasks(tasks)
        
        # Format signals
        return SystemToolsFormatter.signals(["Message 1", "Message 2"])
    """

    @staticmethod
    def checkpoints(checkpoints: list) -> str:
        """Format checkpoint list for display."""
        cp_data = []
        for cp in checkpoints:
            auto_tag = " [AUTO]" if getattr(cp, 'created_by', None) == "auto" else ""
            status = "MANUAL" if getattr(cp, 'created_by', None) == "manual" else "AUTO"
            cp_data.append({
                "id": getattr(cp, 'id', 0),
                "status": status,
                "name": f"{getattr(cp, 'name', 'Unknown')}{auto_tag}",
                "time": getattr(cp, 'created_at', None) and cp.created_at.strftime('%Y-%m-%d %H:%M') or ""
            })
        return render_template("common/events/system_tools.prompt.j2", checkpoints=cp_data)

    @staticmethod
    def autonomous_tasks(tasks: list) -> str:
        """Format autonomous task list for display."""
        cp_data = []
        for t in tasks:
            status = "DLQ" if t.is_dead_letter else ("Active" if t.is_active else "Paused")
            cp_data.append({
                "id": t.id,
                "status": status,
                "name": t.intent_description[:50],
                "time": f"Next: {t.next_run_at or 'Unknown'}"
            })
        return render_template("common/events/system_tools.prompt.j2", checkpoints=cp_data)

    @staticmethod
    def task_health(task) -> str:
        """Format single task health status."""
        status = "Dead Letter (Disabled)" if task.is_dead_letter else ("Active" if task.is_active else "Paused")
        cp_data = [{
            "id": task.id,
            "status": status,
            "name": task.intent_description,
            "time": f"Last: {task.last_run_at} | Failure: {task.last_failure_reason or 'None'}"
        }]
        return render_template("common/events/system_tools.prompt.j2", checkpoints=cp_data)

    @staticmethod
    def signals(messages: list[str]) -> str:
        """Format signal messages for display."""
        signal_data = [{"message": m} for m in messages]
        return render_template("common/events/system_tools.prompt.j2", signals=signal_data)

    @staticmethod
    def rollback_preview(checkpoint_id: int, checkpoint_name: str) -> str:
        """Format rollback preview for display."""
        return render_template("common/events/system_tools.prompt.j2",
                               rollback_preview={"id": checkpoint_id, "name": checkpoint_name})

    @staticmethod
    def checkpoint_creation(checkpoint, total_size: int, total_lines: int) -> str:
        """Format checkpoint creation result."""
        cp_data = [{
            "id": checkpoint.id,
            "status": "SUCCESS",
            "name": checkpoint.name,
            "time": f"{total_size:,} bytes | {total_lines:,} lines"
        }]
        return render_template("common/events/system_tools.prompt.j2", checkpoints=cp_data)

    @staticmethod
    def app_rankings(records: list, platform: str) -> str:
        """Format app usage rankings for display."""
        cp_data = []
        for r in records:
            status = " [RUNNING]" if getattr(r, 'is_running', False) else ""
            cp_data.append({
                "id": 0,
                "name": f"{getattr(r, 'app_name', 'Unknown')} ({getattr(r, 'bundle_id', 'N/A')})",
                "status": f"Score {getattr(r, 'priority_score', 0):.2f}{status}",
                "time": platform
            })
        return render_template("common/events/system_tools.prompt.j2", checkpoints=cp_data)


class ProjectManagementFormatter:
    """
    Utility class for formatting project management outputs.
    
    Centralizes formatting for project/project_management.prompt.j2 template.
    
    Usage:
        from app.utils.controller_response import ProjectManagementFormatter
        
        # Format episodes list
        return ProjectManagementFormatter.episodes(episodes)
        
        # Format architecture info
        return ProjectManagementFormatter.architecture_summary(info)
    """

    @staticmethod
    def checklist(items: list, status_key: str = None, name_key: str = "name") -> str:
        """
        Format items as a checklist.
        
        Args:
            items: List of items to format
            status_key: Optional key to extract status (will show FAILED if truthy, SUCCESS otherwise)
            name_key: Key to extract item name
        """
        checklist = []
        for item in items:
            if status_key:
                status = "FAILED" if item.get(status_key) else "SUCCESS"
                checklist.append(f"[{status}] {item.get(name_key, 'Unknown')}")
            else:
                checklist.append(str(item))
        return render_template("domain/project/project_management.prompt.j2", checklist=checklist)

    @staticmethod
    def episodes(episodes: list) -> str:
        """Format memory episodes for display."""
        checklist = []
        for ep in episodes:
            status = "FAILED" if ep.get("error") else "SUCCESS"
            checklist.append(f"[{status}] {ep.get('goal', 'Unknown')}")
        return render_template("domain/project/project_management.prompt.j2", checklist=checklist)

    @staticmethod
    def architecture_summary(info: dict) -> str:
        """Format architecture information for display."""
        checklist = [f"Summary: {info.get('summary', 'N/A')}"]
        for sub in info.get("sub_modules", []):
            checklist.append(f"Module {sub.get('name', 'Unknown')}: {sub.get('summary', '')[:100]}...")
        for dep in info.get("dependencies", []):
            checklist.append(f"Depends on {dep.get('target', 'Unknown')}")
        return render_template("domain/project/project_management.prompt.j2", checklist=checklist)

    @staticmethod
    def concepts(results: list) -> str:
        """Format concept search results for display."""
        checklist = []
        for r in results:
            scope = "[Global]" if r.score == 0 else ""
            item = f"{r.name} {scope} (Score: {r.score:.2f}): {r.description}"
            if r.files:
                basenames = [f.split("/")[-1] for f in r.files]
                item += f" | Related: {', '.join(basenames)}"
            checklist.append(item)
        return render_template("domain/project/project_management.prompt.j2", checklist=checklist)


class SkillResponse:

    @staticmethod
    def success(skill_name: str, extracted_data: dict[str, Any] | None = None) -> str:
        """Render a skill success response."""
        details = None
        if extracted_data:
            details = render_template(
                "core/vision/perceptions.prompt.j2",
                extracted_data=extracted_data
            )

        return ControllerResponse.success(
            message=f"Skill '{skill_name}' completed",
            details=details
        )

    @staticmethod
    def error(
        skill_name: str,
        message: str,
        fallback_context: dict[str, Any] | None = None,
        suggestions: list | None = None
    ) -> str:
        """Render a skill error response with optional fallback details."""
        details = None
        if fallback_context:
            failed_step = fallback_context.get("failed_step", {})
            error_message = fallback_context.get("error_message", message)
            details = render_template(
                "common/events/skill_error_details.prompt.j2",
                failed_step=failed_step,
                error_message=error_message,
                suggestions=suggestions or []
            )

        return ControllerResponse.error(
            message=f"Skill '{skill_name}' failed: {message}",
            details=details
        )

    @staticmethod
    def cancelled(skill_name: str, reason: str | None = None) -> str:
        """Render a skill cancellation response."""
        msg = f"Skill '{skill_name}' was cancelled"
        if reason:
            msg += f": {reason}"
        return ControllerResponse.error(message=msg)


class ContentFormatter:
    """
    Utility class for formatting content displays.
    
    Handles formatting for file contents, documents, spreadsheets, todos, etc.
    Eliminates hardcoded string concatenation for content presentation.
    
    Usage:
        from app.utils.controller_response import ContentFormatter
        
        # Format code file
        return ContentFormatter.file_content(filename, content, lang)
        
        # Format spreadsheet
        return ContentFormatter.spreadsheet(filename, sheets)
        
        # Format todo list
        return ContentFormatter.todo_list(todos)
    """

    @staticmethod
    def file_content(filename: str, content: str, lang: str = None, has_header: bool = False) -> str:
        """Format file content with optional syntax highlighting."""
        # Auto-detect language if not provided
        if not lang and filename:
            lang = detect_language(filename)

        return render_template(
            "domain/project/file_content.prompt.j2",
            filename=filename,
            content=content,
            lang=lang or "text",
            has_header=has_header
        )

    @staticmethod
    def spreadsheet(filename: str, sheets: list) -> str:
        """Format spreadsheet content with multiple sheets."""
        return render_template(
            "domain/project/spreadsheet_content.prompt.j2",
            filename=filename,
            sheets=sheets
        )

    @staticmethod
    def todo_list(todos: list, title: str = None) -> str:
        """Format todo list for display."""
        todo_data = []
        for t in todos:
            todo_data.append({
                "status": t.status,
                "title": t.title,
                "id": t.id,
                "due_date": t.due_date,
            })
        return render_template(
            "common/events/todo_list.prompt.j2",
            todos=todo_data,
            title=title
        ), {"count": len(todo_data)}

    @staticmethod
    def web_search_results(query: str, results: list) -> str:
        """Format web search results."""
        return render_template(
            "common/events/search_results.prompt.j2",
            query=query,
            results=results,
            result_type="web"
        ), {"count": len(results)}

    @staticmethod
    def chat_search_results(query: str, results: list) -> str:
        """Format chat history search results."""
        formatted_results = []
        for msg in results:
            role = "User" if msg.type == "human" else "Assistant"
            content = msg.content
            preview = content[:200] + "..." if len(content) > 200 else content
            formatted_results.append({"role": role, "content": preview})

        return render_template(
            "common/events/search_results.prompt.j2",
            query=query,
            results=formatted_results,
            result_type="chat"
        ), {"count": len(formatted_results)}

