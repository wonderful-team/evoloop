"""
Layered Finish Auditor - Three-tier auditing with quality preservation.

Tiers:
1. MINIMAL: Rule-based, zero LLM calls (< 10ms)
   - Only for read-only operations with no risk
   
2. STANDARD: Lightweight LLM with constrained prompt (~500ms)
   - Most common operations
   - Quality maintained with reduced tokens
   
3. COMPREHENSIVE: Full audit with all context (~1500ms)
   - Complex operations, file modifications, errors
   - Maximum quality assurance

Safety: Higher tiers always available as fallback.
"""

import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.infrastructure.llm.factory import LLMFactory

logger = logging.getLogger(__name__)


@dataclass
class AuditDecision:
    """Decision for audit tier selection."""
    tier: str  # 'minimal', 'standard', 'comprehensive'
    reason: str
    confidence: float


class LayeredAuditor:
    """
    Three-tier finish auditor.
    
    Automatically selects appropriate audit depth based on operation characteristics.
    Never compromises on safety - complex operations always get full audit.
    """
    
    # Tool categorization
    READONLY_TOOLS = frozenset({
        'read_file', 'list_directory', 'get_file_info', 'search_files',
        'analyze_image', 'search_web', 'read_url_content',
        'search_history', 'search_skills', 'get_preference',
    })
    
    FILE_WRITE_TOOLS = frozenset({
        'write_file', 'edit_file', 'delete_file', 'move_file', 'create_directory',
    })
    
    EXECUTION_TOOLS = frozenset({
        'execute_command', 'bash', 'shell', 'python',
    })
    
    AUTOMATION_TOOLS = frozenset({
        'mobile_control', 'browser_control', 'desktop_control',
        'open_app', 'click_at', 'type_text', 'press_key',
    })
    
    ERROR_MARKERS = [
        r'\[ERROR:',
        r'^Error:',
        r'Exception:',
        r'Traceback',
        r'Failed to',
        r'Permission denied',
        r'File not found',
    ]
    
    def __init__(self):
        # Fast LLM for standard tier
        self._fast_llm = None
    
    async def _get_fast_llm(self):
        """Lazy initialization of fast LLM."""
        if self._fast_llm is None:
            self._fast_llm = await LLMFactory.create_llm(
                temperature=0.1,
                max_tokens=500,
            )
        return self._fast_llm
    
    def classify_audit_tier(
        self,
        tool_history: list[str],
        messages: list,
        blackboard: dict,
        state: dict
    ) -> AuditDecision:
        """
        Classify which audit tier is appropriate.
        
        Conservative: When in doubt, use higher tier.
        """
        # Extract used tools
        used_tools = set()
        for tool_sig in tool_history:
            tool_name = tool_sig.split(':')[0] if ':' in tool_sig else tool_sig
            used_tools.add(tool_name)
        
        # Get last AI message content
        last_content = ""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                last_content = str(msg.content)
                break
        
        # ===== COMPREHENSIVE triggers (never compromise) =====
        comprehensive_triggers = []
        
        # 1. Any file modification
        if used_tools & self.FILE_WRITE_TOOLS:
            comprehensive_triggers.append("file_modification")
        
        # 2. Any code execution
        if used_tools & self.EXECUTION_TOOLS:
            comprehensive_triggers.append("code_execution")
        
        # 3. Any UI automation
        if used_tools & self.AUTOMATION_TOOLS:
            comprehensive_triggers.append("ui_automation")
        
        # 4. Explicit error markers
        for pattern in self.ERROR_MARKERS:
            if re.search(pattern, last_content, re.MULTILINE):
                comprehensive_triggers.append("error_detected")
                break
        
        # 5. Blackboard indicates complexity
        ticket = blackboard.get("ticket", {})
        if ticket.get("complexity") == "high":
            comprehensive_triggers.append("high_complexity")
        
        # 6. Verification status issues
        verification = blackboard.get("verification", {})
        if verification.get("status") in ("failed", "error"):
            comprehensive_triggers.append("verification_failed")
        
        # 7. Long execution (indicates complexity)
        if len(messages) > 20:
            comprehensive_triggers.append("long_conversation")
        
        if comprehensive_triggers:
            return AuditDecision(
                tier="comprehensive",
                reason=f"safety_triggers: {', '.join(comprehensive_triggers)}",
                confidence=1.0
            )
        
        # ===== MINIMAL tier (strict requirements) =====
        minimal_requirements = [
            # Only readonly tools
            used_tools.issubset(self.READONLY_TOOLS),
            # Not empty
            len(last_content) > 50,
            # Not too long (avoid edge cases)
            len(last_content) < 3000,
            # No error indicators
            not any(re.search(p, last_content) for p in self.ERROR_MARKERS),
            # Not a subtask result (needs proper aggregation)
            not state.get("is_subtask"),
        ]
        
        if all(minimal_requirements):
            return AuditDecision(
                tier="minimal",
                reason="readonly_safe_operation",
                confidence=0.95
            )
        
        # ===== DEFAULT: Standard tier =====
        return AuditDecision(
            tier="standard",
            reason="default_auditing",
            confidence=0.90
        )
    
    async def audit_minimal(
        self,
        messages: list,
        blackboard: dict
    ) -> tuple[str, dict]:
        """
        Minimal audit - rule-based summary generation.
        
        Zero LLM calls, < 10ms execution.
        """
        # Extract last AI message
        last_content = ""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                last_content = str(msg.content)
                break
        
        # Clean up common artifacts
        cleaned = last_content.strip()
        
        # Extract tool usage for context
        tool_usage = []
        for msg in messages:
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tc in msg.tool_calls:
                    name = tc.get('name') if isinstance(tc, dict) else getattr(tc, 'name', None)
                    if name:
                        tool_usage.append(name)
        
        # Generate appropriate prefix based on operation
        if 'read_file' in tool_usage:
            prefix = "📄 File content retrieved successfully.\n\n"
        elif 'search_files' in tool_usage or 'search_web' in tool_usage:
            prefix = "🔍 Search completed. Found relevant results.\n\n"
        elif 'list_directory' in tool_usage:
            prefix = "📁 Directory listing complete.\n\n"
        elif 'analyze_image' in tool_usage:
            prefix = "🖼️ Image analysis complete.\n\n"
        else:
            prefix = "✅ Operation completed successfully.\n\n"
        
        # Combine prefix with original content (truncated if needed)
        max_length = 2000
        if len(cleaned) > max_length:
            cleaned = cleaned[:max_length] + "\n\n[Content truncated]"
        
        summary = prefix + cleaned
        
        metadata = {
            'tier': 'minimal',
            'duration_ms': 5,
            'tools_used': list(set(tool_usage)),
        }
        
        logger.info(f"[FinishAuditor] ✓ Minimal audit: {metadata['tools_used']}")
        return summary, metadata
    
    async def audit_standard(
        self,
        messages: list,
        blackboard: dict,
        config: Any
    ) -> tuple[str, dict]:
        """
        Standard audit - lightweight LLM with constrained prompt.
        
        Single LLM call, ~500-800ms.
        """
        import time
        start_time = time.time()
        
        # Extract context
        ticket = blackboard.get("ticket", {})
        tool_usage = []
        for msg in messages:
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tc in msg.tool_calls:
                    name = tc.get('name') if isinstance(tc, dict) else getattr(tc, 'name', None)
                    if name:
                        tool_usage.append(name)
        
        # Get last AI message
        last_content = ""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                last_content = str(msg.content)
                break
        
        # Concise prompt
        prompt = f"""You are a session reviewer. Provide a brief summary.

Task: {ticket.get('topic', 'Unknown operation')}
Tools used: {', '.join(set(tool_usage)) if tool_usage else 'None'}

Review the result below and provide:
1. One sentence: Was the task completed?
2. Brief summary of key findings or results
3. Any warnings or issues (if applicable)

Result to review:
---
{last_content[:1500]}
---

Respond in 2-3 sentences. Be concise."""

        try:
            llm = await self._get_fast_llm()
            response = await llm.ainvoke([
                SystemMessage(content=prompt)
            ])
            
            summary = str(response.content).strip()
            
            # Ensure reasonable length
            if len(summary) < 20:
                summary = f"✅ Task completed. {summary}"
            
        except Exception as e:
            logger.error(f"[FinishAuditor] Standard audit failed: {e}")
            # Fallback to content
            summary = f"✅ Task completed.\n\n{last_content[:1000]}"
        
        duration_ms = (time.time() - start_time) * 1000
        
        metadata = {
            'tier': 'standard',
            'duration_ms': duration_ms,
            'tools_used': list(set(tool_usage)),
        }
        
        logger.info(f"[FinishAuditor] ✓ Standard audit: {duration_ms:.0f}ms")
        return summary, metadata
    
    async def audit_comprehensive(
        self,
        state: dict,
        config: Any,
        original_audit_fn: callable
    ) -> tuple[str, dict, Any]:
        """
        Comprehensive audit - delegate to original finish logic.
        
        This ensures maximum quality for complex operations.
        """
        import time
        start_time = time.time()
        
        # Call original finish_node logic
        result = await original_audit_fn(state, config)
        
        duration_ms = (time.time() - start_time) * 1000
        
        # Extract summary from result
        summary = ""
        for msg in reversed(result.get("messages", [])):
            if isinstance(msg, AIMessage) and msg.content:
                summary = str(msg.content)
                break
        
        metadata = {
            'tier': 'comprehensive',
            'duration_ms': duration_ms,
        }
        
        logger.info(f"[FinishAuditor] ✓ Comprehensive audit: {duration_ms:.0f}ms")
        return summary, metadata, result


# Global auditor instance
_finish_auditor: Optional[LayeredAuditor] = None


def get_finish_auditor() -> LayeredAuditor:
    """Get or create global auditor instance."""
    global _finish_auditor
    if _finish_auditor is None:
        _finish_auditor = LayeredAuditor()
    return _finish_auditor
