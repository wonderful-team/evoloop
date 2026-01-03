from app.domain.codebase.indexing.base import BaseExtractor, Document, ExtractedEntity, ExtractedRelation, ExtractionResult
from app.domain.codebase.indexing.parsers import parser_registry
from app.domain.codebase.indexing.queries import TREE_SITTER_QUERIES
from app.logging import logger


class TreeSitterExtractor(BaseExtractor):
    def __init__(self):
        # Parsers logic moved to ParserRegistry
        pass  

    async def extract(self, file_path: str, content: str, module_path: str = None) -> ExtractionResult:
        """
        Extract code structure.
        
        Args:
            file_path: Absolute path (mostly for metadata).
            content: File content.
            module_path: Relative path or unique module identifier. Used for 'full_name' uniqueness.
                         If None, defaults to file_path (which might be absolute, less ideal).
        """
        extension = file_path.split(".")[-1]
        
        # Default module_path to file_name if not provided, or full path
        if not module_path:
            module_path = file_path

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
            return ExtractionResult(documents=documents, entities=[], relations=[])
        
        parser_info = parser_registry.get_parser(extension)
        if not parser_info:
            logger.debug(f"No parser for extension {extension}, skipping structured extraction.")
            return ExtractionResult(documents=[], entities=[], relations=[])

        parser, language = parser_info
        try:
            tree = parser.parse(bytes(content, "utf8"))
        except Exception as e:
            logger.warning(f"TreeSitter binary parse failed: {e}")
            return ExtractionResult(documents=[], entities=[], relations=[])

        lang_key = parser_registry.get_language_key(extension)

        query_data = TREE_SITTER_QUERIES.get(lang_key)
        if not query_data or "defs" not in query_data:
             logger.debug(f"No queries for language {lang_key}")
             return ExtractionResult(documents=[], entities=[], relations=[])
        
        query_str = query_data["defs"]
        try:
            query = language.query(query_str)
            import tree_sitter
            cursor = tree_sitter.QueryCursor(query)
            matches = list(cursor.matches(tree.root_node))
        except Exception as e:
            logger.warning(f"TreeSitter query failed: {e}")
            return ExtractionResult(documents=[], entities=[], relations=[])
        
        # logger.debug(f"TreeSitter matches: {len(matches)}")

        documents = []
        entities = []
        relations = []
        processed_ranges = set()

        for pattern_index, captured_nodes in matches:
            # captured_nodes is a dict: name -> list of nodes OR single node
            # We iterate over the dict to find our targets
            for capture_name, nodes in captured_nodes.items():
                # Create a list if it's a single node
                if not isinstance(nodes, list):
                    nodes = [nodes]

                for node in nodes:
                    # Capture Map for this specific node context
                    
                    # We iterate capture_name because we care about the main definition node (function/class)
                    # "function" or "class" is the main anchor.
                    if capture_name in ["function", "class"]:
                        # This node IS the definition node.
                        start_byte = node.start_byte
                        end_byte = node.end_byte

                        # Avoid duplicates if query captures both definition and name
                        if (start_byte, end_byte) in processed_ranges:
                            continue
                        processed_ranges.add((start_byte, end_byte))

                        chunk_content = content[node.start_point[0]:node.end_point[0] + 1]  # Approximate lines

                        # Extract name
                        name = "anonymous"
                        
                        name_nodes = captured_nodes.get("name", [])
                        if not isinstance(name_nodes, list): name_nodes = [name_nodes]

                        if name_nodes:
                            name = name_nodes[0].text.decode("utf8")

                        # Resolve Parent Context (Qualified Name)
                        fqn_parts = [name]
                        curr = node.parent
                        while curr:
                            # Heuristic: Check if parent is a Class Definition
                            
                            c_type = curr.type
                            # Generic cover for class types
                            if c_type in ["class_definition", "class_declaration", "class_specifier", "impl_item"]: 
                                # Find name of this class
                                class_name = None
                                for child in curr.children:
                                    if child.type == "identifier" or child.type == "type_identifier" or child.type == "name":
                                        class_name = child.text.decode("utf8")
                                        break
                                    
                                # Try specific field "name"
                                name_child = curr.child_by_field_name("name")
                                if name_child:
                                    class_name = name_child.text.decode("utf8")
                                
                                if class_name:
                                    fqn_parts.insert(0, class_name)
                                    # We assume one level of class nesting for now or keep going up
                            
                            curr = curr.parent
                        
                        local_identifier = ".".join(fqn_parts)
                        
                        # Fix Go Methods (Receiver)
                        if lang_key == "go" and capture_name == "function" and node.type == "method_declaration":
                             receiver_node = node.child_by_field_name("receiver")
                             if receiver_node:
                                 recv_text = receiver_node.text.decode("utf8")
                                 recv_type = recv_text.replace("(", "").replace(")", "").replace("*", "").split()[-1]
                                 local_identifier = f"{recv_type}.{name}"

                        # --- IDENTITY FIX: PREPEND MODULE/PATH ---
                        # full_identifier = "path/to/file.py::ClassName.Method"
                        full_identifier = f"{module_path}::{local_identifier}"


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
                        
                        # Add Entity
                        entities.append(ExtractedEntity(
                            name=name,
                            type=capture_name,
                            full_name=full_identifier, # <--- UNIQUE GLOBAL ID
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            content=chunk_content,
                            metadata={"lang": lang_key}
                        ))
                        
                        # --- RELATION EXTRACTION ---
                        # 1. Inheritance (Superclasses)
                        if capture_name == "class" and "superclasses" in captured_nodes:
                            supers = captured_nodes["superclasses"]
                            if not isinstance(supers, list): supers = [supers]
                            for s_node in supers:
                                s_text = s_node.text.decode("utf8")
                                clean_text = s_text.strip("()")
                                if clean_text:
                                    parts = [p.strip() for p in clean_text.split(",") if p.strip()]
                                    for parent_name in parts:
                                        relations.append(ExtractedRelation(
                                            source_full_name=full_identifier, # <--- Source is now Unique
                                            target_full_name=parent_name, # Target is still just a name (Resolve later)
                                            relation_type="inherits",
                                            start_line=node.start_point[0] + 1
                                        ))

                    # 2. Imports (Dependencies) - Still tricky, keeping basic logic placeholder
                    elif capture_name == "import":
                         pass 

        return ExtractionResult(documents=documents, entities=entities, relations=relations)
