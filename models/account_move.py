import unicodedata
from urllib.parse import urlsplit

from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    _PORTAL_FEL_SERIES_FIELDS = (
        "fel_serie",
        "fel_documento_serie",
        "fel_serie_documento",
        "fel_numero_serie",
        "serie_fel",
        "serie_documento_fel",
        "fel_series",
    )
    _PORTAL_FEL_NUMBER_FIELDS = (
        "fel_numero",
        "fel_documento_numero",
        "fel_numero_documento",
        "numero_fel",
        "numero_documento_fel",
        "fel_number",
        "fel_no",
    )

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

    @staticmethod
    def _normalize_fel_field_text(value):
        return "".join(
            character
            for character in unicodedata.normalize("NFKD", value or "")
            if not unicodedata.combining(character)
        ).lower()

    def _get_portal_fel_metadata_value(self, candidate_names, search_terms):
        self.ensure_one()
        field_name = next(
            (name for name in candidate_names if name in self._fields),
            False,
        )
        if not field_name:
            for name, field in self._fields.items():
                field_description = self._normalize_fel_field_text(field.string)
                searchable_text = self._normalize_fel_field_text(
                    f"{name} {field_description}"
                )
                if (
                    ("fel" in searchable_text or "dte" in searchable_text)
                    and any(term in searchable_text for term in search_terms)
                    and field.type in ("char", "text", "integer")
                ):
                    field_name = name
                    break
        if not field_name:
            return False
        value = self.sudo()[field_name]
        return str(value).strip() if value not in (False, None, "") else False

    def _get_portal_fel_series(self):
        return self._get_portal_fel_metadata_value(
            self._PORTAL_FEL_SERIES_FIELDS,
            ("serie", "series"),
        )

    def _get_portal_fel_number(self):
        return self._get_portal_fel_metadata_value(
            self._PORTAL_FEL_NUMBER_FIELDS,
            ("numero", "number", "folio"),
        )
