import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import BaseModel, Field, ValidationError

from app.core.llm import InternalLLMService

class MockResponseSchema(BaseModel):
    summary: str
    is_completed: bool

@pytest.mark.asyncio
async def test_invoke_structured_fallback_validation_error():
    """
    Test that when structured_llm.ainvoke raises ValidationError (due to markdown-wrapped JSON),
    InternalLLMService extracts the input string directly from ValidationError,
    successfully parses and validates it, without re-invoking the LLM.
    """
    # 1. Manually trigger a ValidationError with markdown-wrapped JSON
    invalid_json_str = "```json\n{\n  \"summary\": \"Task finished successfully.\",\n  \"is_completed\": true\n}\n```"
    try:
        MockResponseSchema.model_validate_json(invalid_json_str)
    except ValidationError as exc:
        validation_error = exc

    # 2. Mock structured_llm and default_llm
    # We want structured_llm.ainvoke to raise our validation_error
    structured_llm_mock = AsyncMock()
    structured_llm_mock.ainvoke.side_effect = validation_error

    llm_mock = MagicMock()
    # If the optimization works, llm_mock.ainvoke SHOULD NOT be called at all!
    llm_mock.ainvoke = AsyncMock()
    llm_mock.ainvoke.return_value = MagicMock(content="should not be called")
    llm_mock.with_structured_output = MagicMock(return_value=structured_llm_mock)

    # 3. Patch get_default_llm to return our mocked LLM
    with patch("app.infrastructure.llm.factory.get_default_llm", AsyncMock(return_value=llm_mock)):
        result = await InternalLLMService.invoke_structured(
            messages=[{"role": "user", "content": "hello"}],
            output_schema=MockResponseSchema,
            purpose="test_fallback",
            model_name="mock-model"
        )

        # 4. Verify result matches the input we extracted
        assert result.summary == "Task finished successfully."
        assert result.is_completed is True

        # 5. Verify structured_llm.ainvoke was called, but llm_mock.ainvoke (fallback API call) WAS NOT called
        structured_llm_mock.ainvoke.assert_called_once()
        llm_mock.ainvoke.assert_not_called()

@pytest.mark.asyncio
async def test_invoke_structured_fallback_re_invoke_llm():
    """
    Test that when a non-ValidationError (or ValidationError without string input) is raised,
    it falls back to re-invoking the LLM as a safety net.
    """
    structured_llm_mock = AsyncMock()
    structured_llm_mock.ainvoke.side_effect = ValueError("Some parsing error without Pydantic validation")

    llm_mock = MagicMock()
    llm_mock.ainvoke = AsyncMock()
    # The fallback LLM call should return the valid JSON inside markdown
    llm_mock.ainvoke.return_value = MagicMock(content="```json\n{\n  \"summary\": \"Fallback worked.\",\n  \"is_completed\": false\n}\n```")
    llm_mock.with_structured_output = MagicMock(return_value=structured_llm_mock)

    with patch("app.infrastructure.llm.factory.get_default_llm", AsyncMock(return_value=llm_mock)):
        result = await InternalLLMService.invoke_structured(
            messages=[{"role": "user", "content": "hello"}],
            output_schema=MockResponseSchema,
            purpose="test_fallback_re_invoke",
            model_name="mock-model"
        )

        assert result.summary == "Fallback worked."
        assert result.is_completed is False

        # Both structured_llm.ainvoke and llm_mock.ainvoke should be called
        structured_llm_mock.ainvoke.assert_called_once()
        llm_mock.ainvoke.assert_called_once()

class KnowledgeItem(BaseModel):
    title: str
    content: str

class DynamicVerdictMock(BaseModel):
    summary: str
    is_completed: bool
    knowledge: list[KnowledgeItem] = Field(default_factory=list)

@pytest.mark.asyncio
async def test_invoke_structured_coercion():
    """
    Test that coercion (auto-healing) successfully:
    1. Converts a list of strings into a list of models with coerced fields.
    2. Fills in missing required fields (is_completed, summary) with default values.
    """
    # 1. Trigger validation error with incomplete data and wrong type
    bad_json_str = '```json\n{\n  "knowledge": [\n    "Item 1: Multi-turn memory",\n    "Item 2: Verification status"\n  ]\n}\n```'
    try:
        DynamicVerdictMock.model_validate_json(bad_json_str)
    except ValidationError as exc:
        validation_error = exc

    # 2. Mock structured_llm to raise the ValidationError
    structured_llm_mock = AsyncMock()
    structured_llm_mock.ainvoke.side_effect = validation_error

    llm_mock = MagicMock()
    llm_mock.ainvoke = AsyncMock()
    llm_mock.with_structured_output = MagicMock(return_value=structured_llm_mock)

    # 3. Patch get_default_llm to return our mocked LLM
    with patch("app.infrastructure.llm.factory.get_default_llm", AsyncMock(return_value=llm_mock)):
        result = await InternalLLMService.invoke_structured(
            messages=[{"role": "user", "content": "hello"}],
            output_schema=DynamicVerdictMock,
            purpose="test_coercion",
            model_name="mock-model"
        )

        # 4. Verify validation passed and data was successfully coerced/auto-healed.
        # Generic coercion puts the raw string into the FIRST required str field of the
        # item model (KnowledgeItem.title), and fills the remaining required str fields
        # with zero-values (""). No hardcoded field names or default strings are used.
        assert result.is_completed is False
        assert result.summary == ""
        assert len(result.knowledge) == 2
        # "title" is the first declared required str field → receives the raw string value
        assert result.knowledge[0].title == "Item 1: Multi-turn memory"
        # "content" is the second required str field → zero-value ""
        assert result.knowledge[0].content == ""
        assert result.knowledge[1].title == "Item 2: Verification status"
        assert result.knowledge[1].content == ""

        structured_llm_mock.ainvoke.assert_called_once()
        llm_mock.ainvoke.assert_not_called()
