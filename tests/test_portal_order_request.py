from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import new_test_user

from .common import PartnerSelfServicePortalCommon


@tagged("post_install", "-at_install")
class TestPortalOrderRequest(PartnerSelfServicePortalCommon):
    def test_confirmation_creates_confirmed_sale_from_assigned_warehouse(self):
        request_record = self._create_request(quantity=2.0)

        request_record.action_confirm()

        self.assertEqual(request_record.state, "confirmed")
        self.assertTrue(request_record.name.startswith("SPR/"))
        self.assertTrue(request_record.sale_order_id)
        self.assertEqual(request_record.sale_order_id.state, "sale")
        self.assertEqual(request_record.sale_order_id.partner_id, self.customer_company)
        self.assertEqual(request_record.sale_order_id.warehouse_id, self.warehouse)
        self.assertEqual(
            request_record.sale_order_id.portal_order_request_id,
            request_record,
        )
        self.assertEqual(
            request_record.sale_order_id.order_line.product_uom_qty,
            2.0,
        )
        self.assertTrue(request_record.sale_order_id.picking_ids)
        self.assertFalse(
            request_record.sale_order_id.picking_ids.filtered(
                lambda picking: picking.state != "done"
            )
        )
        available = self.warehouse._get_portal_available_quantities(
            self.product.ids
        )
        self.assertEqual(available[self.product.id], 8.0)

    def test_confirmation_rejects_insufficient_inventory(self):
        request_record = self._create_request(quantity=11.0)

        with self.assertRaises(ValidationError):
            request_record.action_confirm()

        self.assertEqual(request_record.state, "draft")
        self.assertFalse(request_record.sale_order_id)

    def test_confirmation_queues_email_for_configured_users(self):
        recipient = new_test_user(
            self.env,
            login="portal.notification@example.com",
            groups="sales_team.group_sale_salesman",
            company_id=self.env.company.id,
        )
        self.env.company.portal_notification_user_ids = recipient
        request_record = self._create_request()

        request_record.action_confirm()

        queued_email = self.env["mail.mail"].search(
            [("subject", "ilike", request_record.name)],
            limit=1,
        )
        self.assertTrue(queued_email)
        self.assertIn(recipient.partner_id, queued_email.recipient_ids)
