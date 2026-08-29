import asyncio
import json
import logging
import os

from app.core.monitoring.activity import activity_monitor

logger = logging.getLogger(__name__)


class NativeMixin:
    @classmethod
    async def _handle_native(cls, thread_id, payload, extracted_data):
        script_path = payload.get("script_path")
        command = payload.get("command", "python3")
        args = payload.get("args", [])
        sync_state = payload.get("sync_state")

        if not script_path:
            logger.error(f"[{thread_id}] No script_path provided for native step")
            return

        # G5: default-deny whitelist (command + script_prefix + sha256)
        from app.core.atlas.script_gate import check_native_allowed

        check_native_allowed(command, script_path)

        cmd_list = [command, script_path] + [str(a) for a in args]

        logger.info(f"[{thread_id}] Executing native script: {' '.join(cmd_list)}")
        await activity_monitor.log_event(
            "macro_thought",
            {"text": f"Running native script: {' '.join(cmd_list)}"},
            thread_id,
        )

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd_list,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)

            if process.returncode != 0:
                err_msg = stderr.decode().strip()
                logger.error(
                    "[%s] Native script failed with code %s: %s",
                    thread_id,
                    process.returncode,
                    err_msg,
                )
                raise ValueError(
                    f"Native script exited with code {process.returncode}: {err_msg}"
                )

            if sync_state and os.path.exists(sync_state):
                with open(sync_state, encoding="utf-8") as f:
                    state_data = json.load(f)

                items = state_data.get("items", [])
                if items:
                    extracted_data["batch_items"] = items
                    logger.info(
                        f"[{thread_id}] Synced {len(items)} items from {sync_state} to extracted_data"
                    )

        except asyncio.TimeoutError:
            logger.error("[%s] Native script timed out after 300s", thread_id)
            raise
        except Exception:
            logger.exception("[%s] Failed to execute native script", thread_id)
            raise
