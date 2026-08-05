from odoo.tests import tagged

from .common import PartnerSelfServicePortalCommon


@tagged("post_install", "-at_install")
class TestPortalSecurity(PartnerSelfServicePortalCommon):
    def test_portal_rule_isolates_customer_companies(self):
        own_request = self._create_request()
        other_company = self.env["res.partner"].create(
            {
                "name": "Other Portal Company",
                "is_company": True,
                "portal_warehouse_id": self.warehouse.id,
            }
        )
        other_contact = self.env["res.partner"].create(
            {
                "name": "Other Portal Contact",
                "parent_id": other_company.id,
            }
        )
        other_request = self._create_request(
            partner=other_company,
            requested_by=other_contact,
        )

        visible_requests = self.env[
            "partner.portal.order.request"
        ].with_user(self.portal_user).search([])

        self.assertIn(own_request, visible_requests)
        self.assertNotIn(other_request, visible_requests)
