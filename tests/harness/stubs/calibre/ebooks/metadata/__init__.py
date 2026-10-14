def check_isbn(isbn):
    if not isbn:
        return None
    s = ''.join(ch for ch in str(isbn) if ch.isdigit() or ch in 'Xx')
    return s if len(s) in (10, 13) else None
