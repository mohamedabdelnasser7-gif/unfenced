"""HTTP for calls that carry a key (the WhatsApp token, the Shopify token).

Redirects are refused, so a key in a header never follows one to another host
(urllib's default opener keeps the headers on a redirect).
"""
import urllib.request


class NoRedirects(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect: the 3xx answer comes back as an HTTPError."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def no_redirect_opener():
    return urllib.request.build_opener(NoRedirects())


def open_once(req, timeout):
    """Open one request with no redirect followed."""
    return no_redirect_opener().open(req, timeout=timeout)
