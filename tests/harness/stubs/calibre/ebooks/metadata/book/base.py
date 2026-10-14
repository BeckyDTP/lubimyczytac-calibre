class Metadata(object):
    def __init__(self, title, authors=None):
        self.title = title
        self.authors = list(authors) if authors else []
        self.tags = []
        self.comments = None
        self.isbn = None
        self.identifiers = {}
        self.rating = None
        self.publisher = None
        self.pubdate = None
        self.series = None
        self.series_index = None
        self.languages = []
        self.has_cover = False
        self.source_relevance = None
    def set_identifier(self, k, v):
        self.identifiers[k] = v
    def snapshot(self):
        d = dict(self.__dict__)
        return d
