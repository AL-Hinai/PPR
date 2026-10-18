import secrets

from django.conf import settings


class ContentSecurityPolicyMiddleware:
    """Adds a Content-Security-Policy with a per-request nonce (``request.csp_nonce``) for inline scripts.

    Only HTML pages get it: a policy on a PDF response blocks the browser's built-in PDF viewer, and responses
    that set their own policy (e.g. sandboxed dossier files) keep it.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.csp_nonce = secrets.token_urlsafe(16)
        response = self.get_response(request)
        is_html = response.get("Content-Type", "").startswith("text/html")
        if settings.CSP_ENABLED and is_html and "Content-Security-Policy" not in response:
            response["Content-Security-Policy"] = "; ".join(
                f"{directive} {' '.join(sources)}".replace("{nonce}", request.csp_nonce)
                for directive, sources in settings.CSP_DIRECTIVES.items()
            )
        return response
