from typing import Any

from app.core.engine.message.native_classes import HumanMessage


class EventAdapter:
    @staticmethod
    def adapt(
        source: str, event_type: str, payload: dict[str, Any]
    ) -> list[HumanMessage]:
        """
        Convert external event payload into native messages.
        """
        if source == "niushop":
            return EventAdapter._adapt_niushop(event_type, payload)
        elif source == "gitlab":
            return EventAdapter._adapt_gitlab(event_type, payload)
        elif source == "crawler":
            return EventAdapter._adapt_crawler(event_type, payload)
        else:
            # Default fallback
            return [
                HumanMessage(content=f"Received unknown event from {source}: {payload}")
            ]

    @staticmethod
    def _adapt_crawler(event_type: str, payload: dict[str, Any]) -> list[HumanMessage]:
        error_type = payload.get("error_type", "Unknown")
        url = payload.get("url", "N/A")
        message = payload.get("message", "")
        severity = payload.get("severity", "medium")

        # 提取关键上下文
        page_state = payload.get("page_state") or {}
        snapshot = payload.get("page_snapshot") or {}

        content = f"""
        **System Notification**: Crawler Error Detected [{severity.upper()}]
        **Error Type**: {error_type}
        **Target URL**: {url}
        
        **Error Message**:
        {message}
        
        **Page Diagnostics**:
        - Title: {page_state.get("title", "N/A")}
        - Status Code: {page_state.get("status_code", "N/A")}
        - Content Length: {page_state.get("page_size_bytes", 0)} bytes
        - DOM Elements: {snapshot.get("visible_elements_count", 0)}
        
        **Mission**:
        The crawler encountered a failure that requires intelligent diagnosis. 
        Please analyze the error context, snapshots, and screenshots provided to identify the root cause.
        
        **Verification & Reliability Protocol**:
        As a "Field Guidance" Agent, your solution must be high-confidence. Follow these steps:
        1. **Locate Suspension**: Use the `list_suspensions` MCP tool to find the corresponding suspended session using the target URL or Job ID (if available).
        2. **Inner Monologue Analysis**: Simulate and reconstruct the provided DOM snippet in your reasoning. Identify exactly why the current selector or logic failed.
        3. **Formulate Solution**: Prepare a Sandbox payload (JavaScript preferred) that can:
            - Execute safely inside the browser (include try/catch).
            - Bypass the error, extract the required data, or return a state update.
            - Ensure no side effects beyond the crawl scope.
        4. **Inject Resolution**: Use the `resolve_suspension` MCP tool to inject your sandbox code into the suspended session, fixing the error and resuming the job.
        
        **Your Goal**: Restore gathering capability with minimal trial-and-error using the interactive resolution tools.
        """
        return [HumanMessage(content=content.strip())]

    @staticmethod
    def _adapt_niushop(event_type: str, payload: dict[str, Any]) -> list[HumanMessage]:
        task_id = payload.get("id", "Unknown")
        title = payload.get("title", "")
        desc = payload.get("description", "")

        content = f"""
        **System Notification**: NiuShop Task Assigned
        **Task ID**: {task_id}
        **Title**: {title}
        **Description**:
        {desc}

        Please analyze this task and start execution.
        """
        return [HumanMessage(content=content)]

    @staticmethod
    def _adapt_gitlab(event_type: str, payload: dict[str, Any]) -> list[HumanMessage]:
        # Simplify GitLab webhook payload
        object_attr = payload.get("object_attributes", {})
        title = object_attr.get("title", "")
        desc = object_attr.get("description", "")
        url = object_attr.get("url", "")

        content = f"""
        **System Notification**: GitLab Issue Created
        **Title**: {title}
        **URL**: {url}
        **Description**:
        {desc}

        Please fix this issue.
        """
        return [HumanMessage(content=content)]
