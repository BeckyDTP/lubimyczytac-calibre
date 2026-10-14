def sanitize_comments_html(html):
    if isinstance(html, bytes):
        html = html.decode('utf-8')
    return html
