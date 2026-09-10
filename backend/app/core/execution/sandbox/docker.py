import asyncio
import logging

import docker
from docker.errors import NotFound

from app.core.execution.sandbox.base import Sandbox, SandboxProcess
from app.core.project.utils import resolve_member_workspace_root

logger = logging.getLogger(__name__)


def _to_container_path(host_path: str, workspace_root: str) -> str | None:
    """Translate a host path under the workspace mount into the container path.

    WORKSPACE_ROOT is bind-mounted to ``/workspace``; paths outside it are not
    accessible inside the container and return ``None``.
    """
    host_path = host_path.rstrip("/")
    workspace_root = workspace_root.rstrip("/")
    if host_path == workspace_root:
        return "/workspace"
    if host_path.startswith(workspace_root + "/"):
        return "/workspace" + host_path[len(workspace_root) :]
    return None


class DockerSandboxProcess(SandboxProcess):
    """Handle to a command running via ``exec`` inside the sandbox container."""

    def __init__(
        self, client, container_name: str, exec_id: str, stream_task: asyncio.Task
    ):
        self._client = client
        self._container_name = container_name
        self._exec_id = exec_id
        self._stream_task = stream_task
        self._pid: int | None = None

    @property
    def pid(self) -> int | None:
        return self._pid

    async def wait(self, timeout: float) -> int:
        loop = asyncio.get_running_loop()
        start = loop.time()
        while True:
            try:
                info = self._client.api.exec_inspect(self._exec_id)
            except docker.errors.NotFound:
                return -1
            if not info.get("Running"):
                try:
                    await asyncio.wait_for(self._stream_task, timeout=5.0)
                except asyncio.TimeoutError:
                    pass
                pid = info.get("Pid")
                if pid:
                    self._pid = int(pid)
                return int(info.get("ExitCode", -1))
            if loop.time() - start > timeout:
                raise asyncio.TimeoutError()
            await asyncio.sleep(0.2)

    def _signal_exec(self, signal_name: str) -> None:
        """Send a signal to the exec process (and its children) inside the container."""
        try:
            info = self._client.api.exec_inspect(self._exec_id)
            pid = info.get("Pid")
            if not pid:
                return
            container = self._client.containers.get(self._container_name)
            container.exec_run(["kill", "-s", signal_name, str(pid)])
            container.exec_run(["pkill", "-s", signal_name, "-P", str(pid)])
        except Exception:
            logger.warning("[DockerSandbox] exec %s failed", signal_name, exc_info=True)

    def terminate(self) -> None:
        self._signal_exec("TERM")

    def kill(self) -> None:
        self._signal_exec("KILL")


class DockerSandbox(Sandbox):
    """
    Executes commands inside a per-user Docker container.

    多租户按用户隔离：每个 member 一个独立容器
    ``evoloop-sandbox-runtime-<member_id>``，仅 bind 挂载该用户的
    workspace 子目录（容器内看不到任何其他用户目录/宿主文件系统）。
    """

    def __init__(self, image_name: str, member_id: int):
        self.image_name = image_name
        self.client = docker.from_env()
        self.member_id = int(member_id)
        self.container_name = f"evoloop-sandbox-runtime-{self.member_id}"
        self.container = None
        self._initialize_container()

    def _initialize_container(self):
        """Start or reuse the sandbox container."""
        member_root = resolve_member_workspace_root(self.member_id)
        if not member_root:
            raise RuntimeError(
                f"Member workspace root unavailable for member {self.member_id} "
                "(WORKSPACE_ROOT not configured or member identity missing); "
                "refusing to start an isolated sandbox without a per-user mount"
            )
        # Captured at container creation so spawn() translates host paths against
        # the exact mount this container was started with.
        self.workspace_root = member_root.rstrip("/")

        try:
            # Check if exists
            try:
                self.container = self.client.containers.get(self.container_name)
                if self.container.status != "running":
                    self.container.start()
            except NotFound:
                # Create and start
                # Mount the member workspace (ONLY this directory) to /workspace
                mounts = {
                    member_root: {
                        "bind": "/workspace",
                        "mode": "rw",
                    }
                }

                logger.info(
                    f"Starting Docker Sandbox for member {self.member_id} "
                    f"with image {self.image_name} (mount {member_root})"
                )
                self.container = self.client.containers.run(
                    self.image_name,
                    command="tail -f /dev/null",  # Keep alive
                    detach=True,
                    name=self.container_name,
                    volumes=mounts,
                    working_dir="/workspace",
                    security_opt=["no-new-privileges"],
                    read_only=False,
                    mem_limit="4g",
                    nano_cpus=2_000_000_000,  # 2 CPU cores
                    pids_limit=256,
                )

        except Exception as e:
            logger.exception(f"Failed to initialize Docker Sandbox: {e}")
            raise

    async def spawn(
        self,
        command: str,
        *,
        working_dir: str | None = None,
        on_output=None,
        stdout_buf: list[str] | None = None,
        stderr_buf: list[str] | None = None,
    ) -> SandboxProcess:
        if not self.container:
            raise RuntimeError("Sandbox container not initialized")

        container_wd = "/workspace"
        if working_dir:
            container_wd = _to_container_path(working_dir, self.workspace_root)
            if container_wd is None:
                raise RuntimeError(
                    f"Working directory {working_dir!r} is outside WORKSPACE_ROOT "
                    f"({self.workspace_root!r}) and not mounted in the sandbox"
                )

        wrapped = (
            f"cd {container_wd} && {command}"
            if container_wd != "/workspace"
            else command
        )

        loop = asyncio.get_running_loop()
        exec_id = self.client.api.exec_create(
            self.container.id,
            ["/bin/sh", "-c", wrapped],
            user="root",
        )["Id"]
        stream = self.client.api.exec_start(exec_id, stream=True, demux=True)

        def _stream():
            for stdout_chunk, stderr_chunk in stream:
                if stdout_chunk:
                    text = stdout_chunk.decode("utf-8", errors="replace")
                    if stdout_buf is not None:
                        stdout_buf.append(text)
                    if on_output is not None:
                        loop.call_soon_threadsafe(on_output, text)
                if stderr_chunk:
                    text = stderr_chunk.decode("utf-8", errors="replace")
                    if stderr_buf is not None:
                        stderr_buf.append(text)
                    if on_output is not None:
                        loop.call_soon_threadsafe(on_output, "[stderr] " + text)

        stream_task = asyncio.create_task(asyncio.to_thread(_stream))
        return DockerSandboxProcess(
            self.client, self.container_name, exec_id, stream_task
        )

    def upload_file(self, local_path: str, remote_path: str) -> None:
        # Bind mount covers WORKSPACE_ROOT automatically; manual copies for the
        # rest are not implemented for this phase.
        pass

    def download_file(self, remote_path: str, local_path: str) -> None:
        # Bind mount handles this.
        pass

    def teardown(self) -> None:
        if self.container:
            try:
                self.container.stop()
                self.container.remove()
            except Exception as e:
                logger.warning(f"Error tearing down sandbox: {e}", exc_info=True)
