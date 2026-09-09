from odoo.tests.common import TransactionCase, new_test_user


class PartnerSelfServicePortalCommon(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)],
            limit=1,
        )
        if not cls.warehouse:
            raise AssertionError("Inventory must provide a test warehouse")

        cls.customer_company = cls.env["res.partner"].create(
            {
                "name": "Portal Customer Company",
                "is_company": True,
                "portal_warehouse_id": cls.warehouse.id,
            }
        )
        cls.customer_contact = cls.env["res.partner"].create(
            {
                "name": "Portal Customer User",
                "email": "portal.customer@example.com",
                "parent_id": cls.customer_company.id,
                "portal_user_type": "office",
            }
        )
        cls.portal_user = new_test_user(
            cls.env,
            login="portal.customer@example.com",
            groups="base.group_portal",
            partner_id=cls.customer_contact.id,
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "Portal Stock Product",
                "is_storable": True,
                "sale_ok": True,
                "list_price": 25.0,
            }
        )
        cls.env["stock.quant"]._update_available_quantity(
            cls.product,
            cls.warehouse.lot_stock_id,
            10.0,
        )

    def _create_request(self, quantity=2.0, partner=None, requested_by=None):
        partner = partner or self.customer_company
        requested_by = requested_by or self.customer_contact
        return self.env["partner.portal.order.request"].create(
            {
                "partner_id": partner.id,
                "requested_by_id": requested_by.id,
                "warehouse_id": self.warehouse.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": quantity,
                            "available_qty_at_request": 10.0,
                        },
                    )
                ],
            }
        )
