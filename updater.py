import asyncio
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Dict, Any, Tuple, Optional

logger = logging.getLogger("Updater")

UPDATE_MARKER_FILE = Path(__file__).parent / ".update_in_progress"

async def _run_cmd(*args: str, timeout: float = 30.0) -> Tuple[int, str, str]:
    """Runs a shell command asynchronously with timeout."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return (
            proc.returncode if proc.returncode is not None else 1,
            stdout.decode(errors="replace").strip(),
            stderr.decode(errors="replace").strip()
        )
    except asyncio.TimeoutError:
        return 1, "", f"Таймаут выполнения команды ({timeout}s)"
    except Exception as e:
        return 1, "", str(e)


async def get_current_version_info() -> Dict[str, str]:
    """Returns local git commit info: hash, date, message, branch."""
    # Commit hash
    code, commit, _ = await _run_cmd("git", "rev-parse", "--short", "HEAD")
    if code != 0:
        commit = "unknown"

    # Commit date
    code, date_str, _ = await _run_cmd("git", "log", "-1", "--format=%cd", "--date=format:%d.%m.%Y %H:%M")
    if code != 0:
        date_str = "неизвестно"

    # Commit subject
    code, subject, _ = await _run_cmd("git", "log", "-1", "--format=%s")
    if code != 0:
        subject = "нет описания"

    # Branch
    code, branch, _ = await _run_cmd("git", "rev-parse", "--abbrev-ref", "HEAD")
    if code != 0:
        branch = "main"

    return {
        "commit": commit,
        "date": date_str,
        "subject": subject,
        "branch": branch
    }


async def check_for_updates() -> Dict[str, Any]:
    """Fetches origin/main and checks if there are new commits."""
    info = await get_current_version_info()
    current_commit = info["commit"]

    # 1. Fetch remote origin
    code, _, err = await _run_cmd("git", "fetch", "origin", "main", timeout=20.0)
    if code != 0:
        logger.error(f"git fetch failed: {err}")
        return {
            "has_updates": False,
            "current_commit": current_commit,
            "remote_commit": "",
            "commit_count": 0,
            "commits": [],
            "error": f"Ошибка связи с GitHub: {err or 'неизвестная ошибка'}"
        }

    # 2. Get remote commit
    code, remote_commit, _ = await _run_cmd("git", "rev-parse", "--short", "origin/main")
    if code != 0:
        remote_commit = ""

    # 3. Check diff log
    code, diff_log, _ = await _run_cmd("git", "log", "HEAD..origin/main", "--oneline")
    commits = [line.strip() for line in diff_log.splitlines() if line.strip()]

    has_updates = len(commits) > 0 or (remote_commit and remote_commit != current_commit)

    return {
        "has_updates": has_updates,
        "current_commit": current_commit,
        "remote_commit": remote_commit,
        "commit_count": len(commits),
        "commits": commits[:5],  # preview up to 5 commits
        "error": None
    }


async def apply_update() -> Tuple[bool, str]:
    """Pulls latest changes, installs dependencies if requirements changed, and sets update marker."""
    logger.info("Applying update from origin/main...")
    req_file = Path(__file__).parent / "requirements.txt"
    old_req = req_file.read_bytes() if req_file.exists() else b""

    # 1. Discard tracked local changes on server to prevent git pull merge conflicts
    await _run_cmd("git", "checkout", "--", ".")

    # 2. Pull from origin main
    code, stdout, stderr = await _run_cmd("git", "pull", "origin", "main", timeout=40.0)
    if code != 0:
        err_msg = stderr or stdout or "Неизвестная ошибка git pull"
        logger.error(f"Update failed on git pull: {err_msg}")
        return False, f"Ошибка git pull: {err_msg}"

    # 3. Check requirements.txt
    new_req = req_file.read_bytes() if req_file.exists() else b""
    if old_req != new_req:
        logger.info("requirements.txt changed, upgrading dependencies...")
        code, p_out, p_err = await _run_cmd(sys.executable, "-m", "pip", "install", "-r", "requirements.txt", timeout=120.0)
        if code != 0:
            logger.warning(f"pip install failed (non-fatal warning): {p_err or p_out}")

    # 4. Save marker file with target commit
    info = await get_current_version_info()
    new_commit = info["commit"]
    try:
        UPDATE_MARKER_FILE.write_text(new_commit, encoding="utf-8")
    except Exception as e:
        logger.warning(f"Could not write update marker file: {e}")

    logger.info(f"Update applied successfully to commit {new_commit}!")
    return True, new_commit


async def restart_service():
    """Triggers graceful restart under systemd or restarts current process."""
    logger.info("Restart service requested. Waiting 1.5s for network messages to flush...")
    await asyncio.sleep(1.5)

    if sys.platform != "win32":
        # 1. Try systemctl restart if running on Linux systemd
        try:
            p = await asyncio.create_subprocess_exec("systemctl", "restart", "ai-aggregator")
            await p.communicate()
            if p.returncode == 0:
                return
            logger.warning(f"systemctl restart failed with return code {p.returncode}, falling back to process restart")
        except Exception as e:
            logger.info(f"systemctl restart not available ({e}), using signal/re-exec restart fallback")

    # 2. Fallback: re-exec current python process
    try:
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as e:
        logger.warning(f"os.execv failed ({e}), falling back to SIGTERM/exit")
        if sys.platform != "win32":
            os.kill(os.getpid(), signal.SIGTERM)
        else:
            sys.exit(0)
        logger.warning(f"SIGTERM / execv failed: {e}. Exiting cleanly via sys.exit(0)...")
        os._exit(0)


def check_and_clear_update_flag() -> Optional[str]:
    """If marker file exists from recent update, returns the commit and deletes file."""
    if UPDATE_MARKER_FILE.exists():
        try:
            commit = UPDATE_MARKER_FILE.read_text(encoding="utf-8").strip()
            UPDATE_MARKER_FILE.unlink(missing_ok=True)
            return commit or "последней версии"
        except Exception as e:
            logger.warning(f"Failed to read/delete update marker: {e}")
    return None
