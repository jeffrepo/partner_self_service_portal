import base64

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import new_test_user

from .common import PartnerSelfServicePortalCommon


@tagged("post_install", "-at_install")
class TestPortalPaymentProof(PartnerSelfServicePortalCommon):
    def test_paid_sale_order_is_not_eligible_for_another_proof(self):
        request_record = self._create_request()
        request_record.action_confirm()
        sale_order = request_record.sale_order_id

        self.assertEqual(
            sale_order.portal_invoice_payment_state,
            "not_invoiced",
        )
        self.assertTrue(sale_order._is_portal_payment_proof_eligible())

        invoice = sale_order._create_invoices()
        invoice.action_post()
        self.assertEqual(sale_order.portal_invoice_payment_state, "pending")
        self.assertTrue(sale_order._is_portal_payment_proof_eligible())

        journal = self.env["account.journal"].search(
            [
                ("company_id", "=", self.env.company.id),
                ("type", "in", ("bank", "cash")),
            ],
            limit=1,
        )
        self.assertTrue(journal)
        payment_method_line = journal.inbound_payment_method_line_ids[:1]
        self.assertTrue(payment_method_line)
        payment = self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": self.customer_company.id,
                "amount": invoice.amount_residual,
                "currency_id": invoice.currency_id.id,
                "date": fields.Date.today(),
                "journal_id": journal.id,
                "payment_method_line_id": payment_method_line.id,
            }
        )
        payment.action_post()
        receivable_lines = (invoice.line_ids | payment.move_id.line_ids).filtered(
            lambda line: (
                line.account_id.account_type == "asset_receivable"
                and not line.reconciled
            )
        )
        receivable_lines.reconcile()

        self.assertTrue(invoice.currency_id.is_zero(invoice.amount_residual))
        self.assertEqual(sale_order.portal_invoice_payment_state, "paid")
        self.assertFalse(sale_order._is_portal_payment_proof_eligible())

    def test_proof_does_not_create_account_payment(self):
        recipient = new_test_user(
            self.env,
            login="payment.notification@example.com",
            groups="account.group_account_invoice",
            company_id=self.env.company.id,
        )
        self.env.company.portal_notification_user_ids = recipient
        external_recipient = self.env["res.partner"].create(
            {
                "name": "External Payment Recipient",
                "email": "external.payment@example.com",
            }
        )
        self.env.company.portal_payment_notification_partner_ids = (
            external_recipient
        )
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
        self.assertIn(recipient.partner_id, queued_email.recipient_ids)
        self.assertIn(external_recipient, queued_email.recipient_ids)
        self.assertIn(request_record.sale_order_id.name, queued_email.body_html)
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

    def test_external_payment_recipient_cannot_have_an_odoo_user(self):
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.env.company.portal_payment_notification_partner_ids = (
                self.customer_contact
            )

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
