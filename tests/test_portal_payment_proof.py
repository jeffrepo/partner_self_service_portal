import base64

from odoo.tests import tagged
from odoo.tests.common import new_test_user

from .common import PartnerSelfServicePortalCommon


@tagged("post_install", "-at_install")
class TestPortalPaymentProof(PartnerSelfServicePortalCommon):
    def test_proof_does_not_create_account_payment(self):
        recipient = new_test_user(
            self.env,
            login="payment.notification@example.com",
            groups="account.group_account_invoice",
            company_id=self.env.company.id,
        )
        self.env.company.portal_notification_user_ids = recipient
        request_record = self._create_request()
        request_record.action_confirm()
        payment_count_before = self.env["account.payment"].search_count([])
        attachment = self.env["ir.attachment"].create(
            {
                "name": "payment-proof.pdf",
                "datas": base64.b64encode(b"%PDF-1.4 test"),
                "mimetype": "application/pdf",
                "res_model": "partner.portal.payment.proof",
                "res_id": 0,
            }
        )

        proof = self.env["partner.portal.payment.proof"].create(
            {
                "sale_order_id": request_record.sale_order_id.id,
                "partner_id": self.customer_company.id,
                "uploaded_by_id": self.customer_contact.id,
                "amount": 50.0,
                "attachment_id": attachment.id,
            }
        )
        attachment.res_id = proof.id
        proof.notify_internal_users()

        self.assertTrue(proof.name.startswith("CPP/"))
        self.assertEqual(proof.state, "submitted")
        self.assertEqual(
            self.env["account.payment"].search_count([]),
            payment_count_before,
        )
        queued_email = self.env["mail.mail"].search(
            [("subject", "ilike", proof.name)],
            limit=1,
        )
        self.assertTrue(queued_email)
        self.assertIn(attachment, queued_email.attachment_ids)
