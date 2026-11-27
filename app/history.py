import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.transcriber import TranscriptSegment


@dataclass
class HistoryEntry:
    id: str
    created_at: str
    file_name: str
    audio_path: str
    segments: list[TranscriptSegment]

    @property
    def full_text(self) -> str:
        return " ".join(seg.text for seg in self.segments)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "file_name": self.file_name,
            "audio_path": self.audio_path,
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
        return cls(
            id=str(data["id"]),
            created_at=str(data["created_at"]),
            file_name=str(data["file_name"]),
            audio_path=str(data["audio_path"]),
            segments=segments,
        )


class HistoryManager:

    def __init__(self, storage_path: str | Path = "data/history.json") -> None:
        self.storage_path = Path(storage_path).expanduser().resolve()

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
    ) -> HistoryEntry:
        path = Path(audio_path).expanduser().resolve()
        entry = HistoryEntry(
            id=str(uuid.uuid4()),
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            file_name=path.name,
            audio_path=str(path),
            segments=segments,
        )
        entries = self.load()
        entries.insert(0, entry)  # newest first
        self._save(entries)
        return entry

    def delete(self, entry_id: str) -> bool:
        entries = self.load()
        updated = [e for e in entries if e.id != entry_id]
        if len(updated) == len(entries):
            return False
        self._save(updated)
        return True