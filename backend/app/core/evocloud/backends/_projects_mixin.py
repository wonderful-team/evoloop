"""EvoCloud projects mixin: projects, tasks, budget, timesheet, statistics."""

from app.constants import DEFAULT_PROJECT_ID
from app.core.config import settings
from app.core.identity import identity_service


class ProjectsMixin:
    """Project and task management API methods."""

    async def get_projects(
        self, page=1, page_size=100, token: str | None = None
    ) -> dict:
        return await self.request(
            "GET", "/projectmanage/api/projectOpen/projects",
            params={"page": page, "page_size": page_size}, token=token,
        )

    async def create_project(
        self, name: str, description: str, path: str, token: str | None = None
    ) -> dict:
        device_key = await identity_service.store.get_device_key()
        payload = {
            "name": name,
            "description": description,
            "path": path,
            "source": device_key or settings.SERVICE_NAME,
        }
        return await self.request(
            "POST", "/projectmanage/api/projectOpen/createProject",
            data=payload, token=token,
        )

    async def update_project(
        self,
        project_id: int,
        description: str = None,
        name: str = None,
        path: str = None,
        source: str = None,
        token: str | None = None,
    ) -> dict:
        data = {"project_id": project_id}
        if description is not None:
            data["project_desc"] = description
        if name is not None:
            data["name"] = name
        if path is not None:
            data["path"] = path
        if source is not None:
            data["source"] = source
        return await self.request(
            "POST", "/projectmanage/api/projectOpen/updateProject",
            data=data, token=token,
        )

    async def delete_project(self, project_id: int, token: str | None = None) -> dict:
        return await self.request(
            "POST", "/projectmanage/api/projectOpen/deleteProject",
            data={"project_id": project_id}, token=token,
        )

    async def get_current_project(self, token: str | None = None) -> dict:
        return await self.request(
            "GET", "/projectmanage/api/projectOpen/getCurrentProject", token=token
        )

    async def get_project_tasks(
        self, project_id: int, page=1, page_size=50, status=None, token=None
    ) -> dict:
        p = {"project_id": project_id, "page": page, "page_size": page_size}
        if status is not None:
            p["status"] = status
        return await self.request(
            "GET", "/projectmanage/api/task/projectTasks", params=p, token=token
        )

    async def get_task_detail(self, task_id: int, token=None) -> dict:
        return await self.request(
            "GET", f"/projectmanage/api/task/detail/{task_id}", token=token
        )

    async def create_task(self, data: dict, token=None) -> dict:
        return await self.request(
            "POST", "/projectmanage/api/task/create", data=data, token=token
        )

    async def update_task(self, task_id: int, data: dict, token=None) -> dict:
        return await self.request(
            "PUT", f"/projectmanage/api/task/update/{task_id}", data=data, token=token
        )

    async def delete_task(self, task_id: int, token=None) -> dict:
        return await self.request(
            "DELETE", "/projectmanage/api/task/delete",
            data={"task_id": task_id}, token=token,
        )

    async def update_task_status(
        self, task_id: int, status: int, progress: int = 0, token=None
    ) -> dict:
        return await self.request(
            "POST", "/projectmanage/api/task/updateStatus",
            data={"task_id": task_id, "status": status, "progress": progress},
            token=token,
        )

    async def get_budget_list(
        self, project_id: int, page=1, page_size=50, token=None
    ) -> dict:
        return await self.request(
            "GET", "/projectmanage/api/budget/lists",
            params={"project_id": project_id, "page": page, "page_size": page_size},
            token=token,
        )

    async def get_budget_overview(self, project_id: int, token=None) -> dict:
        return await self.request(
            "GET", "/projectmanage/api/budget/overview",
            params={"project_id": project_id}, token=token,
        )

    async def get_timesheet_list(
        self, project_id: int, page=1, page_size=50, token=None
    ) -> dict:
        return await self.request(
            "GET", "/projectmanage/api/timesheet/lists",
            params={"project_id": project_id, "page": page, "page_size": page_size},
            token=token,
        )

    async def add_timesheet_quick(self, data: dict, token=None) -> dict:
        return await self.request(
            "POST", "/projectmanage/api/timesheet/quickAdd", data=data, token=token
        )

    async def get_project_statistics(
        self, project_id=DEFAULT_PROJECT_ID, token=None
    ) -> dict:
        p = {"project_id": project_id} if project_id is not None else {}
        return await self.request(
            "GET", "/projectmanage/api/project/statistics", params=p, token=token
        )
