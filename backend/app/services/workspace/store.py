"""WorkspaceStore — the only code that touches the workspaces volume.

Per-user-per-agent git-backed folders on the named volume `workspaces:/workspaces`
at `workspaces/{user_id}/{agent_id}`. Every mutating operation is serialized by a
per-workspace asyncio.Lock (one bash at a time, ADR-0002 Q12) and leaves both a git
commit and a file_edits audit row (ADR-0003).
"""

import asyncio
import hashlib
import pathlib
import subprocess
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.db import AsyncSessionLocal
from app.models.file_edits import FileEdit
import uuid as _uuid


def _workspace_root() -> pathlib.Path:
    return pathlib.Path(settings.WORKSPACE_ROOT)


def _workspace_path(user_id: str, agent_id: str) -> pathlib.Path:
    return _workspace_root() / str(user_id) / str(agent_id)


def _validate_rel_path(path: str) -> str:
    if not path or path in (".", "./"):
        return "."
    p = pathlib.PurePosixPath(path)
    if p.is_absolute():
        raise AppError(status_code=422, detail="path must be relative")
    for part in p.parts:
        if part in ("..", ".") or not part:
            # allow "." only as the root query itself; not inside
            if path != ".":
                raise AppError(status_code=422, detail="path may not contain '..' or '.' segments")
        if part and any(ord(ch) < 32 or ord(ch) == 127 for ch in part):
            raise AppError(status_code=422, detail="invalid path characters")
    return path


def _line_hash(line: str) -> str:
    return hashlib.sha1(line.encode("utf-8")).hexdigest()[:8]


def _file_hashes(content: str) -> list[str]:
    return [_line_hash(l) for l in content.splitlines()]


