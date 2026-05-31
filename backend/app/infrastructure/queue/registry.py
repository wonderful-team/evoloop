"""
Task Registry for EvoLoop Task Queue.

Contains common task mappings and registration logic shared between 
different scheduler implementations (Celery, Huey, LocalCelery).
"""

# Task name to module mapping for dynamic loading
TASK_MODULE_MAP = {
    # Engine tasks
    "engine_persist_file_operation": "app.core.engine.tasks",
    "engine_harvest_concepts": "app.core.engine.tasks",
    "engine_record_episode": "app.core.engine.tasks",
    "engine_prune_checkpoints": "app.core.engine.tasks",
    "engine_cleanup_artifacts": "app.core.engine.tasks",
    "engine_git_harvest": "app.core.engine.tasks",
    "engine_reconcile_skill_macro": "app.core.engine.tasks",
    "engine_scheduler_tick": "app.core.engine.tasks",
    "run_autonomous_task_execution": "app.core.engine.tasks",
    "engine_run_agent_background": "app.core.engine.tasks",
    "engine_resume_graph_background": "app.core.engine.tasks",
    # Atlas tasks
    "atlas_explore_app": "app.core.atlas.tasks",
    "atlas_execute_exploration": "app.core.atlas.tasks",
    # Vision tasks
    "cleanup_screenshots": "app.core.vision.cleanup",
    "cleanup_screen_recordings": "app.core.vision.cleanup",
    # Indexing tasks
    "index_repository": "app.domain.codebase.indexing.tasks",
    "incremental_index": "app.domain.codebase.indexing.tasks",
    "codebase_index_file": "app.domain.codebase.indexing.tasks",
    "codebase_remove_file": "app.domain.codebase.indexing.tasks",
    "codebase_move_file": "app.domain.codebase.indexing.tasks",
    # Project tasks
    "summarize_project": "app.domain.project.summarizer",
    "sync_project": "app.domain.project.sync_tasks",
    # Wiki tasks
    "sync_wiki_page": "app.domain.wiki.tasks",
    "wiki_generate": "app.domain.wiki.tasks",
    # EvoCloud sync tasks
    "evocloud.sync_conversation": "app.core.evocloud.bridge.sync_tasks",
    "evocloud.sync_messages": "app.core.evocloud.bridge.sync_tasks",
    "evocloud.sync_full": "app.core.evocloud.bridge.sync_tasks",
    "evocloud.sync_incremental": "app.core.evocloud.bridge.sync_tasks",
}
