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
        proof.with_user(self.portal_user).sudo().notify_internal_users()

        self.assertTrue(proof.name.startswith("CPP/"))
        self.assertEqual(proof.state, "submitted")
        self.assertEqual(proof.sale_order_ids, request_record.sale_order_id)
        self.assertEqual(
            self.env["account.payment"].search_count([]),
            payment_count_before,
        )
        queued_email = self.env["mail.mail"].search(
            [("subject", "ilike", proof.name)],
            limit=1,
        )
        self.assertTrue(queued_email)
        self.assertEqual(len(queued_email.attachment_ids), 1)
        email_attachment = queued_email.attachment_ids
        self.assertNotEqual(email_attachment, attachment)
        self.assertEqual(email_attachment.name, attachment.name)
        self.assertEqual(email_attachment.mimetype, attachment.mimetype)
        self.assertEqual(email_attachment.raw, attachment.raw)
        self.assertEqual(email_attachment.res_model, "mail.message")
        self.assertEqual(
            email_attachment.res_id,
            queued_email.mail_message_id.id,
        )
        prepared_email = queued_email._prepare_outgoing_list()[0]
        self.assertIn(
            (email_attachment.name, email_attachment.raw, email_attachment.mimetype),
            prepared_email["attachments"],
        )
        chatter_message = request_record.sale_order_id.message_ids.filtered(
            lambda message: attachment in message.attachment_ids
        )
        self.assertTrue(chatter_message)

    def test_one_proof_can_cover_multiple_invoices_and_orders(self):
        first_request = self._create_request(quantity=2.0)
        first_request.action_confirm()
        second_request = self._create_request(quantity=2.0)
        second_request.action_confirm()
        sale_orders = first_request.sale_order_id | second_request.sale_order_id
        invoices = self.env["account.move"]
        for sale_order in sale_orders:
            invoices |= sale_order._create_invoices()
        invoices.action_post()
        attachment = self.env["ir.attachment"].create(
            {
                "name": "batch-payment.pdf",
                "datas": base64.b64encode(b"%PDF-1.4 batch test"),
                "mimetype": "application/pdf",
                "res_model": "partner.portal.payment.proof",
                "res_id": 0,
            }
        )

        proof = self.env["partner.portal.payment.proof"].create(
            {
                "sale_order_id": sale_orders[0].id,
                "sale_order_ids": [(6, 0, sale_orders.ids)],
                "invoice_ids": [(6, 0, invoices.ids)],
                "partner_id": self.customer_company.id,
                "uploaded_by_id": self.customer_contact.id,
                "amount": sum(invoices.mapped("amount_residual")),
                "attachment_id": attachment.id,
            }
        )

        self.assertEqual(proof.sale_order_ids, sale_orders)
        self.assertEqual(proof.invoice_ids, invoices)
        self.assertEqual(len(invoices), 2)
        for sale_order in sale_orders:
            self.assertIn(proof, sale_order.portal_all_payment_proof_ids)
