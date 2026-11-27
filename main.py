import sys
import av
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from app.theme import STYLESHEET
from app.ui import LOGO_PATH, MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("ozgSub")
    app.setWindowIcon(QIcon(str(LOGO_PATH)))
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(STYLESHEET)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
