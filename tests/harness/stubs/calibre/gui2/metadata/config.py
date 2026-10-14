from qt.core import QGridLayout
class ConfigWidget(object):
    def __init__(self, plugin):
        self.plugin = plugin
        self.l = QGridLayout()
    def commit(self):
        pass
