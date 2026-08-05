from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    portal_order_request_id = fields.Many2one(
        comodel_name="partner.portal.order.request",
        string="Solicitud del portal",
        copy=False,
        readonly=True,
        index=True,
    )
    portal_payment_proof_ids = fields.One2many(
        comodel_name="partner.portal.payment.proof",
        inverse_name="sale_order_id",
        string="Comprobantes del portal",
    )
