class _Widget(object):
    def __init__(self, *a, **k):
        self._checked = False; self._value = 0; self._index = 0
    def __getattr__(self, n):
        return lambda *a, **k: None
    def setChecked(self, v): self._checked = bool(v)
    def isChecked(self): return self._checked
    def setProperty(self, name, v): self._value = v
    def value(self): return self._value
    def setCurrentIndex(self, i): self._index = i
    def currentIndex(self): return self._index
    def __or__(self, o): return self
class _Grid(_Widget):
    def __init__(self, *a, **k):
        _Widget.__init__(self); self._rows = 0
    def addWidget(self, w, row=0, col=0, rs=1, cs=1):
        self._rows = max(self._rows, row + rs)
    def rowCount(self): return self._rows
class _Namespace(object):
    def __getattr__(self, n):
        return _Widget
QtWidgets = _Namespace(); QtGui = _Namespace(); QtCore = _Namespace()
Qt = _Widget()
QGridLayout = _Grid
for _n in ['QApplication','QAction','QMessageBox','QDialog','QMenu','QHeaderView','QLabel','QTableWidget','QIcon','QPixmap','QSize','QAbstractItemView','QTableWidgetItem','QPushButton','QHBoxLayout','QVBoxLayout','QPalette','QColor','QGroupBox','QCheckBox','QComboBox']:
    globals()[_n] = type(_n, (_Widget,), {})
