
from typing import Dict, Any, List
from langchain_core.messages import HumanMessage

class EventAdapter:
    @staticmethod
    def adapt(source: str, event_type: str, payload: Dict[str, Any]) -> List[HumanMessage]:
        """
        Convert external event payload into LangChain messages.
        """
        if source == "niushop":
            return EventAdapter._adapt_niushop(event_type, payload)
        elif source == "gitlab":
            return EventAdapter._adapt_gitlab(event_type, payload)
        else:
            # Default fallback
            return [HumanMessage(content=f"Received unknown event from {source}: {payload}")]

    @staticmethod
    def _adapt_niushop(event_type: str, payload: Dict[str, Any]) -> List[HumanMessage]:
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
    def _adapt_gitlab(event_type: str, payload: Dict[str, Any]) -> List[HumanMessage]:
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
