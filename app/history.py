import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.transcriber import TranscriptSegment


@dataclass
class HistoryEntry:
    id: str
    title: str
    created_at: str
    file_name: str
    audio_path: str
    segments: list[TranscriptSegment]
    duration: float = 0.0
    processing_time: float = 0.0

    @property
    def full_text(self) -> str:
        return " ".join(seg.text for seg in self.segments)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at,
            "file_name": self.file_name,
            "audio_path": self.audio_path,
            "duration": self.duration,
            "processing_time": self.processing_time,
            "segments": [
                {"start": s.start, "end": s.end, "text": s.text}
                for s in self.segments
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HistoryEntry":
        segments = [
            TranscriptSegment(
                start=float(s["start"]),
                end=float(s["end"]),
                text=str(s["text"]),
            )
            for s in data.get("segments", [])
        ]
        file_name = str(data.get("file_name", ""))
        title = str(data.get("title") or Path(file_name).stem or "Untitled")
        return cls(
            id=str(data["id"]),
            title=title,
            created_at=str(data.get("created_at", "")),
            file_name=file_name,
            audio_path=str(data.get("audio_path", "")),
            segments=segments,
            duration=float(data.get("duration", 0.0)),
            processing_time=float(data.get("processing_time", 0.0)),
        )


class HistoryManager:
    def __init__(self, storage_path: str | Path = "data/history.json") -> None:
        self.storage_path = Path(storage_path).expanduser().resolve()
        self.uploads_dir = self.storage_path.parent / "uploads"

    def load(self) -> list[HistoryEntry]:
        if not self.storage_path.exists():
            return []
        try:
            raw = json.loads(self.storage_path.read_text(encoding="utf-8"))
            return [HistoryEntry.from_dict(item) for item in raw]
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return []

    def _save(self, entries: list[HistoryEntry]) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            [entry.to_dict() for entry in entries],
            ensure_ascii=False,
            indent=2,
        )
        tmp_path = self.storage_path.with_suffix(".tmp")
        tmp_path.write_text(payload, encoding="utf-8")
        tmp_path.replace(self.storage_path)

    def add(
        self,
        audio_path: str | Path,
        segments: list[TranscriptSegment],
        *,
        title: str | None = None,
        file_name: str | None = None,
        duration: float = 0.0,
        processing_time: float = 0.0,
        entry_id: str | None = None,
    ) -> HistoryEntry:
        path = Path(audio_path).expanduser().resolve()
        resolved_name = file_name or path.name
        entry = HistoryEntry(
            id=entry_id or uuid.uuid4().hex[:12],
            title=title or Path(resolved_name).stem,
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            file_name=resolved_name,
            audio_path=str(path),
            segments=segments,
            duration=round(duration, 2),
            processing_time=round(processing_time, 2),
        )
        entries = self.load()
        entries.insert(0, entry)  # newest first
        self._save(entries)
        return entry

    def update(self, updated_entry: HistoryEntry) -> bool:
        entries = self.load()
        for idx, entry in enumerate(entries):
            if entry.id == updated_entry.id:
                entries[idx] = updated_entry
                self._save(entries)
                return True
        return False

    def delete(self, entry_id: str) -> bool:
        entries = self.load()
        target = next((e for e in entries if e.id == entry_id), None)
        if not target:
            return False
        updated = [e for e in entries if e.id != entry_id]
        self._save(updated)

        audio_path = Path(target.audio_path)
        try:
            if audio_path.is_file() and audio_path.resolve().parent == self.uploads_dir.resolve():
                audio_path.unlink(missing_ok=True)
        except OSError:
            pass
        return True
