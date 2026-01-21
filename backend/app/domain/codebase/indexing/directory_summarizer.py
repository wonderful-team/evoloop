import logging

from app.infrastructure.database.graph.driver import get_graph_db

logger = logging.getLogger(__name__)


class DirectorySummarizer:
    """
    Implements Recursive Summarization for Directories.
    Creates `Directory` nodes in Neo4j that aggregate `File` and child `Directory` summaries.
    """

    async def summarize_directory(self, project_id: int, dir_path: str, recursive: bool = True):
        """
        Summarize a directory.
        1. Find all Files in this directory (direct children).
        2. Find all Sub-directories (direct children).
        3. If recursive, summarize sub-directories first (Bottom-up).
        4. Aggregate summaries and generate own summary.
        5. Store in Neo4j.
        """
        driver = await get_graph_db()

        # 1. Identify Children (Files and Subdirs)
        # We need to rely on the graph structure.
        # Assuming we have (File {path: ...}) nodes.
        # We need to find immediate children.
        # Since we don't maintain a perfect directory tree in Graph yet, we infer from File paths.
        # However, verifying immediate children from paths like 'a/b/c.py' vs 'a/b/d/e.py' via Cypher regex is possible but tricky.
        # Better approach: The `IndexingService` creates `(Directory)-[:CONTAINS]->(File)` links?
        # We don't have that yet.
        # STRATEGY: We will do a "Virtual" traversal using Python and known file paths if Graph is incomplete,
        # OR we rely on a helper to query ALL files starting with dir_path and build tree in memory.

        # Let's use the In-Memory Tree approach for robustness in V1.
        all_files_query = """
        MATCH (f:File {project_id: $pid})
        WHERE f.path STARTS WITH $path
        RETURN f.path as path, f.summary as summary
        """
        # Note: f.summary doesn't exist yet on File nodes (we have ::whole_file chunks).
        # We should use the Embedding or fetch the Chunk content?
        # Ideally, File node has a 'description' or we use the linked 'whole_file' chunk.

        async with driver.session() as session:
            result = await session.run(
                all_files_query,
                pid=project_id,
                path=dir_path if dir_path.endswith("/") else dir_path + "/",
            )
            records = await result.data()

        # Build Local Tree
        # We only care about DIRECT children for this summary.
        # Direct Files: path == dir_path +filename
        # Direct Subdirs: path == dir_path + subdir_name + ...

        direct_files = []
        direct_subdirs = set()

        base_len = len(dir_path) + (1 if not dir_path.endswith("/") else 0)

        for r in records:
            rel_path = r["path"][base_len:]  # strip prefix
            parts = rel_path.split("/")

            if len(parts) == 1:
                # Is a file
                # Fetch summary/content for this file
                # We use the whole file content proxy logic below (Step 3).
                direct_files.append(r["path"])
            else:
                # Is in a subdir
                subdir_name = parts[0]
                direct_subdirs.add(
                    dir_path + ("/" if not dir_path.endswith("/") else "") + subdir_name
                )

        # 2. Recursive Step (Bottom-Up)
        child_summaries = []

        if recursive:
            for subdir in direct_subdirs:
                # Recurse
                sub_summary = await self.summarize_directory(project_id, subdir, recursive=True)
                child_summaries.append(f"Directory {subdir}: {sub_summary}")

        # 3. Process Files
        # We need their summaries.
        # Querying DB for 'whole_file' chunks for these files.
        if direct_files:
            file_summaries_query = """
            MATCH (f:File {project_id: $pid})
            WHERE f.path IN $paths
            OPTIONAL MATCH (f)-[:CONTAINS]->(c:CodeChunk {chunk_type: 'file'})
            RETURN f.path as path, c.content as content
            """
            async with driver.session() as session:
                result = await session.run(file_summaries_query, pid=project_id, paths=direct_files)
                f_records = await result.data()

            for fr in f_records:
                # Use the 'whole_file' chunk content as a proxy for summary.
                # In the future (Phase 2), we should store a generated summary on the File node itself.
                # For now, we take the first 1000 characters to give the context window enough signal.
                content_preview = (fr["content"] or "")[:1000].replace("\n", " ")
                if len(fr["content"] or "") > 1000:
                    content_preview += "..."
                child_summaries.append(f"File {fr['path']}: {content_preview}")

        if not child_summaries:
            return "Empty Directory"

        # 4. Generate Summary
        summary_text = await self.generate_summary(dir_path, child_summaries)

        # 5. Store in Neo4j
        async with driver.session() as session:
            await session.run(
                """
                MERGE (d:Directory {path: $path, project_id: $pid})
                SET d.description = $summary, d.updated_at = timestamp()
            """,
                path=dir_path,
                pid=project_id,
                summary=summary_text,
            )

            # Also Link to Parent?
            # Implied by path structure, but explicit link is better for graph traversal.
            # (Parent)-[:CONTAINS]->(ChildDir)
            # We can infer parent path string.
            if "/" in dir_path.strip("/"):
                parent_path = dir_path.rstrip("/").rsplit("/", 1)[0]
                await session.run(
                    """
                    MATCH (p:Directory {path: $ppath, project_id: $pid})
                    MATCH (c:Directory {path: $cpath, project_id: $pid})
                    MERGE (p)-[:CONTAINS]->(c)
                """,
                    ppath=parent_path,
                    cpath=dir_path,
                    pid=project_id,
                )

        logger.info(f"Summarized Directory: {dir_path}")
        return summary_text

    async def generate_summary(self, dir_path: str, child_summaries: list[str]) -> str:
        from langchain_core.messages import HumanMessage, SystemMessage

        from app.core.llm.factory import LLMFactory

        llm = LLMFactory.create_llm()

        # Context Management: If too many children, sample or hierarchically summarize?
        # V1: Just join.
        context = "\n".join(child_summaries)

        system_prompt = "You are a System Architect. Summarize the role and architectural responsibility of this directory based on its contents."
        user_prompt = f"Directory: {dir_path}\n\nContents:\n{context}\n\nProvide a concise, high-level summary (1-2 sentences) of what this module does."

        try:
            response = await llm.invoked([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ])
            return response.content
        except Exception:
            # Fallback for LLM failure or invocation error (invoked vs invoke)
            # invoke is standard
            try:
                response = await llm.ainvoke([
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt),
                ])
                return response.content
            except Exception as e:
                logger.error(f"LLM Summary Failed: {e}")
                return "Summary generation failed."


# Global Instance
directory_summarizer = DirectorySummarizer()
