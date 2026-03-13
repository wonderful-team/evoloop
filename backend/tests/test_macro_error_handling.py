import asyncio
import logging
import unittest.mock
import sys

from app.core.execution.macro.service import MacroService

# Mock settings to avoid Pydantic validation errors during test execution
mock_settings = unittest.mock.MagicMock()
mock_settings.PROJECT_NAME = "EvoLoop"
mock_settings.WORKER_AGENT_MAX_STEPS = 10
sys.modules["app.core.config"] = unittest.mock.MagicMock(settings=mock_settings)


logging.basicConfig(level=logging.DEBUG)

mock_macro = [
    {
        'step_number': 1,
        'type': 'action',
        'event_type': 'navigate',
        'source': 'dom',
        'payload': {'url': 'https://www.baidu.com/'}
    },
    {
        'step_number': 2,
        'type': 'action',
        'event_type': 'wait',
        'source': 'dom',
        'payload': {'seconds': 1}
    },
    {
        'step_number': 3,
        'type': 'action',
        'event_type': 'click',
        'source': 'dom',
        'target_selector': '#non-existent-id',
        'payload': {
            'timeout_ms': 1000,
            'continue_on_error': True
        }
    }
]

async def run_test():
    print("--- Starting Standardized MacroService Error Handling Test ---")
    result = await MacroService.run("test_thread_999", mock_macro, {})
    
    status = result.get('status')
    msg = result.get('message', '')
    
    print(f"\nFinal Result -> Status: {status}")
    if status != 'success':
        print(f"Error Message: {msg}")

if __name__ == "__main__":
    asyncio.run(run_test())
