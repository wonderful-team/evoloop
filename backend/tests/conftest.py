"""
Pytest configuration for EvoLoop Backend tests.

This module mocks heavy dependencies that are not available in the test environment.
"""
import sys
from unittest.mock import MagicMock


# Create comprehensive mocks for heavy dependencies
def _create_mock_modules():
    """Create mock modules for dependencies that may not be installed."""
    
    # Mock langchain_core - need to create a proper module structure
    # Using MagicMock for submodules
    mock_langchain_core = MagicMock()
    
    # messages submodule
    mock_langchain_core.messages = MagicMock()
    mock_langchain_core.messages.HumanMessage = MagicMock
    mock_langchain_core.messages.AIMessage = MagicMock
    mock_langchain_core.messages.BaseMessage = MagicMock
    mock_langchain_core.messages.SystemMessage = MagicMock
    mock_langchain_core.messages.ToolMessage = MagicMock
    mock_langchain_core.messages.RemoveMessage = MagicMock
    
    # runnables submodule
    mock_langchain_core.runnables = MagicMock()
    mock_langchain_core.runnables.RunnableConfig = dict
    
    # callbacks submodule
    mock_langchain_core.callbacks = MagicMock()
    mock_langchain_core.callbacks.manager = MagicMock()
    mock_langchain_core.callbacks.manager.CallbackManagerForLLMRun = MagicMock
    
    # outputs submodule
    mock_langchain_core.outputs = MagicMock()
    mock_langchain_core.outputs.ChatResult = MagicMock
    mock_langchain_core.outputs.ChatGeneration = MagicMock
    mock_langchain_core.outputs.Generation = MagicMock
    mock_langchain_core.outputs.LLMResult = MagicMock
    
    # language_models submodule
    mock_langchain_core.language_models = MagicMock()
    mock_langchain_core.language_models.BaseChatModel = MagicMock
    mock_langchain_core.language_models.LanguageModelInput = MagicMock
    mock_langchain_core.language_models.LanguageModelOutput = MagicMock
    
    # tools submodule
    mock_langchain_core.tools = MagicMock()
    
    # Create a proper tool decorator that preserves async functions
    def mock_tool_decorator(*args, **kwargs):
        def decorator(func):
            return func
        # Handle both @tool and @tool() syntax
        if args and callable(args[0]):
            return args[0]
        return decorator
    
    mock_langchain_core.tools.tool = mock_tool_decorator
    mock_langchain_core.tools.BaseTool = MagicMock
    mock_langchain_core.tools.Tool = MagicMock
    mock_langchain_core.tools.structured_tool = MagicMock()
    
    # Mock langgraph
    mock_langgraph = MagicMock()
    mock_langgraph.graph = MagicMock()
    mock_langgraph.graph.END = "END"
    mock_langgraph.graph.StateGraph = MagicMock
    
    # Mock langgraph.graph.message
    mock_graph_message = MagicMock()
    
    def add_messages_reducer(existing, new):
        """Reducer function for messages."""
        if existing is None:
            existing = []
        if isinstance(new, list):
            return existing + new
        return existing + [new]
    
    mock_graph_message.add_messages = add_messages_reducer
    mock_langgraph.graph.message = mock_graph_message
    
    # Mock pgvector
    mock_pgvector = MagicMock()
    mock_pgvector.sqlalchemy = MagicMock()
    
    # Create a proper Vector class that mimics pgvector.sqlalchemy.Vector
    # It needs to inherit from SQLAlchemy's UserDefinedType to work in mapped_column
    try:
        from sqlalchemy.types import UserDefinedType
        from sqlalchemy.sql.type_api import TypeEngine
        
        class MockVector(UserDefinedType):
            """Mock pgvector Vector type for testing."""
            
            def __init__(self, dimensions=None):
                self.dimensions = dimensions
            
            def get_col_spec(self, **kw):
                return f"VECTOR({self.dimensions})" if self.dimensions else "VECTOR"
            
            @property
            def python_type(self):
                return list
            
            def compare_values(self, x, y):
                return x == y
    except ImportError:
        # Fallback if SQLAlchemy is not available
        class MockVector:
            def __init__(self, dimensions=None):
                self.dimensions = dimensions
    
    mock_pgvector.sqlalchemy.Vector = MockVector
    
    # Mock pgvector.sqlalchemy
    mock_pgvector_sqlalchemy = MagicMock()
    mock_pgvector_sqlalchemy.Vector = MockVector
    
    # Mock neo4j
    mock_neo4j = MagicMock()
    
    # Mock torch
    mock_torch = MagicMock()
    mock_torch.Tensor = MagicMock
    mock_torch.tensor = MagicMock
    
    # Mock transformers
    mock_transformers = MagicMock()
    
    # Mock sentence_transformers
    mock_sentence_transformers = MagicMock()
    
    # Mock celery
    mock_celery = MagicMock()
    mock_celery.Celery = MagicMock
    mock_celery.shared_task = MagicMock
    
    # Mock jwt (PyJWT)
    mock_jwt = MagicMock()
    mock_jwt.encode = MagicMock(return_value="mock_token")
    mock_jwt.decode = MagicMock(return_value={"sub": "test"})
    mock_jwt.ExpiredSignatureError = Exception
    mock_jwt.InvalidTokenError = Exception
    
    # Mock tiktoken
    mock_tiktoken = MagicMock()
    mock_tiktoken.encoding_for_model = MagicMock(return_value=MagicMock())
    mock_tiktoken.get_encoding = MagicMock(return_value=MagicMock())
    
    # Mock langchain_anthropic
    mock_langchain_anthropic = MagicMock()
    mock_langchain_anthropic.ChatAnthropic = MagicMock
    
    # Mock langchain_openai
    mock_langchain_openai = MagicMock()
    mock_langchain_openai.ChatOpenAI = MagicMock
    mock_langchain_openai.OpenAI = MagicMock
    mock_langchain_openai.OpenAIEmbeddings = MagicMock
    
    # Mock langchain_community
    mock_langchain_community = MagicMock()
    mock_langchain_community.chat_models = MagicMock()
    mock_langchain_community.chat_models.ChatOllama = MagicMock
    mock_langchain_community.embeddings = MagicMock()
    mock_langchain_community.embeddings.OllamaEmbeddings = MagicMock
    
    # Register mocks
    sys.modules['langchain_core'] = mock_langchain_core
    sys.modules['langchain_core.messages'] = mock_langchain_core.messages
    sys.modules['langchain_core.runnables'] = mock_langchain_core.runnables
    sys.modules['langchain_core.callbacks'] = mock_langchain_core.callbacks
    sys.modules['langchain_core.callbacks.manager'] = mock_langchain_core.callbacks.manager
    sys.modules['langchain_core.outputs'] = mock_langchain_core.outputs
    sys.modules['langchain_core.language_models'] = mock_langchain_core.language_models
    sys.modules['langchain_core.tools'] = mock_langchain_core.tools
    sys.modules['langchain_core.tools.structured_tool'] = mock_langchain_core.tools.structured_tool
    sys.modules['langgraph'] = mock_langgraph
    sys.modules['langgraph.graph'] = mock_langgraph.graph
    sys.modules['langgraph.graph.message'] = mock_langchain_core.graph.message if hasattr(mock_langchain_core, 'graph') else mock_graph_message
    sys.modules['langchain_anthropic'] = mock_langchain_anthropic
    sys.modules['langchain_openai'] = mock_langchain_openai
    sys.modules['langchain_community'] = mock_langchain_community
    sys.modules['langchain_community.chat_models'] = mock_langchain_community.chat_models
    sys.modules['langchain_community.embeddings'] = mock_langchain_community.embeddings
    sys.modules['pgvector'] = mock_pgvector
    sys.modules['pgvector.sqlalchemy'] = mock_pgvector_sqlalchemy
    sys.modules['neo4j'] = mock_neo4j
    sys.modules['torch'] = mock_torch
    sys.modules['transformers'] = mock_transformers
    sys.modules['sentence_transformers'] = mock_sentence_transformers
    sys.modules['jwt'] = mock_jwt
    sys.modules['PyJWT'] = mock_jwt
    sys.modules['tiktoken'] = mock_tiktoken
    
    # Handle celery import - use our local implementation
    # Don't mock celery, let the real LocalCelery be used
    
    return {
        'langchain_core': mock_langchain_core,
        'langgraph': mock_langgraph,
        'pgvector': mock_pgvector,
        'neo4j': mock_neo4j,
    }


# Create mocks at module load time
_MOCKS = _create_mock_modules()


def pytest_configure(config):
    """Configure pytest before test collection."""
    # Ensure mocks are in place
    pass


def pytest_unconfigure(config):
    """Clean up after test collection."""
    pass
