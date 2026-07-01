"""Entry point for the AI Ebook Reader & Vocabulary Learning Platform."""

import logging
import os
import sys

# Set Qt Quick Controls style before QApplication is created
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Fusion")

logger = logging.getLogger(__name__)


def main() -> int:
    """Initialize and start the application."""
    # Configure logging early - output to both console and file
    log_dir = os.path.join(os.path.expanduser("~"), ".ai-ebook-reader", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "app.log")

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )
    logger.info("Log file: %s", log_file)

    # QtWebEngine must be initialized before QApplication
    from PySide6.QtWebEngineQuick import QtWebEngineQuick
    QtWebEngineQuick.initialize()

    from PySide6.QtWidgets import QApplication
    from PySide6.QtQml import QQmlApplicationEngine

    from src.application.app import Application
    from src.presentation.controllers.app_controller import AppController, PDFImageProvider

    app = QApplication(sys.argv)
    app.setApplicationName("AI Ebook Reader")
    app.setOrganizationName("AIEbookReader")
    app.setApplicationVersion("0.1.0")

    # Initialize application lifecycle manager
    application = Application()

    # Run startup sequence (migrations, WAL recovery, settings)
    if not application.startup():
        logger.error("Application startup failed — exiting")
        return 1

    # Connect application shutdown to Qt's aboutToQuit signal
    app.aboutToQuit.connect(application.shutdown)

    engine = QQmlApplicationEngine()

    # Create main app controller (uses WebEngine for PDF rendering)
    app_controller = AppController()

    # Expose to QML
    engine.rootContext().setContextProperty("app", application)
    engine.rootContext().setContextProperty("appController", app_controller)

    # Load main QML window
    qml_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "presentation", "qml"
    )
    engine.addImportPath(qml_dir)
    qml_path = os.path.join(qml_dir, "MainWindow.qml")
    engine.load(qml_path)

    if not engine.rootObjects():
        logger.error("Failed to load QML — exiting")
        application.shutdown()
        return 1

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
