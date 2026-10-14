import re, threading
def fixauthors(authors):
    return list(authors) if authors else authors
class Source(object):
    cached_cover_url_is_reliable = True
    cache_lock = threading.RLock()
    def __init__(self, *a, **k):
        self._identifier_to_cover_url_cache = {}
        self._isbn_to_identifier_cache = {}
    def test_fields(self, mi):
        return None
    def cached_isbn_to_identifier(self, isbn):
        return self._isbn_to_identifier_cache.get(isbn)
    def cache_isbn_to_identifier(self, isbn, id_):
        with self.cache_lock:
            self._isbn_to_identifier_cache[isbn] = id_
    def cache_identifier_to_cover_url(self, id_, url):
        with self.cache_lock:
            self._identifier_to_cover_url_cache[id_] = url
    def get_title_tokens(self, title, strip_joiners=True, strip_subtitle=False):
        # Kopia logiki calibre (wystarczajaca dla testow A/B - obie strony uzywaja tej samej)
        if title:
            if strip_subtitle:
                subtitle = re.compile(r'([\(\[\{].*?[\)\]\}]|[/:\\].*$)')
                if len(subtitle.sub('', title)) > 1:
                    title = subtitle.sub('', title)
            title_patterns = [(re.compile(pat, re.IGNORECASE), repl) for pat, repl in [
                (r'(?i)[({\[](\d{4}|omnibus|anthology|hardcover|audiobook|audio\scd|paperback|turtleback|mass\s*market|edition|ed\.)[\])}]', ''),
                (r'(?i)[({\[].*?(edition|ed.).*?[\]})]', ''),
                (r'(\d+),(\d+)', r'\1\2'),
                (r'(\s-)', ' '),
                (r'''[:,;!@$%^&*(){}.`~"\s\[\]/]''', ' '),
            ]]
            for pat, repl in title_patterns:
                title = pat.sub(repl, title)
            tokens = title.split()
            for token in tokens:
                token = token.strip().strip('"').strip("'")
                if token and (not strip_joiners or token.lower() not in ('a', 'and', 'the', '&')):
                    yield token
