"""Artifact integrity helpers for reproducible benchmark evidence."""

from __future__ import annotations

import difflib
import hashlib
import os
import re
from pathlib import Path
from typing import Mapping

from .models import Manifest, RunConfig, RunStatus


_DIGEST_RE = re.compile(r"^sha256:[a-f0-9]{64}$")


def hash_tree(root: Path) -> dict[str, str]:
    """Return a deterministic, sorted map of relative path to sha256 digest.

    Hashes include the relative path, the file mode, and the raw file bytes.
    Directories named ``.git`` and ``runs`` are excluded.  Symlinks that
    resolve outside of ``root`` raise ``ValueError``.
    """
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError(f"hash_tree root must be a directory: {root}")

    hashes: dict[str, str] = {}

    for dirpath, dirnames, filenames in os.walk(root):
        # Exclude .git and runs directories from traversal.
        dirnames[:] = [name for name in dirnames if name not in {".git", "runs"}]

        rel_dir = Path(dirpath).relative_to(root)
        for filename in filenames:
            file_path = Path(dirpath) / filename
            rel_path = (rel_dir / filename).as_posix()

            if file_path.is_symlink():
                resolved = file_path.resolve()
                try:
                    resolved.relative_to(root)
                except ValueError as exc:
                    raise ValueError(
                        f"symlink escapes workspace: {rel_path}"
                    ) from exc
                if not resolved.is_file():
                    # Internal symlink that does not point to a regular file is
                    # skipped to avoid directory cycles.
                    continue
                # Hash the target bytes through the symlink path.
                file_path = resolved
            elif not file_path.is_file():
                continue

            st = file_path.stat()
            data = file_path.read_bytes()
            digest_input = f"{rel_path}\0{st.st_mode}\0".encode() + data
            hashes[rel_path] = hashlib.sha256(digest_input).hexdigest()

    return dict(sorted(hashes.items()))


def write_patch(
    before: dict[str, str],
    after: dict[str, str],
    destination: Path,
    *,
    before_root: Path | None = None,
    after_root: Path | None = None,
) -> None:
    """Write a patch describing the transition from ``before`` to ``after``.

    UTF-8 text files are rendered as a unified diff.  Binary files are
    recorded only by their hash transition.  When ``before_root`` or
    ``after_root`` are omitted, ``destination.parent`` is used as the
    workspace root to read file contents.
    """
    destination = Path(destination)
    before_root = Path(before_root) if before_root else destination.parent
    after_root = Path(after_root) if after_root else destination.parent

    before_set = set(before)
    after_set = set(after)
    added = sorted(after_set - before_set)
    deleted = sorted(before_set - after_set)
    common = sorted(before_set & after_set)

    lines: list[str] = ["--- before", "+++ after", ""]

    for rel_path in added:
        after_path = after_root / rel_path
        if _is_text_file(after_path):
            new_lines = after_path.read_text(encoding="utf-8").splitlines()
            lines.extend(
                difflib.unified_diff(
                    [],
                    new_lines,
                    fromfile=f"a/{rel_path}",
                    tofile=f"b/{rel_path}",
                    lineterm="",
                )
            )
        else:
            lines.append(f"Binary file {rel_path} added: {after[rel_path]}")
        lines.append("")

    for rel_path in deleted:
        before_path = before_root / rel_path
        if _is_text_file(before_path):
            old_lines = before_path.read_text(encoding="utf-8").splitlines()
            lines.extend(
                difflib.unified_diff(
                    old_lines,
                    [],
                    fromfile=f"a/{rel_path}",
                    tofile=f"b/{rel_path}",
                    lineterm="",
                )
            )
        else:
            lines.append(f"Binary file {rel_path} deleted: {before[rel_path]}")
        lines.append("")

    for rel_path in common:
        if before[rel_path] == after[rel_path]:
            continue
        before_path = before_root / rel_path
        after_path = after_root / rel_path
        if _is_text_file(before_path) and _is_text_file(after_path):
            if before_path.read_bytes() == after_path.read_bytes():
                # A freeze may tighten permissions without changing the agent's
                # submitted content; that is integrity metadata, not a code diff.
                continue
            old_lines = before_path.read_text(encoding="utf-8").splitlines()
            new_lines = after_path.read_text(encoding="utf-8").splitlines()
            diff_lines = list(
                difflib.unified_diff(
                    old_lines,
                    new_lines,
                    fromfile=f"a/{rel_path}",
                    tofile=f"b/{rel_path}",
                    lineterm="",
                )
            )
            if diff_lines:
                lines.extend(diff_lines)
            else:
                lines.append(
                    f"File {rel_path} changed: "
                    f"{before[rel_path]} -> {after[rel_path]}"
                )
        else:
            lines.append(
                f"Binary file {rel_path} changed: "
                f"{before[rel_path]} -> {after[rel_path]}"
            )
        lines.append("")

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def build_manifest(
    *,
    run_id: str,
    status: RunStatus,
    started_at: str,
    finished_at: str,
    seed: int,
    config: RunConfig,
    artifact_hashes: Mapping[str, str],
    git_commit: str,
    image_digest: str,
    adapter_version: str,
    versions: Mapping[str, str] | None = None,
    network_allowed: bool = False,
    schema_version: str = "1.0",
) -> Manifest:
    """Assemble an immutable manifest for one benchmark attempt."""
    if not _DIGEST_RE.fullmatch(image_digest):
        raise ValueError("image_digest must be sha256:<64 hex chars>")

    return Manifest(
        schema_version=schema_version,
        run_id=run_id,
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        seed=seed,
        config=config,
        artifact_hashes=dict(artifact_hashes),
        git_commit=git_commit,
        images={"benchmark": image_digest},
        adapter_version=adapter_version,
        versions=dict(versions) if versions is not None else {},
        network_allowed=network_allowed,
    )


def _is_text_file(path: Path) -> bool:
    """Return True if *path* can be read as UTF-8 text without NUL bytes."""
    try:
        data = path.read_bytes()
    except OSError:
        return False
    if b"\x00" in data:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


__all__ = ["hash_tree", "write_patch", "build_manifest"]
