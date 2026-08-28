"""Minimal sandbox service — POST /exec runs bash -lc in /workspaces/{user_id}/{agent_id}.

Security posture (post-sweep):
- Shared-secret auth: every request must carry X-Sandbox-Token matching
  SANDBOX_SHARED_SECRET on BOTH sides (backend HttpSandbox sends it; compose
  wires the same value into both containers). With no secret configured the
  service refuses execs — fail closed, never open.
- No secrets in env by compose design (no env_file: .env).
- Container hardening (read_only, cap_drop ALL, no-new-privileges, mem/pids
  limits) lives in docker-compose.yml.
"""

import os
import pathlib
import subprocess

from fastapi import FastAPI, HTTPException, Request

app = FastAPI()

WORKSPACE_ROOT = pathlib.Path("/workspaces")


class ExecRequest(BaseModel):  # type: ignore[name-defined]
    cmd: str
    workdir: str = "."
    user_id: str
    agent_id: str


def _authorized(request: Request) -> bool:
    expected = os.environ.get("SANDBOX_SHARED_SECRET", "")
    if not expected:
        # Fail closed: with no secret configured there is no auth at all,
        # so the endpoint must refuse everything.
        return False
    provided = request.headers.get("X-Sandbox-Token", "")
    # hmac.compare_digest keeps the check timing-safe.
    import hmac

    return hmac.compare_digest(provided, expected)


@app.post("/exec")
async def exec_cmd(body: ExecRequest, request: Request):
    if not _authorized(request):
        raise HTTPException(status_code=401, detail="unauthorized")

    if not body.cmd or len(body.cmd) > 8000:
        raise HTTPException(status_code=422, detail="invalid cmd")
    # Resolve workspace
    wp = WORKSPACE_ROOT / body.user_id / body.agent_id
    wp.mkdir(parents=True, exist_ok=True)
    # Resolve workdir under workspace
    workdir = (wp / body.workdir).resolve() if body.workdir != "." else wp.resolve()
    try:
        workdir.relative_to(wp.resolve())
    except ValueError:
        raise HTTPException(status_code=422, detail="workdir escapes workspace")
    workdir.mkdir(parents=True, exist_ok=True)

    # Egress is NOT allowlisted by this app (the old comment claimed an
    # allowlist that never existed — sweep H2). Any enforcement would be
    # network-level (compose networks / firewall), not string matching on cmd.
    #
    # start_new_session=True puts bash in its own process group so a timeout
    # kills the WHOLE group (detached grandchildren like `sleep 1000 &` don't
    # survive the parent's death). os.killpg(-pid, SIGKILL) targets that group.
    # Without it, TimeoutExpired orphaned grandchildren and returned a 500.
    try:
        proc = subprocess.Popen(
            ["bash", "-lc", body.cmd],
            cwd=str(workdir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
    except OSError as exc:
        return {"stdout": "", "stderr": f"sandbox launch error: {exc}",
                "exit_code": 1, "truncated": False}
    try:
        stdout, stderr = proc.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        # bash is in its own session/group (start_new_session), so killing the
        # group by pid kills the parent AND any detached grandchildren.
        try:
            os.killpg(proc.pid, 9)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            stdout, stderr = proc.communicate(timeout=2)
        except (subprocess.TimeoutExpired, ValueError):
            stdout, stderr = "", ""
        return {"stdout": "", "stderr": "sandbox command timed out",
                "exit_code": 124, "truncated": False}
    stdout = (stdout or "")[:8000]
    stderr = (stderr or "")[:2000]
    return {"stdout": stdout, "stderr": stderr, "exit_code": proc.returncode,
            "truncated": len(stdout) > 8000}
