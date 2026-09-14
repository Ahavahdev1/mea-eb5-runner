"""Transactional file writer with staging and rollback."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


class Transaction:
    """Write a target file atomically with crash recovery.

    The obvious direct-write solution fails the crash tests because it leaves
    partial state on disk.  A correct implementation uses a staging directory,
    a write-ahead journal, and atomic ``os.replace``.
    """

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.stage = self.root / ".stage"
        self.journal = self.root / ".journal"
        self.target = self.root / "data.txt"
        self._recover()

    def _recover(self) -> None:
        """On startup, complete or roll back any incomplete transaction."""
        if self.journal.exists():
            # BUG: validated-but-uncommitted data is incorrectly promoted after
            # a crash. The required behavior is to commit only a "commit" journal.
            staged = self.stage / "data.txt"
            if staged.exists():
                os.replace(staged, self.target)
            shutil.rmtree(self.stage, ignore_errors=True)
            self.journal.unlink(missing_ok=True)

    def prepare(self, content: str) -> None:
        shutil.rmtree(self.stage, ignore_errors=True)
        self.stage.mkdir(parents=True, exist_ok=True)
        (self.stage / "data.txt").write_text(content, encoding="utf-8")
        self.journal.write_text("prepare", encoding="utf-8")

    def validate(self) -> bool:
        staged = self.stage / "data.txt"
        if not staged.exists():
            return False
        self.journal.write_text("validate", encoding="utf-8")
        return True

    def commit(self) -> None:
        staged = self.stage / "data.txt"
        if not staged.exists():
            raise RuntimeError("nothing to commit")
        self.journal.write_text("commit", encoding="utf-8")
        os.replace(staged, self.target)
        self.journal.unlink(missing_ok=True)
        shutil.rmtree(self.stage, ignore_errors=True)

    def rollback(self) -> None:
        self.journal.write_text("rollback", encoding="utf-8")
        shutil.rmtree(self.stage, ignore_errors=True)
        self.journal.unlink(missing_ok=True)


def direct_write(content: str, root: Path | str) -> None:
    """Obvious non-transactional baseline that fails crash tests."""
    Path(root).mkdir(parents=True, exist_ok=True)
    Path(root, "data.txt").write_text(content, encoding="utf-8")
