from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.history import HistoryEntry, HistoryManager
from app.srt_exporter import export_srt
from app.theme import enable_windows_dark_titlebar
from app.transcriber import ALLOWED_EXTENSIONS, Transcriber, TranscriptSegment
from app.worker import TranscribeWorker

LOGO_PATH = Path(__file__).resolve().parent / "assets" / "logo.svg"


def fmt_time(sec: float) -> str:
    total = max(0, int(sec or 0))
    hours = total // 3600
    minutes = (total % 3600) // 60
    seconds = total % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


class EditSegmentDialog(QDialog):
    def __init__(self, seg: TranscriptSegment, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Edit Segment ({fmt_time(seg.start)})")
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        self.text_edit = QTextEdit()
        self.text_edit.setPlainText(seg.text)
        self.text_edit.setFixedHeight(90)
        layout.addWidget(self.text_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_text(self) -> str:
        return self.text_edit.toPlainText().strip()


class SegmentRow(QFrame):
    seek_requested = Signal(float)
    edit_requested = Signal(int)

    def __init__(self, seg_idx: int, seg: TranscriptSegment) -> None:
        super().__init__()
        self.seg_idx = seg_idx
        self.start_sec = seg.start
        self.end_sec = seg.end
        self.setObjectName("segmentRow")
        self.setProperty("active", False)

        row = QHBoxLayout(self)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(14)

        self.ts_btn = QPushButton(fmt_time(self.start_sec))
        self.ts_btn.setObjectName("timestampBtn")
        self.ts_btn.setFixedWidth(74)
        self.ts_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ts_btn.clicked.connect(lambda: self.seek_requested.emit(self.start_sec))
        row.addWidget(self.ts_btn, 0, Qt.AlignmentFlag.AlignTop)

        self.text_label = QLabel(seg.text)
        self.text_label.setObjectName("segPrimary")
        self.text_label.setWordWrap(True)
        self.text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(self.text_label, 1)

    def set_text(self, text: str) -> None:
        self.text_label.setText(text)

    def set_active(self, active: bool) -> None:
        if self.property("active") != active:
            self.setProperty("active", active)
            self.style().unpolish(self)
            self.style().polish(self)

    def mouseDoubleClickEvent(self, event) -> None:
        self.edit_requested.emit(self.seg_idx)
        super().mouseDoubleClickEvent(event)


class DropCard(QFrame):
    file_dropped = Signal(Path)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("dropCard")
        self.setAcceptDrops(True)
        self.setProperty("dragging", False)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                p = Path(url.toLocalFile())
                if p.is_file() and p.suffix.lower() in ALLOWED_EXTENSIONS:
                    event.acceptProposedAction()
                    self._set_dragging(True)
                    return
        event.ignore()

    def dragLeaveEvent(self, event) -> None:
        self._set_dragging(False)

    def dropEvent(self, event: QDropEvent) -> None:
        self._set_dragging(False)
        for url in event.mimeData().urls():
            p = Path(url.toLocalFile())
            if p.is_file() and p.suffix.lower() in ALLOWED_EXTENSIONS:
                self.file_dropped.emit(p)
                event.acceptProposedAction()
                return

    def _set_dragging(self, state: bool) -> None:
        self.setProperty("dragging", state)
        self.style().unpolish(self)
        self.style().polish(self)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ozgSub — Local Subtitle Studio")
        self.resize(1120, 720)
        self.setMinimumSize(860, 580)
        self.setAcceptDrops(True)

        self.transcriber = Transcriber(model_size="large-v3")
        self.history = HistoryManager()
        self.history_entries: list[HistoryEntry] = []
        self.active_entry: HistoryEntry | None = None
        self.segment_widgets: dict[int, SegmentRow] = {}
        self.active_worker: TranscribeWorker | None = None

        self.speeds = [1.0, 1.25, 1.5, 2.0]
        self.speed_idx = 0
        self.seeking_slider = False

        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(1.0)
        self.player.positionChanged.connect(self._on_audio_position)
        self.player.durationChanged.connect(self._on_audio_duration)
        self.player.playbackStateChanged.connect(self._on_playback_state)

        self._build_ui()
        self._refresh_history_list()
        enable_windows_dark_titlebar(self)

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        # Sidebar
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(250)
        sb = QVBoxLayout(sidebar)
        sb.setContentsMargins(14, 18, 14, 14)
        sb.setSpacing(12)

        logo = QSvgWidget(str(LOGO_PATH))
        logo.setFixedSize(42, 42)
        sb.addWidget(logo, 0)

        self.new_btn = QPushButton("HOMEPAGE")
        self.new_btn.setObjectName("primaryBtn")
        self.new_btn.setFixedHeight(38)
        self.new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_btn.clicked.connect(self._show_dropzone)
        sb.addWidget(self.new_btn)

        self.history_label = QLabel("HISTORY")
        self.history_label.setObjectName("sectionLabel")
        sb.addWidget(self.history_label)

        self.history_list = QListWidget()
        self.history_list.setObjectName("historyList")
        self.history_list.itemClicked.connect(self._on_history_clicked)
        self.history_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.history_list.customContextMenuRequested.connect(self._on_history_context)
        sb.addWidget(self.history_list, 1)

        gpu = self.transcriber.gpu_info
        hw_box = QFrame()
        hw_box.setObjectName("hwBox")
        hw_lay = QVBoxLayout(hw_box)
        hw_lay.setContentsMargins(10, 9, 10, 9)
        hw_lay.setSpacing(3)

        hw_name = QLabel(gpu.get("gpu_name", "GPU"))
        hw_name.setObjectName("hwTitle")
        hw_detail_txt = (
            f"CUDA • {gpu['compute_type'].upper()}"
            + (f" • {gpu['vram_gb']} GB" if gpu.get("vram_gb") else "")
            if gpu.get("cuda_available")
            else "CPU Mode"
        )
        hw_detail = QLabel(hw_detail_txt)
        hw_detail.setObjectName("mutedLabel")
        hw_lay.addWidget(hw_name)
        hw_lay.addWidget(hw_detail)
        sb.addWidget(hw_box)

        shell.addWidget(sidebar)

        # Main stack
        self.stack = QStackedWidget()
        shell.addWidget(self.stack, 1)

        # Page 0: DropZone
        drop_page = QWidget()
        dp_lay = QVBoxLayout(drop_page)
        dp_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dp_lay.setContentsMargins(36, 36, 36, 36)

        self.drop_card = DropCard()
        self.drop_card.setFixedSize(540, 340)
        self.drop_card.file_dropped.connect(self._start_transcription)
        dc = QVBoxLayout(self.drop_card)
        dc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dc.setSpacing(14)
        dc.setContentsMargins(36, 36, 36, 36)

        drop_title = QLabel("Drop an audio or video file here")
        drop_title.setObjectName("dropTitle")
        drop_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dc.addWidget(drop_title)

        opts = QHBoxLayout()
        opts.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # opts.setSpacing(16)
        # lang_pill = QLabel("Language: English (EN)")
        # lang_pill.setObjectName("pillLabel")
        self.vad_checkbox = QCheckBox("Silence Filter (VAD)")
        self.vad_checkbox.setChecked(True)
        # opts.addWidget(lang_pill)
        opts.addWidget(self.vad_checkbox)
        dc.addLayout(opts)

        pick_btn = QPushButton("+  Choose File")
        pick_btn.setObjectName("primaryBtn")
        pick_btn.setFixedSize(160, 42)
        pick_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        pick_btn.clicked.connect(self._pick_file)
        dc.addWidget(pick_btn, 0, Qt.AlignmentFlag.AlignCenter)
        
        # drop_sub = QLabel(
        #     "Files are transcribed locally with Whisper Large v3 (English)\n"
        #     "and ready to export as .SRT subtitles."
        # )
        # drop_sub.setObjectName("dropSub")
        # drop_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # dc.addWidget(drop_sub)
        
        formats = QLabel("MP3 • WAV • M4A • FLAC • OGG • MP4 • MKV • MOV • WEBM")
        formats.setObjectName("mutedLabel")
        formats.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dc.addWidget(formats)

        dp_lay.addWidget(self.drop_card)
        self.stack.addWidget(drop_page)

        # Page 1: Transcript view
        tr_page = QWidget()
        tp = QVBoxLayout(tr_page)
        tp.setContentsMargins(0, 0, 0, 0)
        tp.setSpacing(0)

        topbar = QFrame()
        topbar.setObjectName("topbar")
        tb = QHBoxLayout(topbar)
        tb.setContentsMargins(24, 14, 24, 14)
        tb.setSpacing(10)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        self.title_edit = QLineEdit()
        self.title_edit.setObjectName("docTitle")
        self.title_edit.editingFinished.connect(self._commit_title)
        self.meta_label = QLabel("")
        self.meta_label.setObjectName("mutedLabel")
        title_col.addWidget(self.title_edit)
        title_col.addWidget(self.meta_label)
        tb.addLayout(title_col, 1)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("searchInput")
        self.search_input.setPlaceholderText("Search transcript...")
        self.search_input.setFixedWidth(200)
        self.search_input.textChanged.connect(self._apply_search_filter)
        tb.addWidget(self.search_input)

        self.export_srt_btn = QPushButton("Export .SRT")
        self.export_srt_btn.setObjectName("primaryBtn")
        self.export_srt_btn.setFixedHeight(36)
        self.export_srt_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_srt_btn.clicked.connect(self._export_srt)
        tb.addWidget(self.export_srt_btn)

        tp.addWidget(topbar)

        self.progress_banner = QFrame()
        self.progress_banner.setObjectName("progressBanner")
        pb_lay = QVBoxLayout(self.progress_banner)
        pb_lay.setContentsMargins(16, 12, 16, 12)
        pb_lay.setSpacing(8)
        pb_top = QHBoxLayout()
        self.status_label = QLabel("Preparing...")
        self.status_label.setObjectName("statusLabel")
        self.pct_label = QLabel("")
        self.pct_label.setObjectName("mutedLabel")
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("cancelBtn")
        self.cancel_btn.setFixedHeight(28)
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.clicked.connect(self._cancel_active_job)
        pb_top.addWidget(self.status_label, 1)
        pb_top.addWidget(self.pct_label)
        pb_top.addWidget(self.cancel_btn)
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        pb_lay.addLayout(pb_top)
        pb_lay.addWidget(self.progress_bar)
        self.progress_banner.hide()

        banner_wrap = QVBoxLayout()
        banner_wrap.setContentsMargins(24, 12, 24, 0)
        banner_wrap.addWidget(self.progress_banner)
        tp.addLayout(banner_wrap)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.seg_container = QWidget()
        self.seg_layout = QVBoxLayout(self.seg_container)
        self.seg_layout.setContentsMargins(28, 16, 28, 24)
        self.seg_layout.setSpacing(6)
        self.seg_layout.addStretch(1)
        self.scroll.setWidget(self.seg_container)
        tp.addWidget(self.scroll, 1)

        self.player_bar = QFrame()
        self.player_bar.setObjectName("playerBar")
        pl = QHBoxLayout(self.player_bar)
        pl.setContentsMargins(20, 10, 20, 10)
        pl.setSpacing(12)

        back_btn = QPushButton("-5s")
        back_btn.setObjectName("miniBtn")
        back_btn.clicked.connect(lambda: self._skip_audio(-5000))
        self.play_btn = QPushButton("▶")
        self.play_btn.setObjectName("playBtn")
        self.play_btn.setFixedSize(36, 36)
        self.play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_btn.clicked.connect(self._toggle_play)
        fwd_btn = QPushButton("+5s")
        fwd_btn.setObjectName("miniBtn")
        fwd_btn.clicked.connect(lambda: self._skip_audio(5000))

        self.cur_time_lbl = QLabel("00:00")
        self.cur_time_lbl.setObjectName("timeLabel")
        self.audio_slider = QSlider(Qt.Orientation.Horizontal)
        self.audio_slider.setRange(0, 0)
        self.audio_slider.sliderPressed.connect(lambda: setattr(self, "seeking_slider", True))
        self.audio_slider.sliderReleased.connect(self._on_slider_released)
        self.tot_time_lbl = QLabel("00:00")
        self.tot_time_lbl.setObjectName("timeLabel")

        self.speed_btn = QPushButton("1x")
        self.speed_btn.setObjectName("miniBtn")
        self.speed_btn.setFixedWidth(48)
        self.speed_btn.clicked.connect(self._cycle_speed)

        pl.addWidget(back_btn)
        pl.addWidget(self.play_btn)
        pl.addWidget(fwd_btn)
        pl.addWidget(self.cur_time_lbl)
        pl.addWidget(self.audio_slider, 1)
        pl.addWidget(self.tot_time_lbl)
        pl.addWidget(self.speed_btn)
        tp.addWidget(self.player_bar)

        self.stack.addWidget(tr_page)

    # Drag & drop
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self.active_worker is not None:
            event.ignore()
            return
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                p = Path(url.toLocalFile())
                if p.is_file() and p.suffix.lower() in ALLOWED_EXTENSIONS:
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        if self.active_worker is not None:
            return
        for url in event.mimeData().urls():
            p = Path(url.toLocalFile())
            if p.is_file() and p.suffix.lower() in ALLOWED_EXTENSIONS:
                self._start_transcription(p)
                event.acceptProposedAction()
                return

    # History
    def _refresh_history_list(self) -> None:
        self.history_entries = self.history.load()
        self.history_list.clear()
        self.history_label.setText(f"HISTORY ({len(self.history_entries)})")
        active_id = self.active_entry.id if self.active_entry else None
        for entry in self.history_entries:
            dur = fmt_time(entry.duration)
            cnt = len(entry.segments)
            lw_item = QListWidgetItem(f"{entry.title}\n{dur} • {cnt} lines")
            lw_item.setData(Qt.ItemDataRole.UserRole, entry.id)
            self.history_list.addItem(lw_item)
            if entry.id == active_id:
                self.history_list.setCurrentItem(lw_item)

    def _on_history_clicked(self, lw_item: QListWidgetItem) -> None:
        if self.active_worker is not None:
            return
        entry_id = lw_item.data(Qt.ItemDataRole.UserRole)
        found = next((x for x in self.history_entries if x.id == entry_id), None)
        if found:
            self._open_entry(found)

    def _on_history_context(self, pos) -> None:
        if self.active_worker is not None:
            return
        lw_item = self.history_list.itemAt(pos)
        if not lw_item:
            return
        entry_id = lw_item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        del_act = QAction("Delete", self)
        del_act.triggered.connect(lambda: self._delete_history_entry(entry_id))
        menu.addAction(del_act)
        menu.exec(self.history_list.mapToGlobal(pos))

    def _delete_history_entry(self, entry_id: str) -> None:
        if self.active_entry and self.active_entry.id == entry_id:
            self.player.stop()
            self.player.setSource(QUrl())
            self.active_entry = None
            self.stack.setCurrentIndex(0)
        self.history.delete(entry_id)
        self._refresh_history_list()

    # Navigation & rendering
    def _show_dropzone(self) -> None:
        if self.active_worker is not None:
            return
        self.player.stop()
        self.active_entry = None
        self.history_list.clearSelection()
        self.stack.setCurrentIndex(0)

    def _pick_file(self) -> None:
        if self.active_worker is not None:
            return
        exts = " ".join(f"*{ext}" for ext in sorted(ALLOWED_EXTENSIONS))
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Select Audio or Video File",
            "",
            f"Media Files ({exts});;All Files (*.*)",
        )
        if path_str:
            self._start_transcription(Path(path_str))

    def _open_entry(self, entry: HistoryEntry) -> None:
        self.player.stop()
        self.active_entry = entry
        self.search_input.clear()
        self.stack.setCurrentIndex(1)
        self._render_active_entry()
        self._load_audio_for_entry(entry)

    def _load_audio_for_entry(self, entry: HistoryEntry) -> None:
        path = Path(entry.audio_path)
        if path.is_file():
            self.player.setSource(QUrl.fromLocalFile(str(path)))
            self.player.setPlaybackRate(self.speeds[self.speed_idx])
            self.player_bar.show()
        else:
            self.player.setSource(QUrl())
            self.player_bar.hide()

    def _clear_segment_widgets(self) -> None:
        self.segment_widgets.clear()
        while self.seg_layout.count() > 1:
            child = self.seg_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _render_active_entry(self) -> None:
        if not self.active_entry:
            return
        entry = self.active_entry
        self.title_edit.setText(entry.title)

        parts = []
        if entry.duration:
            parts.append(fmt_time(entry.duration))
        parts.append(f"{len(entry.segments)} lines")
        if entry.duration and entry.processing_time:
            spd = entry.duration / entry.processing_time
            parts.append(f"{spd:.1f}x realtime")
        self.meta_label.setText("  •  ".join(parts))

        self._clear_segment_widgets()
        for idx, seg in enumerate(entry.segments, start=1):
            self._append_segment_widget(idx, seg)

    def _append_segment_widget(self, seg_idx: int, seg: TranscriptSegment) -> None:
        row = SegmentRow(seg_idx, seg)
        row.seek_requested.connect(self._seek_to_sec)
        row.edit_requested.connect(self._edit_segment)
        self.segment_widgets[seg_idx] = row
        self.seg_layout.insertWidget(self.seg_layout.count() - 1, row)

    def _apply_search_filter(self, query: str) -> None:
        if not self.active_entry:
            return
        q = query.strip().lower()
        for idx, seg in enumerate(self.active_entry.segments, start=1):
            widget = self.segment_widgets.get(idx)
            if widget:
                widget.setVisible(not q or q in seg.text.lower())

    def _commit_title(self) -> None:
        if not self.active_entry or self.active_worker is not None:
            return
        new_title = self.title_edit.text().strip()
        if new_title and new_title != self.active_entry.title:
            self.active_entry.title = new_title
            self.history.update(self.active_entry)
            self._refresh_history_list()

    def _edit_segment(self, seg_idx: int) -> None:
        if not self.active_entry or self.active_worker is not None:
            return
        pos = seg_idx - 1
        if pos < 0 or pos >= len(self.active_entry.segments):
            return
        seg = self.active_entry.segments[pos]
        dlg = EditSegmentDialog(seg, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_text = dlg.get_text()
            if new_text:
                seg.text = new_text
                widget = self.segment_widgets.get(seg_idx)
                if widget:
                    widget.set_text(new_text)
                self.history.update(self.active_entry)

    # Transcription
    def _set_busy(self, busy: bool, status_text: str = "") -> None:
        self.new_btn.setEnabled(not busy)
        self.export_srt_btn.setEnabled(not busy)
        self.title_edit.setReadOnly(busy)
        self.progress_banner.setVisible(busy)
        if busy:
            self.status_label.setText(status_text)
            self.pct_label.setText("Preparing")
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)

    def _start_transcription(self, source_path: Path) -> None:
        if self.active_worker is not None:
            return
        self.player.stop()
        self.player_bar.hide()
        self.active_entry = HistoryEntry(
            id="",
            title=source_path.stem,
            created_at="",
            file_name=source_path.name,
            audio_path=str(source_path),
            segments=[],
            duration=0.0,
            processing_time=0.0,
        )
        self.stack.setCurrentIndex(1)
        self._render_active_entry()
        self._set_busy(True, "Preparing audio file...")

        worker = TranscribeWorker(
            self.transcriber,
            source_path,
            self.history.uploads_dir,
            self.vad_checkbox.isChecked(),
        )
        worker.status_changed.connect(self.status_label.setText)
        worker.metadata_ready.connect(self._on_transcribe_meta)
        worker.segment_added.connect(self._on_transcribe_segment)
        worker.finished_ok.connect(self._on_transcribe_done)
        worker.failed.connect(self._on_worker_error)
        worker.cancelled.connect(self._on_transcribe_cancelled)
        self.active_worker = worker
        worker.start()

    def _on_transcribe_meta(self, duration: float) -> None:
        if self.active_entry:
            self.active_entry.duration = duration
            self.meta_label.setText(f"{fmt_time(duration)}  •  Processing...")

    def _on_transcribe_segment(self, idx: int, seg: TranscriptSegment, pct: float) -> None:
        if not self.active_entry:
            return
        self.active_entry.segments.append(seg)
        self._append_segment_widget(idx, seg)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(int(pct))
        self.pct_label.setText(f"{int(pct)}%")
        self.meta_label.setText(
            f"{fmt_time(self.active_entry.duration)}  •  {len(self.active_entry.segments)} lines"
        )
        self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum())

    def _on_transcribe_done(self, record: dict) -> None:
        self.active_worker = None
        self._set_busy(False)
        saved = self.history.add(
            record["audio_path"],
            record["segments"],
            title=record["title"],
            file_name=record["file_name"],
            duration=record["duration"],
            processing_time=record["processing_time"],
            entry_id=record["id"],
        )
        self._open_entry(saved)
        self._refresh_history_list()

    def _on_transcribe_cancelled(self) -> None:
        self.active_worker = None
        self._set_busy(False)
        self.active_entry = None
        self.stack.setCurrentIndex(0)

    def _on_worker_error(self, err: str) -> None:
        self.active_worker = None
        self._set_busy(False)
        QMessageBox.critical(self, "Error", err)

    def _cancel_active_job(self) -> None:
        if self.active_worker:
            self.status_label.setText("Cancelling...")
            self.active_worker.cancel()

    # Export
    def _export_srt(self) -> None:
        if not self.active_entry or not self.active_entry.segments:
            return
        default_name = f"{self.active_entry.title}.srt"
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save SRT",
            default_name,
            "SubRip Subtitle (*.srt)",
        )
        if not save_path:
            return
        try:
            export_srt(self.active_entry.segments, save_path)
        except OSError as exc:
            QMessageBox.critical(self, "Save Error", str(exc))

    # Audio player
    def _toggle_play(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _skip_audio(self, delta_ms: int) -> None:
        new_pos = max(0, min(self.player.duration(), self.player.position() + delta_ms))
        self.player.setPosition(new_pos)

    def _seek_to_sec(self, sec: float) -> None:
        self.player.setPosition(int(sec * 1000))
        self.player.play()

    def _on_slider_released(self) -> None:
        self.seeking_slider = False
        self.player.setPosition(self.audio_slider.value())

    def _cycle_speed(self) -> None:
        self.speed_idx = (self.speed_idx + 1) % len(self.speeds)
        rate = self.speeds[self.speed_idx]
        self.player.setPlaybackRate(rate)
        self.speed_btn.setText(f"{rate:g}x")

    def _on_playback_state(self, state: QMediaPlayer.PlaybackState) -> None:
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.play_btn.setText("❚❚" if playing else "▶")

    def _on_audio_duration(self, duration_ms: int) -> None:
        self.audio_slider.setRange(0, max(0, duration_ms))
        self.tot_time_lbl.setText(fmt_time(duration_ms / 1000.0))

    def _on_audio_position(self, pos_ms: int) -> None:
        if not self.seeking_slider:
            self.audio_slider.setValue(pos_ms)
        sec = pos_ms / 1000.0
        self.cur_time_lbl.setText(fmt_time(sec))
        for widget in self.segment_widgets.values():
            widget.set_active(widget.start_sec <= sec <= widget.end_sec + 0.15)

    def closeEvent(self, event) -> None:
        self.player.stop()
        if self.active_worker and self.active_worker.isRunning():
            self.active_worker.cancel()
            self.active_worker.wait(2000)
        super().closeEvent(event)
