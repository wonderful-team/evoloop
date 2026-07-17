from app.utils.text import extract_json_from_markdown
import json
from jinja2 import Template
from pydantic import BaseModel, Field
from typing import Any

print('=============================================')
print('TEST 1: strict=False Control Character JSON Parsing')
content = """```json
[
  {
    "id": "task_1",
    "description": "First line
Second line without escape"
  }
]
```"""
try:
    json_str = extract_json_from_markdown(content)
    obj = json.loads(json_str, strict=False)
    print('[PASSED] Successfully parsed unescaped newlines:', obj[0]['description'].replace('\n', '\\n'))
except Exception as e:
    print('[FAILED]', e)

print('\n=============================================')
print('TEST 2: Pydantic Context Rendering via model_dump().items()')

class WorkerConfig(BaseModel):
    context: dict[str, Any] = Field(default_factory=dict)
    tools: list[str] = Field(default_factory=list)

config = WorkerConfig(
    context={'target_file': '/Users/demo/test.xlsx', 'year': 2026},
    tools=['read_file', 'execute_command']
)

template_str = """
[Context Parameters]
{% for key, value in subtask_context.model_dump().items() -%}
- {{ key }}: {{ value }}
{% endfor %}

[Assigned Tools]
{% for tool in tools -%}
- {{ tool }}
{% endfor %}
"""

try:
    rendered = Template(template_str).render(
        subtask_context=config,
        tools=config.tools
    )
    print('[PASSED] Rendered Result:')
    print(rendered.strip())
except Exception as e:
    print('[FAILED]', e)
print('=============================================')
