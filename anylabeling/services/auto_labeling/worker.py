from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from anylabeling.views.labeling.logger import logger


class GenericWorker(QObject):
    finished = pyqtSignal()

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs

    @pyqtSlot()
    def run(self):
        # ``finished`` must fire even when the payload raises.  Callers clear
        # their "a model operation is running" flag from that signal, so a
        # missed emit leaves the rest of the session unable to load anything.
        try:
            self.func(*self.args, **self.kwargs)
        except Exception as e:  # noqa
            logger.warning(f"Background worker failed: {e}")
        finally:
            self.finished.emit()