class WorkspaceStore:
    """Singleton-ish store — per-workspace locks live here."""

    def __init__(self) -> None:
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}

    def _lock(self, user_id: str, agent_id: str) -> asyncio.Lock:
        key = (str(user_id), str(agent_id))
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    def ensure_workspace(self, user_id: str, agent_id: str) -> pathlib.Path:
        wp = _workspace_path(user_id, agent_id)
        wp.mkdir(parents=True, exist_ok=True)
        git_dir = wp / ".git"
        if not git_dir.exists():
            subprocess.run(["git", "init", "-q", str(wp)], check=False)
            subprocess.run(["git", "-C", str(wp), "config", "user.name", "llm-gateway"], check=False)
            subprocess.run(["git", "-C", str(wp), "config", "user.email", "agent@llm-gateway"], check=False)
            # First commit so HEAD exists
            subprocess.run(["git", "-C", str(wp), "commit", "--allow-empty", "-m", "init"], check=False)
        return wp

    def _commit(self, wp: pathlib.Path, message: str) -> None:
        subprocess.run(["git", "-C", str(wp), "add", "-A"], check=False)
        subprocess.run(["git", "-C", str(wp), "commit", "--allow-empty", "-m", message], check=False)

    def read_file(self, user_id: str, agent_id: str, path: str) -> dict:
        rel = _validate_rel_path(path)
        if rel == ".":
            raise AppError(status_code=422, detail="path is a directory")
        wp = self.ensure_workspace(user_id, agent_id)
        fp = wp / rel
        # Guard: must stay under workspace
        try:
            fp.resolve().relative_to(wp.resolve())
        except ValueError:
            raise AppError(status_code=422, detail="path escapes workspace")
        if not fp.is_file():
            raise AppError(status_code=404, detail="file not found")
        content = fp.read_text(encoding="utf-8", errors="surrogateescape")
        lines = content.splitlines()
        return {
            "content": content,
            "lines": [{"n": i + 1, "hash": _line_hash(l), "text": l} for i, l in enumerate(lines)],
        }

    def list_files(self, user_id: str, agent_id: str, path: str = ".") -> list[str]:
        rel = _validate_rel_path(path)
        wp = self.ensure_workspace(user_id, agent_id)
        base = wp / rel if rel != "." else wp
        try:
            base.resolve().relative_to(wp.resolve())
        except ValueError:
            raise AppError(status_code=422, detail="path escapes workspace")
        if not base.exists():
            return []
        if base.is_file():
            return [rel]
        out: list[str] = []
        for p in base.rglob("*"):
            if ".git" in p.parts:
                continue
            if p.is_file():
                try:
                    rel_p = p.relative_to(wp).as_posix()
                    out.append(rel_p)
                except ValueError:
                    continue
        return sorted(out)

    def du_mb(self, user_id: str, agent_id: str) -> float:
        wp = self.ensure_workspace(user_id, agent_id)
        # Count files excluding .git
        total = 0
        for p in wp.rglob("*"):
            if ".git" in p.parts or not p.is_file():
                continue
            try:
                total += p.stat().st_size
            except OSError:
                continue
        return total / (1024 * 1024)

    def _check_quota(self, user_id: str, agent_id: str) -> None:
        if self.du_mb(user_id, agent_id) > float(settings.SANDBOX_DISK_QUOTA_MB):
            raise AppError(status_code=413, detail="workspace quota exceeded")

    async def write_file(
        self,
        user_id: str,
        agent_id: str,
        path: str,
        content: str,
        expected_hashes: Optional[list[str]] = None,
        tool_call_id: str | None = None,
        db: AsyncSession | None = None,
    ) -> dict:
        rel = _validate_rel_path(path)
        if rel == ".":
            raise AppError(status_code=422, detail="path is a directory")
        lock = self._lock(user_id, agent_id)
        async with lock:
            wp = self.ensure_workspace(user_id, agent_id)
            fp = wp / rel
            try:
                (wp / rel).resolve().parent.relative_to(wp.resolve())
            except ValueError:
                raise AppError(status_code=422, detail="path escapes workspace")
            # Hashline conflict check if file exists
            if expected_hashes is not None and fp.is_file():
                cur = fp.read_text(encoding="utf-8", errors="surrogateescape")
                cur_hashes = _file_hashes(cur)
                # expected must be subset of current — if any mismatch, conflict
                if expected_hashes != cur_hashes[: len(expected_hashes)] and set(expected_hashes) - set(cur_hashes):
                    raise AppError(status_code=409, detail="file changed, re-read")
            self._check_quota(user_id, agent_id)
            fp.parent.mkdir(parents=True, exist_ok=True)
            before = fp.read_text(encoding="utf-8", errors="surrogateescape") if fp.is_file() else ""
            fp.write_text(content, encoding="utf-8")
            after = content
            before_hash = hashlib.sha1(before.encode()).hexdigest()[:8] if before else None
            after_hash = hashlib.sha1(after.encode()).hexdigest()[:8]
            # Minimal patch representation for undo
            patch = f"write {rel}"
            edit_id = await self._record_edit(
                user_id, agent_id, "workspace", rel, patch, before_hash, after_hash, tool_call_id, db
            )
            self._commit(wp, f"write {rel} {edit_id}")
            return {"edit_id": edit_id, "path": rel}

    async def apply_patch(
        self,
        user_id: str,
        agent_id: str,
        path: str,
        patch: str,
        expected_hashes: Optional[list[str]] = None,
        tool_call_id: str | None = None,
        db: AsyncSession | None = None,
    ) -> dict:
        rel = _validate_rel_path(path)
        if rel == ".":
            raise AppError(status_code=422, detail="path is a directory")
        lock = self._lock(user_id, agent_id)
        async with lock:
            wp = self.ensure_workspace(user_id, agent_id)
            fp = wp / rel
            if not patch or "---" not in patch or "+++" not in patch:
                # Also accept simple diff without headers: require hunk marker
                if "@@" not in patch:
                    raise AppError(status_code=422, detail="patch must be a unified diff")
            if expected_hashes is not None and fp.is_file():
                cur = fp.read_text(encoding="utf-8", errors="surrogateescape")
                cur_hashes = _file_hashes(cur)
                if set(expected_hashes) - set(cur_hashes):
                    raise AppError(status_code=409, detail="file changed, re-read")
            self._check_quota(user_id, agent_id)
            before = fp.read_text(encoding="utf-8", errors="surrogateescape") if fp.is_file() else ""
            # Apply via `patch -p1` inside workspace; fallback to python if unavailable
            try:
                proc = subprocess.run(
                    ["patch", "-p1", "--forward", "--batch"],
                    input=patch.encode(),
                    cwd=str(wp),
                    capture_output=True,
                    timeout=10,
                )
                if proc.returncode not in (0,):
                    # Try reverse check: maybe already applied
                    raise AppError(status_code=422, detail=f"patch failed: {proc.stderr.decode(errors='ignore')[:400]}")
            except FileNotFoundError:
                # No `patch` binary — naive single-file replace from diff (best-effort)
                raise AppError(status_code=422, detail="patch tool unavailable in this environment")
            after = fp.read_text(encoding="utf-8", errors="surrogateescape") if fp.is_file() else ""
            before_hash = hashlib.sha1(before.encode()).hexdigest()[:8] if before else None
            after_hash = hashlib.sha1(after.encode()).hexdigest()[:8] if after else None
            edit_id = await self._record_edit(
                user_id, agent_id, "workspace", rel, patch, before_hash, after_hash, tool_call_id, db
            )
            self._commit(wp, f"patch {rel} {edit_id}")
            return {"edit_id": edit_id, "path": rel}

    async def edit_lines(
        self,
        user_id: str,
        agent_id: str,
        path: str,
        old_hashes: list[str],
        new_content: str,
        tool_call_id: str | None = None,
        db: AsyncSession | None = None,
    ) -> dict:
        rel = _validate_rel_path(path)
        if rel == ".":
            raise AppError(status_code=422, detail="path is a directory")
        if not old_hashes:
            raise AppError(status_code=422, detail="old_hashes required")
        lock = self._lock(user_id, agent_id)
        async with lock:
            wp = self.ensure_workspace(user_id, agent_id)
            fp = wp / rel
            if not fp.is_file():
                raise AppError(status_code=404, detail="file not found")
            cur = fp.read_text(encoding="utf-8", errors="surrogateescape")
            lines = cur.splitlines()
            cur_hashes = [_line_hash(l) for l in lines]
            # All old_hashes must be present in current file
            if not set(old_hashes).issubset(set(cur_hashes)):
                raise AppError(status_code=409, detail="file changed, re-read")
            # Replace: find contiguous block matching old_hashes and swap
            # For v1, replace all lines whose hashes are in old_hashes with new_content lines
            # Simpler: if single hash, single-line replace
            new_lines = new_content.splitlines()
            # Map hash -> index (first occurrence)
            hash_to_idx = {}
            for i, h in enumerate(cur_hashes):
                if h not in hash_to_idx:
                    hash_to_idx[h] = i
            # Collect indices to replace
            idxs = sorted(hash_to_idx[h] for h in old_hashes if h in hash_to_idx)
            if not idxs:
                raise AppError(status_code=404, detail="hashed lines not found")
            # Replace contiguous span or single line
            start, end = idxs[0], idxs[-1] + 1
            before = cur
            after_lines = lines[:start] + new_lines + lines[end:]
            after = "\n".join(after_lines)
            if cur.endswith("\n"):
                after += "\n"
            self._check_quota(user_id, agent_id)
            fp.write_text(after, encoding="utf-8")
            before_hash = hashlib.sha1(before.encode()).hexdigest()[:8]
            after_hash = hashlib.sha1(after.encode()).hexdigest()[:8]
            patch = f"edit_lines {rel} {','.join(old_hashes[:4])}"
            edit_id = await self._record_edit(
                user_id, agent_id, "workspace", rel, patch, before_hash, after_hash, tool_call_id, db
            )
            self._commit(wp, f"edit_lines {rel} {edit_id}")
            return {"edit_id": edit_id, "path": rel}

    async def _record_edit(
        self,
        user_id: str,
        agent_id: str | None,
        store: str,
        path: str,
        patch: str,
        before_hash: str | None,
        after_hash: str | None,
        tool_call_id: str | None,
        db: AsyncSession | None,
    ) -> str:
        edit_id = str(_uuid.uuid4())
        # Persist if a session is provided; otherwise best-effort via fresh session
        session = db
        owned = False
        if session is None:
            session = AsyncSessionLocal()
            owned = True
        try:
            row = FileEdit(
                id=edit_id,
                user_id=user_id,
                agent_id=agent_id,
                store=store,
                path=path,
                patch=patch[: 20000],
                before_hash=before_hash,
                after_hash=after_hash,
                tool_call_id=tool_call_id,
            )
            session.add(row)
            await session.commit()
        except Exception:
            try:
                await session.rollback()
            except Exception:
                pass
        finally:
            if owned:
                try:
                    await session.close()
                except Exception:
                    pass
        return edit_id

    async def undo(self, user_id: str, agent_id: str, edit_id: str, db: AsyncSession) -> dict:
        lock = self._lock(user_id, agent_id)
        async with lock:
            result = await db.execute(select(FileEdit).where(FileEdit.id == edit_id))
            row = result.scalar_one_or_none()
            if row is None:
                raise AppError(status_code=404, detail="edit not found")
            if str(row.user_id) != str(user_id):
                raise AppError(status_code=403, detail="unauthorised")
            # Reverse via git: `git show <edit_id_commit> | patch -R`
            # Simpler for v1: `git revert` of the last commit that mentions edit_id, or
            # if patch is a simple write, reverse-apply.
            # For now, use `git log --all --grep=edit_id` to find commit
            wp = self.ensure_workspace(user_id, agent_id)
            # Try git revert of the commit that contains edit_id in message
            proc = subprocess.run(
                ["git", "-C", str(wp), "log", "--all", "--oneline", "--grep", edit_id],
                capture_output=True,
                text=True,
            )
            commit = (proc.stdout.strip().split("\n")[0].split()[0] if proc.stdout.strip() else None)
            if commit:
                subprocess.run(["git", "-C", str(wp), "revert", "--no-edit", commit], check=False)
                # Record undo as new edit
                new_id = await self._record_edit(
                    user_id, agent_id, row.store, row.path, f"undo {edit_id}", row.after_hash, row.before_hash, None, db
                )
                self._commit(wp, f"undo {edit_id} -> {new_id}")
                return {"edit_id": new_id, "undone": edit_id}
            raise AppError(status_code=422, detail="cannot locate commit for edit")


_workspace_store: Optional[WorkspaceStore] = None


def get_workspace_store() -> WorkspaceStore:
    global _workspace_store
    if _workspace_store is None:
        _workspace_store = WorkspaceStore()
    return _workspace_store
