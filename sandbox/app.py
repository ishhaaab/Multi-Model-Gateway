"""Minimal sandbox service — POST /exec runs bash -lc in /workspaces/{user_id}/{agent_id}."""

import pathlib
import subprocess

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

WORKSPACE_ROOT = pathlib.Path("/workspaces")


class ExecRequest(BaseModel):
    cmd: str
    workdir: str = "."
    user_id: str
    agent_id: str


@app.post("/exec")
async def exec_cmd(body: ExecRequest):
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
    # Simple allowlist check on egress: if cmd contains curl/wget to non-allowlisted host,
    # the sandbox app itself doesn't enforce network — egress is controlled by compose network
    # isolation. Keep the check minimal here.
    proc = subprocess.run(
        ["bash", "-lc", body.cmd],
        cwd=str(workdir),
        capture_output=True,
        text=True,
        timeout=30,
    )
    # Truncate outputs
    stdout = proc.stdout[:8000]
    stderr = proc.stderr[:2000]
    return {"stdout": stdout, "stderr": stderr, "exit_code": proc.returncode, "truncated": len(proc.stdout) > 8000}
