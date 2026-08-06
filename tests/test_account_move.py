from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAccountMoveFelPortalLink(TransactionCase):
    def test_accepts_feel_certificate_url(self):
        document_url = (
            "https://report.feel.com.gt/ingfacereport/"
            "ingfacereport_documento?uuid=20F70299-D704-4685-977D-27966366A572"
        )
        invoice = self.env["account.move"].new(
            {"fel_documento_certificado": document_url}
        )

        self.assertEqual(invoice._get_portal_fel_document_url(), document_url)

    def test_rejects_untrusted_certificate_urls(self):
        invoice = self.env["account.move"].new()
        invalid_urls = (
            "javascript:alert(1)",
            "http://report.feel.com.gt/documento",
            "https://feel.com.gt.example.com/documento",
            "https://usuario:clave@report.feel.com.gt/documento",
        )

        for invalid_url in invalid_urls:
            invoice.fel_documento_certificado = invalid_url
            self.assertFalse(invoice._get_portal_fel_document_url())
