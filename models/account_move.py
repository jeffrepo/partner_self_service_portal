from urllib.parse import urlsplit

from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    def _get_portal_fel_document_url(self):
        """Return a trusted FEL certificate URL for the invoice portal."""
        self.ensure_one()
        document_url = (self.fel_documento_certificado or "").strip()
        if not document_url:
            return False

        try:
            parsed_url = urlsplit(document_url)
        except ValueError:
            return False

        hostname = (parsed_url.hostname or "").lower().rstrip(".")
        is_feel_hostname = hostname == "feel.com.gt" or hostname.endswith(
            ".feel.com.gt"
        )
        if (
            parsed_url.scheme.lower() != "https"
            or not is_feel_hostname
            or parsed_url.username
            or parsed_url.password
        ):
            return False
        return document_url
