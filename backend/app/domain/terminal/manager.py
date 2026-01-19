import logging
import os
import subprocess

from app.i18n.service import i18n

logger = logging.getLogger(__name__)


class TerminalManager:
    """
    Manages a persistent shell session context (CWD + Env).
    Does NOT use PTY for now (to avoid WebSocket complexity), but emulates statefulness.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TerminalManager, cls).__new__(cls)
            cls._instance.cwd = os.getcwd()
            cls._instance.env = os.environ.copy()
            # Default to reasonable path
            cls._instance.env["TERM"] = "xterm-256color"
        return cls._instance

    def run_command(self, command: str, timeout: int = 60) -> tuple[str, str, int]:
        """
        Runs a command in the persistent context.
        Supports 'cd' and variable exports by parsing them.
        """
        command = command.strip()

        # 1. Handle 'cd' manually
        if command.startswith("cd "):
            path = command[3:].strip()
            return self._change_directory(path)

        # 2. Handle 'export' manually (simple case)
        if command.startswith("export "):
            return self._handle_export(command)

        # 3. Run actual subprocess
        try:
            logger.info(f"Running command: '{command}' in {self.cwd}")
            process = subprocess.run(
                command,
                cwd=self.cwd,
                env=self.env,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )

            stdout = process.stdout
            stderr = process.stderr
            returncode = process.returncode

            return stdout, stderr, returncode

        except subprocess.TimeoutExpired:
            return "", i18n.get("prompts.domain_tools.terminal.timeout"), 124
        except Exception as e:
            return "", str(e), 1

    def _change_directory(self, path: str) -> tuple[str, str, int]:
        # Resolve absolute path relative to current tracked CWD
        new_path = os.path.abspath(os.path.join(self.cwd, path))

        if os.path.isdir(new_path):
            self.cwd = new_path
            return i18n.get("prompts.domain_tools.terminal.cd_success", path=self.cwd), "", 0
        else:
            return "", i18n.get("prompts.domain_tools.terminal.cd_error", path=path, resolved=new_path), 1

    def _handle_export(self, command: str) -> tuple[str, str, int]:
        # export KEY=VALUE
        # Remove 'export '
        kv = command[7:].strip()
        if "=" in kv:
            key, value = kv.split("=", 1)
            # Remove quotes
            value = value.strip("'").strip('"')
            self.env[key] = value
            return i18n.get("prompts.domain_tools.terminal.export_success", key=key), "", 0

        return "", i18n.get("prompts.domain_tools.terminal.export_error"), 1


# Global singleton
terminal_manager = TerminalManager()
