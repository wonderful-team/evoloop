
import asyncio
import logging
import os
from threading import RLock
from typing import Dict, Any

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from app.infrastructure.external.imagicbox import imagicbox_client
from app.domain.project.service import project_context_manager
from app.domain.codebase.indexing.service import IndexingService

logger = logging.getLogger(__name__)

# --- Global Observer Manager ---

class GlobalObserverManager:
    """
    Singleton to manage a single Watchdog Observer instance for the entire application.
    This prevents resource exhaustion and conflict issues on macOS (FSEvents).
    """
    _instance = None
    _lock = RLock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(GlobalObserverManager, cls).__new__(cls)
                cls._instance._init()
            return cls._instance

    def _init(self):
        self._observer = Observer()
        self._watches: Dict[str, Any] = {} # Map path -> Watch Object
        self._started = False

    def start_observer(self):
        with self._lock:
            if not self._started:
                try:
                    self._observer.start()
                    self._started = True
                    logger.info("Global Watchdog Observer started.")
                except Exception as e:
                    logger.error(f"Failed to start Global Observer: {e}")

    def stop_observer(self):
        with self._lock:
            if self._started:
                self._observer.stop()
                self._observer.join()
                self._started = False
                logger.info("Global Watchdog Observer stopped.")

    def schedule(self, event_handler, path: str, recursive: bool = True):
        # Normalize path
        path = os.path.abspath(path)
        
        with self._lock:
            if not self._started:
                self.start_observer()
                
            # Check if this precise path is already watched
            # Note: Watchdog allows multiple handlers on the same path, but we might want to avoid duplicates if intended.
            # However, the user error "already scheduled" usually means Exact Same Watch (same handler instance or internal eq).
            # For simplicity, we just try to schedule and catch the error, or check our map.
            
            # If we already track this path, we might need to unschedule first if we want to replace,
            # or just add another handler (if watchdog supports it).
            # But the error "already scheduled" suggests strictness.
            
            try:
                # Schedule via watchdog
                watch = self._observer.schedule(event_handler, path, recursive=recursive)
                self._watches[path] = watch
                logger.debug(f"Scheduled watch on: {path}")
            except RuntimeError as re:
                if "already scheduled" in str(re):
                    logger.warning(f"Watch already scheduled for {path}. Skipping/Ignoring.")
                else:
                    raise re
            except Exception as e:
                logger.error(f"Failed to schedule watch for {path}: {e}")

    def unschedule(self, path: str):
        path = os.path.abspath(path)
        with self._lock:
            if path in self._watches:
                watch = self._watches[path]
                try:
                    self._observer.unschedule(watch)
                    del self._watches[path]
                    logger.debug(f"Unscheduled watch on: {path}")
                except Exception as e:
                    logger.error(f"Error unscheduling watch for {path}: {e}")

# Global instance
observer_manager = GlobalObserverManager()


# --- Reuse Handlers ---

class IndexingEventHandler(FileSystemEventHandler):
    def __init__(self, service: IndexingService, repo_id: int, loop: asyncio.AbstractEventLoop):
        self.service = service
        self.repo_id = repo_id
        self.loop = loop

    def on_modified(self, event):
        if event.is_directory: return
        self._process(event.src_path)

    def on_created(self, event):
        if event.is_directory: return
        self._process(event.src_path)

    def on_deleted(self, event):
        if event.is_directory: return
        self._process_delete(event.src_path)

    def on_moved(self, event):
        if event.is_directory: return
        self._process_move(event.src_path, event.dest_path)

    def _is_valid_code_file(self, path: str) -> bool:
        return path.endswith((".py", ".js", ".ts", ".go", ".java", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".rs", ".php", ".rb", ".md"))

    def _process(self, path: str):
        if self._is_valid_code_file(path):
            logger.info(f"File modified/created: {path}")
            asyncio.run_coroutine_threadsafe(
                self.service.index_file(path, self.repo_id),
                self.loop
            )

    def _process_delete(self, path: str):
        if self._is_valid_code_file(path):
            logger.info(f"File deleted: {path}")
            asyncio.run_coroutine_threadsafe(
                self.service.remove_file(path, self.repo_id),
                self.loop
            )

    def _process_move(self, src: str, dest: str):
        src_valid = self._is_valid_code_file(src)
        dest_valid = self._is_valid_code_file(dest)

        if src_valid and dest_valid:
            logger.info(f"File moved: {src} -> {dest}")
            asyncio.run_coroutine_threadsafe(
                self.service.move_file(src, dest, self.repo_id),
                self.loop
            )
        elif src_valid and not dest_valid:
            # Moved out of valid scope -> Treat as delete
            self._process_delete(src)
        elif not src_valid and dest_valid:
            # Moved into valid scope -> Treat as create
            self._process(dest)

