class JSONConfig(dict):
    def __init__(self, name):
        dict.__init__(self)
        self.name = name
        self.defaults = {}
    def __getitem__(self, key):
        if dict.__contains__(self, key):
            return dict.__getitem__(self, key)
        return self.defaults[key]
