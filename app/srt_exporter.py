from pathlib import Path
from app.transcriber import TranscriptSegment


def format_timestamp(seconds: float) -> str:
    """Saniyeyi SRT zaman damgası formatına (HH:MM:SS,mmm) çevirir."""
    total_ms = max(0, round(seconds * 1000))
    total_seconds, millis = divmod(total_ms, 1000)
    minutes, secs = divmod(total_seconds, 60)
    hours, mins = divmod(minutes, 60)
    return f"{hours:02d}:{mins:02d}:{secs:02d},{millis:03d}"


def segments_to_srt(segments: list[TranscriptSegment]) -> str:
    """Segment listesini standart SubRip (.srt) metnine dönüştürür."""
    blocks: list[str] = []
    for index, seg in enumerate(segments, start=1):
        start_ts = format_timestamp(seg.start)
        end_ts = format_timestamp(seg.end)
        text = seg.text.strip()
        if not text:
            continue
        blocks.append(f"{index}\n{start_ts} --> {end_ts}\n{text}")
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def export_srt(segments: list[TranscriptSegment], output_path: str | Path) -> Path:
    """SRT içeriğini UTF-8 kodlamasıyla diske güvenli şekilde kaydeder."""
    path = Path(output_path).expanduser().resolve()
    if path.suffix.lower() != ".srt":
        path = path.with_suffix(".srt")
    path.parent.mkdir(parents=True, exist_ok=True)
    content = segments_to_srt(segments)
    path.write_text(content, encoding="utf-8")
    return path