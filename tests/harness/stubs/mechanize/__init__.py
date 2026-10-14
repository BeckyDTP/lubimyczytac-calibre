class HTTPError(Exception):
    def __init__(self, code=500, body=b''):
        Exception.__init__(self, 'HTTP Error %d' % code)
        self.code = code
        self._body = body
    def read(self):
        return self._body
