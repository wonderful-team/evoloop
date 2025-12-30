from typing import Dict, List, Any, Optional
import time

class ActivityMonitor:
    _instance = None
    
    def __init__(self):
        # Structure: { thread_id: { status: str, tasks: List[Dict], artifacts: List[Dict], updated_at: float } }
        self._runs: Dict[str, Dict[str, Any]] = {}
        
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
        
    def start_run(self, thread_id: str, main_goal: str = "处理用户请求"):
        self._runs[thread_id] = {
            "status": "running",
            "main_goal": main_goal,
            "agent_state": {}, # { mode, task_name, task_status }
            "verification": {}, # { status: 'passed'|'failed', summary: str }
            "tasks": [],     # { id, name, status, time, details }
            "artifacts": [], # { id, name, type, status, path }
            "updated_at": time.time()
        }
    
    def end_run(self, thread_id: str, status="done"):
        if thread_id in self._runs:
            # If we were stopping, ensure final status is cancelled
            current_status = self._runs[thread_id]["status"]
            if current_status == "stopping":
                status = "cancelled"
                
            self._runs[thread_id]["status"] = status
            self._runs[thread_id]["updated_at"] = time.time()
            # Mark all running tasks as done or cancelled
            for task in self._runs[thread_id]["tasks"]:
                if task["status"] == "running":
                    task["status"] = "cancelled" if status == "cancelled" else "done"

    def stop_run(self, thread_id: str):
        """Signal a run to stop."""
        if thread_id in self._runs:
            self._runs[thread_id]["status"] = "stopping"
            self._runs[thread_id]["updated_at"] = time.time()

    def check_cancellation(self, thread_id: str):
        """Check if run is marked for stopping and raise exception if so."""
        if thread_id in self._runs:
            if self._runs[thread_id]["status"] == "stopping":
                raise InterruptedError("Cancelled by user")

    
    def add_task(self, thread_id: str, name: str, task_type="node"):
        if thread_id not in self._runs:
            return None
        
        task_id = len(self._runs[thread_id]["tasks"]) + 1
        new_task = {
            "id": task_id,
            "name": name,
            "status": "running",
            "type": task_type,
            "start_time": time.time(),
            "time": "0s"
        }
        self._runs[thread_id]["tasks"].append(new_task)
        self._runs[thread_id]["updated_at"] = time.time()
        return task_id

    def update_task(self, thread_id: str, task_id: int, status: str, details: str = None):
        if thread_id not in self._runs:
            return
        
        for task in self._runs[thread_id]["tasks"]:
            if task["id"] == task_id:
                task["status"] = status
                if details:
                    task["details"] = details
                if status in ["done", "failed"]:
                    duration = time.time() - task["start_time"]
                    task["time"] = f"{duration:.2f}s"
                break
        self._runs[thread_id]["updated_at"] = time.time()

    def add_artifact(self, thread_id: str, name: str, artifact_type: str, status="created", path: str = None):
        if thread_id not in self._runs:
            return
            
        # Check uniqueness
        for art in self._runs[thread_id]["artifacts"]:
            if art["name"] == name:
                art["status"] = "modified"
                return
        
        self._runs[thread_id]["artifacts"].append({
            "id": len(self._runs[thread_id]["artifacts"]) + 1,
            "name": name,
            "type": artifact_type,
            "status": status,
            "path": path,
            "icon": "FileCode" # Default for now
        })
        self._runs[thread_id]["updated_at"] = time.time()

    def get_activity(self, thread_id: str):
        return self._runs.get(thread_id, {
            "status": "idle",
            "tasks": [],
            "artifacts": []
        })

# Global Instance
activity_monitor = ActivityMonitor.get_instance()
