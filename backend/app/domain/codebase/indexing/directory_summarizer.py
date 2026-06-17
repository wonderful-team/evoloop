import logging

from app.infrastructure.database.graph.driver import get_graph_db

logger = logging.getLogger(__name__)


class DirectorySummarizer:
    """
    Implements Recursive Summarization for Directories.
    Creates `Directory` nodes in Neo4j that aggregate `File` and child `Directory` summaries.
    """

    async def summarize_directory(self, project_path: str, project_id: int, dir_path: str, recursive: bool = True, model: str | None = None):
        """
        Summarize a directory.
        1. Find all Files in this directory (direct children).
        2. Find all Sub-directories (direct children).
        3. If recursive, summarize sub-directories first (Bottom-up).
        4. Aggregate summaries and generate own summary.
        5. Store in Neo4j.
        
        Args:
            project_path: 项目本地路径（用于获取项目级 graph driver）
            project_id: 项目 ID（用于图数据查询）
            dir_path: 目录相对路径
            recursive: 是否递归处理子目录
            model: 使用的 LLM 模型
        """
        from app.infrastructure.database.graph.driver import GraphManager
        driver = GraphManager.get_driver(project_path=project_path)

        try:
            # 1. Identify Children (Files and Subdirs)
            all_files_query = """
            MATCH (f:File {project_id: $pid})
            WHERE f.path STARTS WITH $path
            RETURN f.path as path, f.summary as summary
            """
            records = await driver.execute_query(
                all_files_query,
                pid=project_id,
                path=dir_path if dir_path.endswith("/") else dir_path + "/",
            )

            # Build Local Tree
            direct_files = []
            direct_subdirs = set()
            base_len = len(dir_path) + (1 if not dir_path.endswith("/") else 0)

            for r in records:
                rel_path = r["path"][base_len:]
                parts = rel_path.split("/")

                if len(parts) == 1:
                    direct_files.append(r["path"])
                else:
                    subdir_name = parts[0]
                    direct_subdirs.add(
                        dir_path + ("/" if not dir_path.endswith("/") else "") + subdir_name
                    )

            # 2. Recursive Step (Bottom-Up)
            child_summaries = []
            if recursive:
                for subdir in direct_subdirs:
                    sub_summary = await self.summarize_directory(project_path, project_id, subdir, recursive=True, model=model)
                    child_summaries.append({"type": "directory", "name": subdir, "summary": sub_summary})

            # 3. Process Files
            if direct_files:
                file_summaries_query = """
                MATCH (f:File {project_id: $pid})
                WHERE f.path IN $paths
                OPTIONAL MATCH (f)-[:CONTAINS]->(c:CodeChunk {chunk_type: 'file'})
                RETURN f.path as path, c.content as content
                """
                f_records = await driver.execute_query(file_summaries_query, pid=project_id, paths=direct_files)

                for fr in f_records:
                    content_preview = (fr["content"] or "")[:1000]
                    if len(fr["content"] or "") > 1000:
                        content_preview += "..."
                    child_summaries.append({"type": "file", "name": fr["path"], "content": content_preview})

            if not child_summaries:
                return "Empty Directory"

            # 4. Generate Summary
            summary_text = await self.generate_summary(dir_path, child_summaries, model=model)

            # 5. Store in Graph
            await driver.upsert_node("Directory", "path", {
                "path": dir_path,
                "project_id": project_id,
                "description": summary_text
            })

            # Also Link to Parent?
            if "/" in dir_path.strip("/"):
                parent_path = dir_path.rstrip("/").rsplit("/", 1)[0]
                await driver.link_nodes(
                    "Directory", {"path": parent_path, "project_id": project_id},
                    "Directory", {"path": dir_path, "project_id": project_id},
                    "CONTAINS"
                )

            logger.info(f"Summarized Directory: {dir_path}")
            return summary_text
        except NotImplementedError:
            logger.debug("Directory summarization requires graph features (disabled in embedded mode).")
            return "Graph-based summarization not available in embedded mode."

    async def generate_summary(self, dir_path: str, child_summaries: list[dict], model: str | None = None) -> str:
        from app.utils import render_template
        
        prompt_text = render_template(
            "domain/codebase/directory_summary.prompt.j2",
            directory_path=dir_path,
            child_summaries=child_summaries
        )

        from app.core.llm import InternalLLMService
        from app.infrastructure.config.service import SystemConfigService
        model_name = SystemConfigService.get_value("LLM_MODEL")
        response = await InternalLLMService.invoke(
            messages=[{"role": "user", "content": prompt_text}],
            purpose="skill_synthesis",
            model_name=model or model_name,
        )
        return response.content


# Global Instance
directory_summarizer = DirectorySummarizer()
