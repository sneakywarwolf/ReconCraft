# ReconCraft by Nirmal Chakraborty
# Copyright (c) 2025. All rights reserved.
# See LICENSE for details.


#!/usr/bin/env python3
# main.py — hybrid entrypoint with optional debug mode
#python main.py --debug for debug mode

import sys
import logging
import traceback
from pathlib import Path

from PyQt5.QtWidgets import QApplication, QMessageBox, QStatusBar
from gui.ui_main import ReconCraftUI
from PyQt5.QtCore import Qt


LOG_FILE = Path(__file__).resolve().parent / "reconcraft.log"


def install_excepthook(debug: bool):
    """
    Global exception hook:
    - Always logs to reconcraft.log
    - If debug=True, also shows a QMessageBox with details
    """
    def _excepthook(exc_type, exc, tb):
        try:
            logging.exception("Uncaught exception", exc_info=(exc_type, exc, tb))
            if debug:
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Critical)
                msg.setWindowTitle("ReconCraft crashed")
                msg.setText(str(exc))
                msg.setDetailedText("".join(traceback.format_exception(exc_type, exc, tb)))
                msg.exec_()
        finally:
            # Also print to console for attached runs
            traceback.print_exception(exc_type, exc, tb)
            sys.exit(1)

    sys.excepthook = _excepthook


def main(debug: bool = False):
    # Logging: INFO by default; DEBUG in debug mode
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(LOG_FILE),
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    install_excepthook(debug)

    if debug:
        print("[DEBUG] ReconCraft starting…")

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)

    window = ReconCraftUI()
    window.show()

    if debug:
        print("[DEBUG] UI initialized; entering event loop")

    sys.exit(app.exec_())


if __name__ == "__main__":
    debug_mode = "--debug" in sys.argv
    # Remove the flag so Qt doesn't see it
    if debug_mode:
        sys.argv = [arg for arg in sys.argv if arg != "--debug"]
    main(debug=debug_mode)


