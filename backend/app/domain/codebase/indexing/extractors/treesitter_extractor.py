from typing import List, Dict, Any, Optional
import tree_sitter_python
import tree_sitter_javascript
import tree_sitter_typescript 
import tree_sitter_go
import tree_sitter_java
import tree_sitter_cpp
import tree_sitter_rust
import tree_sitter_php
import tree_sitter_ruby

from tree_sitter import Language, Parser
from app.domain.codebase.indexing.base import BaseExtractor, Document
from app.logging import logger


from app.domain.codebase.indexing.parsers import parser_registry
from app.domain.codebase.indexing.queries import TREE_SITTER_QUERIES

class TreeSitterExtractor(BaseExtractor):
    def __init__(self):
        # Parsers logic moved to ParserRegistry
        pass  

    async def extract(self, file_path: str, content: str) -> List[Document]:
        extension = file_path.split(".")[-1]

        # Special handling for Markdown (Simple Header Splitter)
        if extension == "md":
            documents = []
            lines = content.splitlines()
            current_chunk = []
            current_header = "Intro"
            start_line = 1
            
            for i, line in enumerate(lines):
                if line.strip().startswith("#"):
                    # Save previous chunk
                    if current_chunk:
                        text = "\n".join(current_chunk)
                        doc = Document(
                            content=text,
                            metadata={
                                "file_path": file_path,
                                "type": "documentation",
                                "name": current_header,
                                "start_line": start_line,
                                "end_line": i
                            }
                        )
                        documents.append(doc)
                    
                    # Start new chunk
                    current_header = line.strip().lstrip("#").strip()
                    current_chunk = [line]
                    start_line = i + 1
                else:
                    current_chunk.append(line)
            
            # Last chunk
            if current_chunk:
                text = "\n".join(current_chunk)
                doc = Document(
                    content=text,
                    metadata={
                        "file_path": file_path,
                        "type": "documentation",
                        "name": current_header,
                        "start_line": start_line,
                        "end_line": len(lines)
                    }
                )
                documents.append(doc)
            return documents
        
        parser_info = parser_registry.get_parser(extension)
        if not parser_info:
            logger.debug(f"No parser for extension {extension}, skipping structured extraction.")
            return []

        parser, language = parser_info
        tree = parser.parse(bytes(content, "utf8"))

        lang_key = parser_registry.get_language_key(extension)

        query_data = TREE_SITTER_QUERIES.get(lang_key)
        if not query_data or "defs" not in query_data:
             logger.debug(f"No queries for language {lang_key}")
             return []
        
        query_str = query_data["defs"]
        query = language.query(query_str)
        # Python tree-sitter bindings > 0.22 use QueryCursor for execution
        import tree_sitter
        cursor = tree_sitter.QueryCursor(query)
        matches = cursor.matches(tree.root_node)

        documents = []
        processed_ranges = set()

        for pattern_index, captured_nodes in matches:
            # captured_nodes is a dict: name -> list of nodes OR single node
            # We iterate over the dict to find our targets
            for capture_name, nodes in captured_nodes.items():
                # Create a list if it's a single node
                if not isinstance(nodes, list):
                    nodes = [nodes]

                for node in nodes:
                    if capture_name in ["function", "class"]:
                        start_byte = node.start_byte
                        end_byte = node.end_byte

                        # Avoid duplicates if query captures both definition and name
                        if (start_byte, end_byte) in processed_ranges:
                            continue
                        processed_ranges.add((start_byte, end_byte))

                        chunk_content = content[node.start_point[0]:node.end_point[0] + 1]  # Approximate lines

                        # Extract name
                        name = "anonymous"
                        # Finding name is tricky in `matches` API because "name" capture is separate from "function" capture usually?
                        # In my queries: `(function ... @function)` and `(identifier) @name`.
                        # They are in the SAME match pattern.
                        # So `captured_nodes` will contain BOTH "function": [node] and "name": [node].
                        # We are currently iterating "function" nodes.
                        # We need to find the "name" node associated with THIS match.

                        # The `captured_nodes` dict contains all captures for this SINGLE MATCH.
                        # So if I have @function and @name in the same pattern, they are in the same dict.

                        name_nodes = captured_nodes.get("name", [])
                        if not isinstance(name_nodes, list): name_nodes = [name_nodes]

                        if name_nodes:
                            name = name_nodes[0].text.decode("utf8")

                        # Resolve Parent Context (Qualified Name)
                        # We walk up the tree to find if we are inside a Class
                        fqn_parts = [name]
                        curr = node.parent
                        while curr:
                            # Heuristic: Check if parent is a Class Definition
                            # The node content might not give us the type string easily if we don't have the mapping handy.
                            # But we can check generic node types.
                            # Python: class_definition
                            # Java: class_declaration
                            # Go: (Methods are top level with receiver, tricky. Tree-sitter struct is different)
                            # Let's handle Python/Java/Standard OOP style for now.
                            
                            c_type = curr.type
                            if c_type in ["class_definition", "class_declaration", "class_specifier", "impl_item"]: # generic cover
                                # Find name of this class
                                # We need to run a mini-query or manually Scan children for identifier
                                # Scanning children is safer/faster than re-querying
                                class_name = None
                                for child in curr.children:
                                    if child.type == "identifier" or child.type == "type_identifier" or child.type == "name":
                                        class_name = child.text.decode("utf8")
                                        break
                                    # Python: name field is child_by_field_name "name" -> identifier
                                    # Tree sitter API allows child_by_field_name
                                    
                                # Try specific field "name"
                                name_child = curr.child_by_field_name("name")
                                if name_child:
                                    class_name = name_child.text.decode("utf8")
                                
                                if class_name:
                                    fqn_parts.insert(0, class_name)
                                    # We assume one level of class nesting for now or keep going up
                            
                            curr = curr.parent
                        
                        full_identifier = ".".join(fqn_parts)

                        doc = Document(
                            content=node.text.decode("utf8"),
                            metadata={
                                "file_path": file_path,
                                "type": capture_name,
                                "name": full_identifier, # Use FQN here
                                "short_name": name,
                                "start_line": node.start_point[0] + 1,
                                "end_line": node.end_point[0] + 1
                            }
                        )
                        documents.append(doc)
                        
                        # Fix Go Methods (Receiver)
                        # Go methods are top-level `(method_declaration receiver: (parameter_list ... ) ... )`
                        # The receiver determines the "Class".
                        if lang_key == "go" and capture_name == "function" and node.type == "method_declaration":
                             # Extract receiver type
                             receiver_node = node.child_by_field_name("receiver")
                             if receiver_node:
                                 # Usually (parameter_list (parameter_declaration type: ...))
                                 # This is complex to parse manually without query, but let's try a simple text extraction
                                 recv_text = receiver_node.text.decode("utf8")
                                 # recv_text is like "(s *Service)" or "(Service)"
                                 # Naive cleanup
                                 recv_type = recv_text.replace("(", "").replace(")", "").replace("*", "").split()[-1]
                                 
                                 # Check if we already have it in FQN (unlikely with parent walk for Go)
                                 # Update FQN
                                 full_identifier = f"{recv_type}.{name}"
                                 doc.metadata["name"] = full_identifier

        return documents
