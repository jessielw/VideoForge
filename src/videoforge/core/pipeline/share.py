"""Finished files shared between the jobs of one source (dubbed, subbed, 720p).

Each job has its own folder in the source's work folder (workdir.job_dir); what comes from the source
alone sits at the top, shared. A step's fingerprint names its job's paths, so the same encode in two
jobs' folders never matches. Its portable fingerprint puts `<job>` in place of the job's folder and
takes an input from that folder by how it was made (the portable fingerprint it was noted with), or by
its bytes. Finished files are noted with it (workdir.note_finished), and a step with no record of its
own takes a file a job noted with the same portable fingerprint: a hard link into its own folder (a copy
where the file system has none), or the file itself when it's one of the shared ones. Before a run (the reuse
question), an input the job's folder doesn't have yet is told by the step that will make it (`makers`).
"""

from __future__ import annotations

from dataclasses import dataclass
import glob
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import TYPE_CHECKING

from videoforge.core.job import StepRecord
from videoforge.core.workdir import FINISHED_NAME, FinishedFile, finished_files, note_finished

if TYPE_CHECKING:
    from videoforge.core.pipeline.steps import Step

HASHED_MAX = 64 * 1024 * 1024  # a job-folder input not noted (nothing made it) is told by its bytes up to this size
JOB = "<job>"


@dataclass(frozen=True, slots=True)
class Found:
    """A finished file a step could take: where it is, and what its note says."""

    folder: Path  # the job folder (or the work folder, for a shared file) it's in
    notes: dict[str, FinishedFile]  # the step's outputs' notes there, by file name


@dataclass(frozen=True, slots=True)
class Sharing:
    work: Path  # the source's work folder
    home: Path  # this job's folder in it
    makers: tuple[Step, ...] = ()  # the job's steps, for inputs not made yet

    def _inside(self, path: Path) -> bool:
        return path.parent in (self.work, self.home)

    def _identity(self, path: Path) -> str | None:
        """A job-folder input as any job's folder would have it: how it was made (or will be), else its bytes."""
        note = finished_files(self.home).get(path.name)
        if note is not None and note.portable:
            return "made " + note.portable
        maker = next((s for s in self.makers if path in s.outputs), None)
        if maker is not None and not path.exists():
            portable = self.portable(maker)
            return None if portable is None else "made " + portable
        try:
            if path.stat().st_size > HASHED_MAX:
                return None
            return "bytes " + hashlib.sha1(path.read_bytes(), usedforsecurity=False).hexdigest()
        except OSError:
            return "missing"

    def portable(self, step: Step) -> str | None:
        """The step's fingerprint, the same in any job's folder; None when an input can't be told apart."""
        home = str(self.home)

        def swap(text: str) -> str:
            return text.replace(home, JOB)

        inputs: list[list[object]] = []
        for path in step.inputs:
            if path.parent == self.home:
                identity = self._identity(path)
                if identity is None:
                    return None
                inputs.append([f"{JOB}/{path.name}", identity])
            else:
                try:
                    st = path.stat()
                    inputs.append([str(path), st.st_size, st.st_mtime_ns])
                except OSError:
                    inputs.append([str(path), None, None])
        argvs = [[swap(str(a)) for a in argv] for argv in step.argvs]
        outputs = [swap(str(p)) for p in step.outputs]
        doc = json.dumps([step.id, argvs, swap(step.key), inputs, outputs], default=str)
        return hashlib.sha1(doc.encode("utf-8"), usedforsecurity=False).hexdigest()

    def note(self, step: Step, record: StepRecord) -> None:
        """A finished step's files, noted in their folders with its portable fingerprint. Never raises."""
        try:
            portable = self.portable(step) or ""
        except OSError:
            portable = ""
        for folder in dict.fromkeys(p.parent for p in record.outputs if self._inside(p)):
            note_finished(folder, record.id, record.fingerprint, record.outputs, record.seconds, portable)

    def find(self, step: Step) -> Found | None:
        """A job's finished files for the step, made as this job would make them: this job's own folder
        first, then the other jobs'. Its outputs must all be in the work folder (the mux's aren't)."""
        outputs = list(step.outputs)
        if not outputs or not all(self._inside(p) for p in outputs):
            return None
        portable = self.portable(step)
        if portable is None:
            return None

        def matches(note: FinishedFile | None) -> bool:
            return note is not None and note.step == step.id and note.portable == portable

        shared = finished_files(self.work)
        if not all(matches(shared.get(p.name)) for p in outputs if p.parent == self.work):
            return None
        own = [p for p in outputs if p.parent == self.home]
        if not own:
            return Found(self.work, {p.name: shared[p.name] for p in outputs})
        for folder in self._job_folders():
            notes = finished_files(folder)
            if all(matches(notes.get(p.name)) for p in own):
                return Found(folder, {p.name: (notes if p.parent == self.home else shared)[p.name] for p in outputs})
        return None

    def _job_folders(self) -> list[Path]:
        try:
            others = sorted(d for d in self.work.iterdir() if d.is_dir() and d != self.home)
        except OSError:
            others = []
        return [self.home, *others]

    def adopt(self, step: Step) -> tuple[StepRecord, str] | None:
        """Take another job's finished files for the step (find): linked into this job's folder, with a record.
        Returns the record and the job folder they came from ("" for this job's own, or a shared file)."""
        found = self.find(step)
        if found is None:
            return None
        if found.folder != self.home and found.folder != self.work:
            self.home.mkdir(parents=True, exist_ok=True)
            for path in step.outputs:
                if path.parent == self.home:
                    _link(found.folder / path.name, path)
        seconds = max((n.seconds for n in found.notes.values()), default=0.0)
        record = StepRecord(step.id, step.fingerprint(), list(step.outputs), seconds)
        record.capture_outputs()
        self.note(step, record)
        origin = found.folder.name if found.folder not in (self.home, self.work) else ""
        return record, origin


def _link(source: Path, target: Path) -> None:
    """target: the same file as source (a hard link, else a copy), with the files a tool writes beside it
    (x265's `<stats>.cutree`, which its pass 2 reads)."""
    pairs = [(source, target)] + [
        (Path(c), target.with_name(Path(c).name.replace(source.name, target.name, 1)))
        for c in glob.glob(glob.escape(str(source)) + ".*")
        if Path(c).name != FINISHED_NAME
    ]
    for src, dst in pairs:
        dst.unlink(missing_ok=True)
        try:
            os.link(src, dst)
        except OSError:
            shutil.copy2(src, dst)