class RepoWatcher:
    """
    Watches a single repository directory using the global observer.
    """
    def __init__(self, path: str, repo_id: int):
        self.path = path
        self.repo_id = repo_id
        self.service = IndexingService()

    def start(self):
        logger.info(f"Starting RepoWatcher on {self.path} (Repo ID: {self.repo_id})")
        loop = asyncio.get_running_loop()
        event_handler = IndexingEventHandler(self.service, self.repo_id, loop)
        observer_manager.schedule(event_handler, self.path, recursive=True)

    def stop(self):
        observer_manager.unschedule(self.path)


class ProjectDiscoveryEventHandler(FileSystemEventHandler):
    def __init__(self, root_path: str, loop: asyncio.AbstractEventLoop):
        self.root_path = root_path
        self.loop = loop

    def on_created(self, event):
        if not event.is_directory: return
        parent = os.path.dirname(event.src_path)
        if os.path.abspath(parent) != os.path.abspath(self.root_path): return
        logger.info(f"Project Created (Detected): {event.src_path}")

    def on_moved(self, event):
        if not event.is_directory: return
        parent = os.path.dirname(event.src_path)
        if os.path.abspath(parent) != os.path.abspath(self.root_path): return
        # Ensure dest is also in root (rename)
        dest_parent = os.path.dirname(event.dest_path)
        if os.path.abspath(dest_parent) != os.path.abspath(self.root_path): return

        logger.info(f"Project Moved/Renamed (Detected): {event.src_path} -> {event.dest_path}")
        self._schedule_async(self._handle_project_moved(event.src_path, event.dest_path))

    def _schedule_async(self, coro):
        asyncio.run_coroutine_threadsafe(coro, self.loop)

    async def _handle_project_created(self, project_path: str):
        try:
            from app.domain.codebase.indexing.manager import indexing_manager
            repo_name = os.path.basename(project_path)
            service = IndexingService()
            
            # 1. Check if we can map this path to an existing Project ID (Re-import case)
            project_id = None
            try:
                # Local Scan/Context check
                projects = await project_context_manager.scan_projects()
                abs_path = os.path.abspath(project_path)
                for p in projects:
                    if p.get("path") and os.path.abspath(p.get("path")) == abs_path:
                        project_id = p.get("id")
                        logger.info(f"[AutoLink] Found existing project ID {project_id} for {repo_name}")
                        break
                
                # If local scan failed, maybe check Cloud API for "Disconnected" projects?
                # For now, we trust scan_projects() which reads DB + Settings. 
                # Improving robust matching: Maybe check by name if path logic fails?
                # Let's stick to strict path first, fallback to Create.
            except Exception as e:
                logger.warning(f"Project resolution check failed: {e}")

            # 2. If new, Create in Cloud
            if not project_id:
                logger.info(f"[AutoSync] Creating new project '{repo_name}' in Cloud...")
                try:
                    res = await imagicbox_client.create_project(
                        name=repo_name,
                        description=f"Imported from {project_path}",
                        path=project_path
                    )
                    if res.get("code") == 0: # Success
                        project_id = res["data"]["id"]
                        logger.info(f"[AutoSync] Success! Cloud Project ID: {project_id}")
                    else:
                        logger.error(f"[AutoSync] Creation Failed: {res.get('message')}")
                        # Fallback: Proceed with default ID 1? Or Abort?
                        # If we proceed with ID 1, we risk polluting default project.
                        # Safe Mode: Abort and let user correct it.
                        # But user wants auto.
                        # Maybe we try to find by Name as fallback?
                        # For now, if creation fails (e.g. duplicate name), we log error.
                        return 
                except Exception as e:
                    logger.error(f"[AutoSync] API Error: {e}")
                    return

            # 3. Create/Link Local Repo
            repo = await service.get_or_create_repo(project_path, repo_name, project_id=project_id)
            
            # 4. Start Watching & Indexing
            await indexing_manager.start_watching(project_path, repo.id)
            indexing_manager.run_indexing_background(repo.id)
            
        except Exception as e:
            logger.error(f"Error handling new project {project_path}: {e}")

    async def _handle_project_deleted(self, project_path: str):
        try:
            from app.domain.codebase.indexing.manager import indexing_manager
            service = IndexingService()
            repo_name = os.path.basename(project_path)
            
            # 1. Stop Watching Locally
            await indexing_manager.stop_watching(project_path)
            
            # 2. Safety First: Disconnect Cloud Project (Do NOT delete data)
            # Find ID
            repo = await service.get_repo_by_path(project_path)
            if repo and repo.project_id:
                logger.info(f"[AutoSync] Project {repo_name} (ID: {repo.project_id}) disconnected locally.")
                # Optional: Inform Cloud "I am disconnected"?
                # Current API doesn't have "Disconnect" status, so we just do nothing on API side.
                # Data remains safe.
            else:
                logger.info(f"Project deleted locally: {repo_name} (No active link found)")

        except Exception as e:
            logger.error(f"Error handling deleted project {project_path}: {e}")

    async def _handle_project_moved(self, src_path: str, dest_path: str):
        try:
            from app.domain.codebase.indexing.manager import indexing_manager
            service = IndexingService()
            new_name = os.path.basename(dest_path)
            
            # 1. Find Repo based on OLD path
            repo = await service.get_repo_by_path(src_path)
            if not repo:
                # Maybe treated as Delete + Create?
                logger.warning(f"Move source {src_path} not found in index. Treating as New.")
                await self._handle_project_created(dest_path)
                return

            project_id = repo.project_id
            
            # 2. Update Cloud Path & Name
            if project_id:
                logger.info(f"[AutoSync] Renaming Project ID {project_id} -> {new_name}")
                await imagicbox_client.update_project(
                    project_id=project_id,
                    name=new_name,
                    path=dest_path
                )

            # 3. Update Local Repo
            # We need to update existing repo record.
            # IndexingService doesn't have explicit update_repo method exposed nicely,
            # but we can do manual update via service.session_factory if we want or add method.
            # actually, IndexingService is a helper.
            # Let's add a small helper here or use internal logic? 
            # I can just re-bind.
            
            # Easier: Stop Old Watch -> Update DB -> Start New Watch
            await indexing_manager.stop_watching(src_path)
            
            async with service.session_factory() as session:
                r = await session.get(type(repo), repo.id)
                if r:
                    r.local_path = dest_path
                    r.name = new_name
                    session.add(r)
                    await session.commit()
            
            await indexing_manager.start_watching(dest_path, repo.id)
            logger.info(f"Project link updated: {src_path} -> {dest_path}")
            
        except Exception as e:
            logger.error(f"Error handling moved project {src_path}: {e}")


class ProjectDiscoveryWatcher:
    """
    Watches the PROJECTS_ROOT using the global observer.
    """
    def __init__(self, root_path: str):
        self.root_path = root_path

    def start(self):
        if not os.path.exists(self.root_path):
            logger.warning(f"Root path {self.root_path} does not exist. Cannot watch for new projects.")
            return

        logger.info(f"Starting Project Discovery Watcher on: {self.root_path}")
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # If explicit loop needed or not running (should be running in server)
            loop = asyncio.new_event_loop()
            
        event_handler = ProjectDiscoveryEventHandler(self.root_path, loop)
        observer_manager.schedule(event_handler, self.root_path, recursive=True)

    def stop(self):
        observer_manager.unschedule(self.root_path)
