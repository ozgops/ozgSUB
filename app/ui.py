from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSlider,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.history import HistoryEntry, HistoryManager
from app.srt_exporter import export_srt, segments_to_srt
from app.transcriber import ALLOWED_EXTENSIONS, Transcriber, TranscriptSegment
from app.worker import TranscribeWorker


def _format_ms(ms: int) -> str:
    total_seconds = max(0, ms // 1000)
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ozgSub")
        self.resize(1040, 640)

        self.transcriber = Transcriber(model_size="large-v3")
        self.history = HistoryManager()
        self.history_map: dict[str, HistoryEntry] = {}

        self.current_audio_path: str | None = None
        self.current_segments: list[TranscriptSegment] = []
        self.worker: TranscribeWorker | None = None

        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(0.85)

        self._build_ui()
        self._connect_player()
        self._apply_style()
        self._refresh_history()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(14, 14, 14, 14)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root_layout.addWidget(splitter, stretch=1)

        # Left pane: local history
        history_pane = QWidget()
        history_layout = QVBoxLayout(history_pane)
        history_layout.setContentsMargins(0, 0, 8, 0)
        history_layout.setSpacing(8)

        history_title = QLabel("History")
        history_title.setStyleSheet("font-weight: 600; font-size: 14px;")
        history_layout.addWidget(history_title)

        self.history_list = QListWidget()
        self.history_list.itemClicked.connect(self._on_history_selected)
        history_layout.addWidget(self.history_list, stretch=1)

        self.delete_history_btn = QPushButton("Delete Selected")
        self.delete_history_btn.clicked.connect(self._delete_selected_history)
        history_layout.addWidget(self.delete_history_btn)

        # Right pane: transcriber + player
        main_pane = QWidget()
        layout = QVBoxLayout(main_pane)
        layout.setContentsMargins(8, 0, 0, 0)
        layout.setSpacing(12)

        top_row = QHBoxLayout()
        self.select_btn = QPushButton("Open Audio")
        self.select_btn.clicked.connect(self._select_file)

        self.file_label = QLabel("No file selected")
        self.file_label.setStyleSheet("color: #9aa0a6;")

        top_row.addWidget(self.select_btn)
        top_row.addWidget(self.file_label, stretch=1)
        layout.addLayout(top_row)

        action_row = QHBoxLayout()
        self.transcribe_btn = QPushButton("Transcribe (Large v3 • EN)")
        self.transcribe_btn.setEnabled(False)
        self.transcribe_btn.clicked.connect(self._start_transcription)

        self.export_btn = QPushButton("Export .SRT")
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self._export_srt)

        action_row.addWidget(self.transcribe_btn)
        action_row.addWidget(self.export_btn)
        layout.addLayout(action_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.output_text = QPlainTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setPlaceholderText("Transcription output will appear here...")
        layout.addWidget(self.output_text, stretch=1)

        # Built-in audio player bar
        player_row = QHBoxLayout()
        self.play_btn = QPushButton("Play")
        self.play_btn.setEnabled(False)
        self.play_btn.setFixedWidth(72)
        self.play_btn.clicked.connect(self._toggle_playback)

        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setEnabled(False)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.sliderMoved.connect(self.player.setPosition)

        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setStyleSheet("color: #9aa0a6; font-family: Consolas, monospace;")

        player_row.addWidget(self.play_btn)
        player_row.addWidget(self.seek_slider, stretch=1)
        player_row.addWidget(self.time_label)
        layout.addLayout(player_row)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #9aa0a6;")
        layout.addWidget(self.status_label)

        splitter.addWidget(history_pane)
        splitter.addWidget(main_pane)
        splitter.setSizes([250, 790])

    def _connect_player(self) -> None:
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.playbackStateChanged.connect(self._on_playback_state_changed)

    def _apply_style(self) -> None:
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #16181d;
                color: #e8eaed;
                font-family: "Segoe UI", sans-serif;
                font-size: 13px;
            }
            QPushButton {
                background-color: #2b303b;
                border: 1px solid #3c4252;
                border-radius: 6px;
                padding: 8px 14px;
            }
            QPushButton:hover { background-color: #3a4150; }
            QPushButton:disabled { color: #666c78; background-color: #20232b; }
            QPlainTextEdit, QListWidget {
                background-color: #1e2128;
                border: 1px solid #2f3440;
                border-radius: 6px;
                padding: 8px;
            }
            QPlainTextEdit { font-family: "Consolas", monospace; }
            QListWidget::item { padding: 6px; border-radius: 4px; }
            QListWidget::item:selected { background-color: #2f3b52; }
            QProgressBar {
                background-color: #1e2128;
                border: 1px solid #2f3440;
                border-radius: 6px;
                text-align: center;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: #4f8cff;
                border-radius: 5px;
            }
        """)

    def _load_audio_into_player(self, file_path: str) -> None:
        self.player.stop()
        path = Path(file_path)
        if not path.is_file():
            self.play_btn.setEnabled(False)
            self.seek_slider.setEnabled(False)
            self.time_label.setText("00:00 / 00:00")
            self.status_label.setText("Audio file not found on disk.")
            return
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        self.play_btn.setEnabled(True)
        self.seek_slider.setEnabled(True)

    def _toggle_playback(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _on_position_changed(self, position: int) -> None:
        if not self.seek_slider.isSliderDown():
            self.seek_slider.setValue(position)
        self.time_label.setText(f"{_format_ms(position)} / {_format_ms(self.player.duration())}")

    def _on_duration_changed(self, duration: int) -> None:
        self.seek_slider.setRange(0, duration)
        self.time_label.setText(f"{_format_ms(self.player.position())} / {_format_ms(duration)}")

    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        is_playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.play_btn.setText("Pause" if is_playing else "Play")

    def _refresh_history(self) -> None:
        self.history_list.clear()
        self.history_map.clear()
        for entry in self.history.load():
            self.history_map[entry.id] = entry
            item = QListWidgetItem(f"{entry.file_name}\n{entry.created_at}")
            item.setData(Qt.ItemDataRole.UserRole, entry.id)
            self.history_list.addItem(item)

    def _on_history_selected(self, item: QListWidgetItem) -> None:
        entry_id = item.data(Qt.ItemDataRole.UserRole)
        entry = self.history_map.get(entry_id)
        if not entry:
            return
        self.current_audio_path = entry.audio_path
        self.current_segments = entry.segments
        self.file_label.setText(entry.file_name)
        self.output_text.setPlainText(segments_to_srt(entry.segments))
        self.export_btn.setEnabled(bool(entry.segments))
        self.transcribe_btn.setEnabled(Path(entry.audio_path).is_file())
        self._load_audio_into_player(entry.audio_path)
        self.status_label.setText(f"Loaded from history ({len(entry.segments)} segments).")

    def _delete_selected_history(self) -> None:
        item = self.history_list.currentItem()
        if not item:
            return
        entry_id = item.data(Qt.ItemDataRole.UserRole)
        if self.history.delete(entry_id):
            self._refresh_history()
            self.status_label.setText("History entry removed.")

    def _select_file(self) -> None:
        exts = " ".join(f"*{ext}" for ext in sorted(ALLOWED_EXTENSIONS))
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Audio or Video File",
            "",
            f"Media Files ({exts})",
        )
        if not file_path:
            return
        self.current_audio_path = file_path
        self.file_label.setText(Path(file_path).name)
        self.transcribe_btn.setEnabled(True)
        self._load_audio_into_player(file_path)
        self.status_label.setText("File ready.")

    def _start_transcription(self) -> None:
        if not self.current_audio_path:
            return
        self._set_busy(True)
        self.progress_bar.setValue(0)
        self.output_text.clear()
        self.status_label.setText("Loading model and transcribing...")

        self.worker = TranscribeWorker(self.transcriber, self.current_audio_path)
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.finished.connect(self._on_transcription_finished)
        self.worker.error.connect(self._on_transcription_error)
        self.worker.start()

    def _on_transcription_finished(self, segments: list[TranscriptSegment]) -> None:
        self._set_busy(False)
        self.current_segments = segments
        self.output_text.setPlainText(segments_to_srt(segments))
        self.export_btn.setEnabled(bool(segments))

        if self.current_audio_path and segments:
            self.history.add(self.current_audio_path, segments)
            self._refresh_history()

        self.status_label.setText(f"Done ({len(segments)} segments).")

    def _on_transcription_error(self, message: str) -> None:
        self._set_busy(False)
        self.status_label.setText("Transcription failed.")
        QMessageBox.critical(self, "Transcription Error", message)

    def _export_srt(self) -> None:
        if not self.current_segments or not self.current_audio_path:
            return
        default_name = str(Path(self.current_audio_path).with_suffix(".srt"))
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save SRT File",
            default_name,
            "SubRip Subtitle (*.srt)",
        )
        if not save_path:
            return
        try:
            saved = export_srt(self.current_segments, save_path)
            self.status_label.setText(f"Saved: {saved.name}")
        except OSError as exc:
            QMessageBox.critical(self, "Save Error", str(exc))

    def _set_busy(self, busy: bool) -> None:
        self.select_btn.setEnabled(not busy)
        self.transcribe_btn.setEnabled(not busy and bool(self.current_audio_path))
        self.export_btn.setEnabled(not busy and bool(self.current_segments))