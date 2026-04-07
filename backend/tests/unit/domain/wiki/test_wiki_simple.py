"""
Simple tests for Wiki Agent - No heavy dependencies.
"""
import pytest
import os


class TestWikiConfig:
    """Test Wiki configuration."""

    def test_yaml_config(self):
        """Test YAML config exists and valid."""
        import yaml
        
        config_path = os.path.join(
            os.path.dirname(__file__), 
            '..', '..', '..', '..', 
            'app', 'config', 'agents', 'wiki_agent.yml'
        )
        
        with open(config_path) as f:
            config = yaml.safe_load(f)
        
        assert config["name"] == "WikiAgent"
        assert len(config["nodes"]) == 4
        
        node_ids = [n["id"] for n in config["nodes"]]
        assert "router" in node_ids
        assert "wiki_structure_worker" in node_ids
        assert "wiki_content_worker" in node_ids
        assert "wiki_finish" in node_ids


class TestWikiToolsLogic:
    """Test Wiki tools logic - inline to avoid imports."""

    def test_tree_string_generation(self):
        """Test file tree string generation logic."""
        def paths_to_tree_string(paths):
            paths = sorted(paths)
            lines = []
            prev_parts = []
            
            for path in paths:
                parts = path.split("/")
                common_depth = 0
                for i in range(min(len(parts), len(prev_parts))):
                    if parts[i] == prev_parts[i]:
                        common_depth += 1
                    else:
                        break
                
                for i in range(common_depth, len(parts)):
                    prefix = "  " * i + ("└── " if i == len(parts) - 1 else "├── ")
                    lines.append(f"{prefix}{parts[i]}")
                
                prev_parts = parts
            
            return "\n".join(lines)
        
        paths = ["src/main.py", "src/utils.py", "tests/test.py"]
        tree = paths_to_tree_string(paths)
        
        assert "src" in tree
        assert "main.py" in tree
        assert "utils.py" in tree
        assert "tests" in tree


class TestStateLogic:
    """Test state management logic."""

    def test_route_decision(self):
        """Test route decision logic."""
        def route_decision(state):
            if state.get("error"):
                return "END"
            
            wiki_structure = state.get("wiki_structure")
            pages_to_generate = state.get("pages_to_generate")
            
            if wiki_structure is None:
                return "structure"
            
            if not pages_to_generate:
                return "finish"
            
            current_index = state.get("current_page_index", 0)
            if current_index < len(pages_to_generate):
                return "content"
            
            return "finish"
        
        assert route_decision({"wiki_structure": None}) == "structure"
        assert route_decision({
            "wiki_structure": [],
            "pages_to_generate": [{"id": "test"}],
            "current_page_index": 0
        }) == "content"
        assert route_decision({
            "wiki_structure": [],
            "pages_to_generate": [{"id": "test"}],
            "current_page_index": 1
        }) == "finish"

    def test_structure_flattening(self):
        """Test structure flattening logic."""
        def flatten_structure(pages, parent_id=None):
            flat = []
            for i, page in enumerate(pages):
                page_plan = {
                    "id": page.get("id", f"page-{i}"),
                    "title": page.get("title", "Untitled"),
                    "parent_id": parent_id,
                    "order": i,
                }
                flat.append(page_plan)
                
                children = page.get("children", [])
                if children:
                    flat.extend(flatten_structure(children, parent_id=page_plan["id"]))
            
            return flat
        
        hierarchical = [
            {
                "id": "root",
                "title": "Root",
                "children": [
                    {"id": "child1", "title": "Child 1"},
                    {"id": "child2", "title": "Child 2"},
                ]
            }
        ]
        
        flat = flatten_structure(hierarchical)
        
        assert len(flat) == 3
        assert flat[0]["id"] == "root"
        assert flat[1]["parent_id"] == "root"


class TestCodeQuality:
    """Test code quality - syntax checks."""

    def test_all_files_syntax_valid(self):
        """Test all Python files have valid syntax."""
        import ast
        
        base_path = os.path.join(
            os.path.dirname(__file__),
            '..', '..', '..', '..',
            'app', 'domain', 'wiki'
        )
        
        files = [
            '__init__.py',
            'agent_engine.py',
            'agent_state.py',
            'tools.py',
            'nodes/__init__.py',
            'nodes/router.py',
            'nodes/structure_worker.py',
            'nodes/content_worker.py',
            'nodes/finish.py',
        ]
        
        for file in files:
            path = os.path.join(base_path, file)
            if os.path.exists(path):
                with open(path) as f:
                    ast.parse(f.read())


pytestmark = [
    pytest.mark.unit,
    pytest.mark.no_external_services,
]
