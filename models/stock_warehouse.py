from odoo import models


class StockWarehouse(models.Model):
    _inherit = "stock.warehouse"

    def _get_portal_available_quantities(self, product_ids=None):
        """Return free quantities for saleable, company-owned stock in this warehouse."""
        self.ensure_one()
        domain = [
            ("location_id", "child_of", self.lot_stock_id.id),
            ("location_id.usage", "=", "internal"),
            ("company_id", "=", self.company_id.id),
            ("owner_id", "=", False),
            ("product_id.active", "=", True),
            ("product_id.sale_ok", "=", True),
            ("product_id.is_storable", "=", True),
        ]
        if product_ids is not None:
            domain.append(("product_id", "in", product_ids))

        grouped_quants = self.env["stock.quant"].sudo()._read_group(
            domain,
            ["product_id"],
            ["quantity:sum", "reserved_quantity:sum"],
        )
        return {
            product.id: quantity - reserved_quantity
            for product, quantity, reserved_quantity in grouped_quants
            if quantity - reserved_quantity > 0
        }
