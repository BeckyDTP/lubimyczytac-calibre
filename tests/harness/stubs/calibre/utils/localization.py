import unicodedata
_MAP = {'ł': 'l', 'Ł': 'L', 'ß': 'ss', 'ø': 'o', 'Ø': 'O', 'đ': 'd', 'Đ': 'D'}
class _UDC(object):
    def decode(self, s):
        out = []
        for ch in s:
            if ch in _MAP:
                out.append(_MAP[ch]); continue
            d = unicodedata.normalize('NFKD', ch)
            out.append(''.join(c for c in d if not unicodedata.combining(c)))
        return ''.join(out)
_udc = _UDC()
def get_udc():
    return _udc
def canonicalize_lang(x):
    return x
def get_lang():
    return 'pl'
