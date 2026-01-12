
import logging
from dataclasses import dataclass

import tree_sitter

from app.domain.codebase.indexing.parsers import parser_registry
from app.utils.file import read_file_content

logger = logging.getLogger(__name__)

@dataclass
class APIEndpoint:
    method: str
    path: str
    handler_name: str
    file_path: str
    line_number: int

class APIExtractor:
    """
    Extracts API Definitions from code files using TreeSitter.
    Supports:
    - Python (FastAPI/Flask)
    - TypeScript/JS (Express/Node)
    - Java (Spring Boot)
    - Go (Gin/Echo)
    - C# (ASP.NET Core)
    """

    PYTHON_API_QUERY = """
    (decorated_definition
      (decorator
        (call
          (attribute
            object: (_) @obj
            attribute: (identifier) @method)
          arguments: (argument_list (_) @path)
        )
      )
      definition: (function_definition name: (identifier) @handler)
    )
    """

    TYPESCRIPT_API_QUERY = """
    (call_expression
      function: (member_expression
        object: (identifier) @obj
        property: (property_identifier) @method)
      arguments: (arguments
        [(string) (template_string)] @path
        [(arrow_function) (function_expression) (identifier)] @handler
      )
    )
    """

    # Spring Boot: @GetMapping("/users"), @RequestMapping(value = "/users", method = RequestMethod.GET)
    # Simplifying to standard short annotations for now
    JAVA_API_QUERY = """
    (method_declaration
      (modifiers
        (marker_annotation
          name: (identifier) @annotation
        ) @modifier
      )
      name: (identifier) @handler
    )
    (method_declaration
      (modifiers
        (annotation
          name: (identifier) @annotation
          arguments: (annotation_argument_list (string_literal) @path)
        ) @modifier
      )
      name: (identifier) @handler
    )
    """

    # Go (Gin): router.GET("/path", handler) or router.GET("/path", func(...) {})
    GO_API_QUERY = """
    (call_expression
      function: (selector_expression
        operand: (identifier) @obj
        field: (field_identifier) @method)
      arguments: (argument_list
        (interpreted_string_literal) @path
        [(identifier) (func_literal)] @handler
      )
    )
    """

    # C# (.NET): [HttpGet("path")] public IActionResult Get()
    CSHARP_API_QUERY = """
    (method_declaration
      (attribute_list
        (attribute
          name: (identifier) @method_attr
          (attribute_argument_list 
            (attribute_argument) @path_arg
          )?
        )
      )
      name: (identifier) @handler
    )
    """

    HTTP_METHODS = {"get", "post", "put", "delete", "patch", "options", "head"}

    # Map Annotation to Method for Java/C#
    ANNOTATION_TO_METHOD = {
        "GetMapping": "GET",
        "PostMapping": "POST",
        "PutMapping": "PUT",
        "DeleteMapping": "DELETE",
        "PatchMapping": "PATCH",
        "HttpGet": "GET",
        "HttpPost": "POST",
        "HttpPut": "PUT",
        "HttpDelete": "DELETE",
        "HttpPatch": "PATCH"
    }

    async def extract(self, file_path: str) -> list[APIEndpoint]:
        extension = file_path.split(".")[-1].lower()
        supported_exts = ["py", "ts", "js", "tsx", "java", "go", "cs", "csharp"]

        if extension not in supported_exts:
            return []

        parser_info = parser_registry.get_parser(extension)
        if not parser_info:
            return []

        parser, language = parser_info

        try:
            content, _ = read_file_content(file_path)
            if not content: return []

            tree = parser.parse(bytes(content, "utf8"))

            if extension == "py":
                return self._extract_python(tree, language, file_path)
            elif extension in ["ts", "js", "tsx"]:
                return self._extract_typescript(tree, language, file_path)
            elif extension == "java":
                return self._extract_java(tree, language, file_path)
            elif extension == "go":
                return self._extract_go(tree, language, file_path)
            elif extension in ["cs", "csharp"]:
                return self._extract_csharp(tree, language, file_path)

            return []

        except Exception as e:
            logger.error(f"API Extraction failed for {file_path}: {e}")
            return []

    def _extract_python(self, tree, language, file_path) -> list[APIEndpoint]:
        endpoints = []
        try:
            query = tree_sitter.Query(language, self.PYTHON_API_QUERY)
            cursor = tree_sitter.QueryCursor(query)
            matches = cursor.matches(tree.root_node)

            for _, captured_nodes in matches:
                obj_node = self._get_node(captured_nodes, "obj")
                method_node = self._get_node(captured_nodes, "method")
                path_node = self._get_node(captured_nodes, "path")
                handler_node = self._get_node(captured_nodes, "handler")

                if not (obj_node and method_node and path_node and handler_node): continue

                method = method_node.text.decode("utf8").lower()

                if method not in self.HTTP_METHODS: continue

                path = path_node.text.decode("utf8").strip("'\"")
                handler = handler_node.text.decode("utf8")

                endpoints.append(APIEndpoint(
                    method=method.upper(),
                    path=path,
                    handler_name=handler,
                    file_path=file_path,
                    line_number=method_node.start_point[0] + 1
                ))

        except Exception as e:
            logger.warning(f"Python API Query Error: {e}")
        return endpoints

    def _extract_typescript(self, tree, language, file_path) -> list[APIEndpoint]:
        endpoints = []
        try:
            query = tree_sitter.Query(language, self.TYPESCRIPT_API_QUERY)
            cursor = tree_sitter.QueryCursor(query)
            matches = cursor.matches(tree.root_node)

            for _, captured_nodes in matches:
                obj_node = self._get_node(captured_nodes, "obj")
                method_node = self._get_node(captured_nodes, "method")
                path_node = self._get_node(captured_nodes, "path")
                handler_node = self._get_node(captured_nodes, "handler")

                if not (obj_node and method_node and path_node and handler_node): continue

                method = method_node.text.decode("utf8").lower()
                if method not in self.HTTP_METHODS: continue

                path_text = path_node.text.decode("utf8")
                # Remove quotes or backticks
                if path_text.startswith(("'", '"', "`")):
                    path = path_text[1:-1]
                else:
                    path = path_text

                handler = "anonymous"
                if handler_node.type == "identifier":
                     handler = handler_node.text.decode("utf8")

                endpoints.append(APIEndpoint(
                    method=method.upper(),
                    path=path,
                    handler_name=handler,
                    file_path=file_path,
                    line_number=method_node.start_point[0] + 1
                ))

        except Exception as e:
            logger.warning(f"TypeScript API Query Error: {e}")
        return endpoints

    def _extract_java(self, tree, language, file_path) -> list[APIEndpoint]:
        endpoints = []
        try:
            query = tree_sitter.Query(language, self.JAVA_API_QUERY)
            cursor = tree_sitter.QueryCursor(query)
            matches = cursor.matches(tree.root_node)

            for _, captured_nodes in matches:
                annotation_node = self._get_node(captured_nodes, "annotation")
                path_node = self._get_node(captured_nodes, "path")
                handler_node = self._get_node(captured_nodes, "handler")

                if not (annotation_node and handler_node): continue

                annotation = annotation_node.text.decode("utf8")
                method = self.ANNOTATION_TO_METHOD.get(annotation)
                if not method: continue

                path = "/"
                if path_node:
                    path = path_node.text.decode("utf8").strip('"')

                endpoints.append(APIEndpoint(
                    method=method,
                    path=path,
                    handler_name=handler_node.text.decode("utf8"),
                    file_path=file_path,
                    line_number=annotation_node.start_point[0] + 1
                ))
        except Exception as e:
            logger.warning(f"Java API Query Error: {e}")
        return endpoints

    def _extract_go(self, tree, language, file_path) -> list[APIEndpoint]:
        endpoints = []
        try:
            query = tree_sitter.Query(language, self.GO_API_QUERY)
            cursor = tree_sitter.QueryCursor(query)
            matches = cursor.matches(tree.root_node)

            for _, captured_nodes in matches:
                method_node = self._get_node(captured_nodes, "method")
                path_node = self._get_node(captured_nodes, "path")
                handler_node = self._get_node(captured_nodes, "handler")

                if not (method_node and path_node and handler_node): continue

                method = method_node.text.decode("utf8").upper()
                if method not in map(str.upper, self.HTTP_METHODS): continue

                path = path_node.text.decode("utf8").strip('"')

                handler_name = "anonymous"
                if handler_node.type == "identifier":
                    handler_name = handler_node.text.decode("utf8")

                endpoints.append(APIEndpoint(
                    method=method,
                    path=path,
                    handler_name=handler_name,
                    file_path=file_path,
                    line_number=method_node.start_point[0] + 1
                ))
        except Exception as e:
            logger.warning(f"Go API Query Error: {e}")
        return endpoints

    def _extract_csharp(self, tree, language, file_path) -> list[APIEndpoint]:
        endpoints = []
        try:
            query = tree_sitter.Query(language, self.CSHARP_API_QUERY)
            cursor = tree_sitter.QueryCursor(query)
            matches = cursor.matches(tree.root_node)

            for _, captured_nodes in matches:
                attr_node = self._get_node(captured_nodes, "method_attr")
                path_arg_node = self._get_node(captured_nodes, "path_arg")
                handler_node = self._get_node(captured_nodes, "handler")

                if not (attr_node and handler_node): continue

                attr_name = attr_node.text.decode("utf8")
                method = self.ANNOTATION_TO_METHOD.get(attr_name)
                if not method: continue

                path = "/"
                if path_arg_node:
                    # text is usually '"path"', so strip quotes
                    path_text = path_arg_node.text.decode("utf8").strip()
                    if path_text.startswith('"') and path_text.endswith('"'):
                        path = path_text.strip('"')
                    elif path_text.startswith('nameof('):
                        # skip complex args for now
                        continue

                endpoints.append(APIEndpoint(
                    method=method,
                    path=path,
                    handler_name=handler_node.text.decode("utf8"),
                    file_path=file_path,
                    line_number=attr_node.start_point[0] + 1
                ))

        except Exception as e:
            logger.warning(f"C# API Query Error: {e}")
        return endpoints

    def _get_node(self, captured: dict, name: str):
        nodes = captured.get(name)
        if not nodes: return None
        if isinstance(nodes, list): return nodes[0]
        return nodes

    async def sync_to_graph(self, project_id: int, endpoints: list[APIEndpoint]):
        if not endpoints: return

        try:
            from app.infrastructure.database.graph.driver import get_graph_db
            driver = await get_graph_db()
            async with driver.session() as session:
                for ep in endpoints:
                    full_name = f"{ep.method} {ep.path}"
                    await session.run("""
                        MERGE (e:APIEndpoint {full_name: $id, project_id: $pid})
                        SET e.method = $method, e.path = $path, e.handler = $handler, e.file = $file
                        WITH e
                        MATCH (fn:CodeEntity {name: $handler, project_id: $pid}) 
                        MERGE (e)-[:HANDLED_BY]->(fn)
                    """, id=full_name, pid=project_id, method=ep.method, path=ep.path,
                         handler=ep.handler_name, file=ep.file_path)

        except Exception as e:
            logger.error(f"Graph Sync for API failed: {e}")

api_extractor = APIExtractor()
