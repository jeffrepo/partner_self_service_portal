from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import PartnerSelfServicePortalCommon


@tagged("post_install", "-at_install")
class TestPortalConfirmationKey(PartnerSelfServicePortalCommon):
    def test_key_is_hashed_and_verified_per_contact(self):
        confirmation_key = "Compra-2026"

        self.customer_contact._set_portal_confirmation_key(confirmation_key)

        self.assertTrue(
            self.customer_contact.portal_confirmation_key_configured
        )
        self.assertNotIn(
            confirmation_key,
            self.customer_contact.sudo().portal_confirmation_key_hash,
        )
        is_valid, error = (
            self.customer_contact._verify_portal_confirmation_key(
                confirmation_key
            )
        )
        self.assertTrue(is_valid)
        self.assertFalse(error)

        other_contact = self.env["res.partner"].create(
            {
                "name": "Other Portal User",
                "parent_id": self.customer_company.id,
            }
        )
        is_valid, error = other_contact._verify_portal_confirmation_key(
            confirmation_key
        )
        self.assertFalse(is_valid)
        self.assertTrue(error)

    def test_key_requires_six_characters(self):
        with self.assertRaises(ValidationError):
            self.customer_contact._set_portal_confirmation_key("12345")

    def test_key_is_temporarily_locked_after_five_failed_attempts(self):
        self.customer_contact._set_portal_confirmation_key("Compra-2026")

        for _attempt in range(5):
            is_valid, _error = (
                self.customer_contact._verify_portal_confirmation_key(
                    "incorrecta"
                )
            )
            self.assertFalse(is_valid)

        self.assertGreater(
            self.customer_contact.sudo().portal_confirmation_key_locked_until,
            fields.Datetime.now(),
        )
        is_valid, error = (
            self.customer_contact._verify_portal_confirmation_key(
                "Compra-2026"
            )
        )
        self.assertFalse(is_valid)
        self.assertIn("bloqueada", error.lower())
