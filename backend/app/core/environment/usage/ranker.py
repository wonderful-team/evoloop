"""
UsageRanker - OS-native application activity analysis.

Queries macOS (via mdfind/mdls) and Android (via adb usagestats) to determine
a priority score for each installed application. This score drives the Curious
Scan to focus on the apps the user actually uses.

Integration point: Called from EnvironmentProbe.probe_macos() and
injected into the AwakenedState so that ActiveExplorer can prioritize
without re-running shell commands.
"""

import asyncio
import logging
import os
import subprocess
from datetime import datetime, timezone

from app.core.environment.schemas import AppUsageRecord

logger = logging.getLogger(__name__)

# How many top apps to scan in each cycle
DEFAULT_TOP_N = 5

# Score weights
W_RECENCY = 0.5     # How recently was it used?
W_FREQUENCY = 0.3   # How much total time was spent?
W_RUNNING = 0.2     # Is it currently running?

# Maximum age in days for recency scoring (older → score = 0)
MAX_AGE_DAYS = 30


# Removed local AppUsageRecord dataclass to use centralized Pydantic model from models.py


class UsageRanker:
    """
    Ranks installed applications by usage priority.

    Supports:
    - macOS: Uses Spotlight metadata (mdfind + mdls) for last-used timestamps.
    - Android: Uses ADB usagestats dump for total foreground time.
    """

    # ------------------------------------------------------------------ macOS

    @classmethod
    def rank_macos_apps(
        cls,
        app_names: list[str],
        top_n: int = DEFAULT_TOP_N,
    ) -> list[AppUsageRecord]:
        """
        Query macOS Spotlight and running processes for usage stats.
        """
        records: list[AppUsageRecord] = []
        running_apps = cls._get_running_macos_apps()

        # 1. Try a bulk query for recently used apps first
        try:
            bulk_cmd = [
                "mdfind",
                "kMDItemKind == 'Application' && kMDItemLastUsedDate > $time.now(-30d)",
            ]
            result = subprocess.run(bulk_cmd, capture_output=True, text=True, timeout=10)
            recent_paths = [p.strip() for p in result.stdout.splitlines() if p.strip().endswith(".app")]

            if not recent_paths:
                # Relaxed query: any app with usage metadata
                bulk_cmd = ["mdfind", "kMDItemKind == 'Application' && kMDItemLastUsedDate > $time.now(-365d)"]
                result = subprocess.run(bulk_cmd, capture_output=True, text=True, timeout=5)
                recent_paths = [p.strip() for p in result.stdout.splitlines() if p.strip().endswith(".app")]

            # Process paths
            for path in recent_paths[:50]:
                record = cls._probe_macos_path(path)
                if record:
                    records.append(record)
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, subprocess.TimeoutExpired) as e:
            logger.debug(f"[UsageRanker] Bulk macOS probe failed: {e}", exc_info=True)

        # 2. Ensure all running apps and provided app_names are considered
        existing_bundle_ids = {r.bundle_id for r in records}
        existing_names = {r.app_name for r in records}

        # Candidates for individual probing if we have very little data
        candidates = list(running_apps | set(app_names[:20]))

        if len(records) < top_n:
            for name in candidates:
                if name in existing_names:
                    continue
                if len(records) >= top_n * 3:
                    break

                # Try individual probe for high-likelihood candidates
                record = cls._probe_macos_app(name)
                if record:
                    records.append(record)
                else:
                    # Minimum fallback
                    records.append(AppUsageRecord(
                        app_name=name,
                        bundle_id=name,
                        platform="macos"
                    ))

        # 3. Apply running boost and score
        for r in records:
            if r.app_name in running_apps or r.bundle_id in running_apps:
                r.is_running = True
            else:
                r.is_running = False

        cls._compute_priority_scores(records)
        records.sort(key=lambda r: r.priority_score, reverse=True)
        return records[:top_n]

    @staticmethod
    def _get_running_macos_apps() -> set[str]:
        """Get names of currently running non-background processes via AppleScript."""
        try:
            from app.infrastructure.drivers.macos import macos_driver

            script = 'tell application "System Events" to get name of every process whose background only is false'
            output = macos_driver.run_applescript(script)
            if output:
                return {name.strip() for name in output.split(",")}
        except Exception as e:
            logger.debug(f"[UsageRanker] Failed to get running apps: {e}", exc_info=True)
        return set()

    @classmethod
    def _probe_macos_path(cls, app_path: str) -> AppUsageRecord | None:
        """Helper to probe a specific path instead of searching by name."""
        app_name = os.path.basename(app_path).replace(".app", "")
        bundle_id = cls._mdls_get(app_path, "kMDItemCFBundleIdentifier") or app_name
        last_used_str = cls._mdls_get(app_path, "kMDItemLastUsedDate")

        last_used_at = None
        if last_used_str and last_used_str != "(null)":
            try:
                # mdls returns: "2026-02-19 13:11:06 +0000"
                last_used_at = datetime.strptime(last_used_str.strip(), "%Y-%m-%d %H:%M:%S %z")
            except Exception as e:
                logger.debug("Suppressed error: %s", e, exc_info=True)

        return AppUsageRecord(
            app_name=app_name,
            bundle_id=bundle_id,
            platform="macos",
            last_used_at=last_used_at,
        )

    @classmethod
    def _probe_macos_app(cls, app_name: str) -> AppUsageRecord | None:
        """
        Use mdfind + mdls to get the last-used date and kMDItemLastUsedDate.
        Falls back gracefully if Spotlight is unavailable.
        """
        # mdfind to resolve .app path
        find_cmd = [
            "mdfind",
            f"kMDItemDisplayName == '{app_name}' && kMDItemKind == 'Application'",
        ]
        try:
            result = subprocess.run(find_cmd, capture_output=True, text=True, timeout=5)
            app_paths = [
                p.strip()
                for p in result.stdout.splitlines()
                if p.strip().endswith(".app")
            ]
        except Exception as e:
            logger.debug("Suppressed error: %s", e, exc_info=True)
            return None

        if not app_paths:
            return None

        app_path = app_paths[0]
        # Extract bundle ID from mdls
        bundle_id = cls._mdls_get(app_path, "kMDItemCFBundleIdentifier") or app_name
        last_used_str = cls._mdls_get(app_path, "kMDItemLastUsedDate")

        last_used_at: datetime | None = None
        if last_used_str and last_used_str != "(null)":
            try:
                # mdls returns: "2026-02-19 13:11:06 +0000"
                last_used_at = datetime.strptime(
                    last_used_str.strip(), "%Y-%m-%d %H:%M:%S %z"
                )
            except ValueError:
                logger.debug(f"[UsageRanker] Cannot parse date: {last_used_str!r}", exc_info=True)

        return AppUsageRecord(
            app_name=app_name,
            bundle_id=bundle_id,
            platform="macos",
            last_used_at=last_used_at,
            total_foreground_ms=0,  # Spotlight doesn't expose cumulative time
        )

    @staticmethod
    def _mdls_get(app_path: str, attribute: str) -> str | None:
        """Run mdls for a single attribute and return its string value."""
        try:
            result = subprocess.run(
                ["mdls", "-name", attribute, "-raw", app_path],
                capture_output=True,
                text=True,
                timeout=5,
            )
            value = result.stdout.strip()
            return value if value and value != "(null)" else None
        except Exception as e:
            logger.debug("Suppressed error: %s", e, exc_info=True)
            return None

    # ---------------------------------------------------------------- Android

    @classmethod
    async def rank_android_apps(
        cls,
        device_id: str,
        package_names: list[str],
        top_n: int = DEFAULT_TOP_N,
    ) -> list[AppUsageRecord]:
        """
        Query Android ADB usagestats for foreground time per package.

        Args:
            device_id: ADB device serial.
            package_names: List of package names to evaluate.
            top_n: How many apps to return.

        Returns:
            Sorted list of AppUsageRecord (highest priority first).
        """
        records: list[AppUsageRecord] = []
        raw_stats = await cls._dump_android_usagestats(device_id)

        for pkg in package_names:
            stats = raw_stats.get(pkg, {})
            last_used_ms = stats.get("lastTimeUsed", 0)
            total_ms = stats.get("totalTimeInForeground", 0)

            last_used_at: datetime | None = None
            if last_used_ms:
                try:
                    last_used_at = datetime.fromtimestamp(last_used_ms / 1000, tz=timezone.utc)
                except Exception as e:
                    logger.debug("Suppressed error: %s", e, exc_info=True)

            records.append(
                AppUsageRecord(
                    app_name=pkg.split(".")[-1],  # Friendly name from package
                    bundle_id=pkg,
                    platform="android",
                    last_used_at=last_used_at,
                    total_foreground_ms=total_ms,
                )
            )

        cls._compute_priority_scores(records)
        records.sort(key=lambda r: r.priority_score, reverse=True)
        return records[:top_n]

    @staticmethod
    async def _dump_android_usagestats(device_id: str) -> dict[str, dict]:
        """
        Parse output of `adb shell dumpsys usagestats` for the last 7 days.
        Returns: { "com.example.app": {"lastTimeUsed": ms, "totalTimeInForeground": ms} }
        """
        raw: dict[str, dict] = {}
        try:
            proc = await asyncio.create_subprocess_exec(
                "adb", "-s", device_id, "shell", "dumpsys", "usagestats",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
            lines = stdout.decode(errors="replace").splitlines()

            current_pkg: str | None = None
            for line in lines:
                line = line.strip()
                if line.startswith("package="):
                    current_pkg = line.split("=", 1)[1].strip()
                    raw.setdefault(current_pkg, {})
                elif current_pkg:
                    if "lastTimeUsed=" in line:
                        try:
                            val = line.split("lastTimeUsed=")[1].split()[0]
                            raw[current_pkg]["lastTimeUsed"] = int(val)
                        except (ValueError, IndexError):
                            pass
                    if "totalTimeInForeground=" in line:
                        try:
                            val = line.split("totalTimeInForeground=")[1].split()[0]
                            raw[current_pkg]["totalTimeInForeground"] = int(val)
                        except (ValueError, IndexError):
                            pass
        except asyncio.TimeoutError:
            logger.warning(f"[UsageRanker] ADB usagestats timed out for device {device_id}", exc_info=True)
        except Exception as e:
            logger.warning(f"[UsageRanker] ADB usagestats failed: {e}", exc_info=True)

        return raw

    # -------------------------------------------------------- Scoring logic

    @classmethod
    def _compute_priority_scores(cls, records: list[AppUsageRecord]) -> None:
        """
        Compute normalized priority scores in-place.

        Score = W_RECENCY * recency_score + W_FREQUENCY * frequency_score
        Both sub-scores are normalized 0-1 within the current batch.
        """
        now = datetime.now(tz=timezone.utc)
        max_age_secs = MAX_AGE_DAYS * 86400

        # Recency scores
        recency_raw: list[float] = []
        for r in records:
            if r.last_used_at:
                last_used = r.last_used_at
                if last_used.tzinfo is None:
                    last_used = last_used.replace(tzinfo=timezone.utc)
                age_secs = max(0.0, (now - last_used).total_seconds())
                recency_raw.append(max(0.0, 1.0 - age_secs / max_age_secs))
            else:
                recency_raw.append(0.0)

        # Frequency scores (normalize by max in batch)
        max_freq = max((r.total_foreground_ms for r in records), default=1) or 1
        freq_raw = [r.total_foreground_ms / max_freq for r in records]

        for i, record in enumerate(records):
            running_val = 1.0 if record.is_running else 0.0
            record.priority_score = round(
                W_RECENCY * recency_raw[i]
                + W_FREQUENCY * freq_raw[i]
                + W_RUNNING * running_val,
                4,
            )
