from odoo import api, fields, models


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
    portal_batch_payment_proof_ids = fields.Many2many(
        comodel_name="partner.portal.payment.proof",
        relation="portal_payment_proof_sale_order_rel",
        column1="sale_order_id",
        column2="proof_id",
        string="Comprobantes por lote del portal",
        readonly=True,
    )
    portal_all_payment_proof_ids = fields.Many2many(
        comodel_name="partner.portal.payment.proof",
        string="Todos los comprobantes del portal",
        compute="_compute_portal_all_payment_proof_ids",
    )

    @api.depends("portal_payment_proof_ids", "portal_batch_payment_proof_ids")
    def _compute_portal_all_payment_proof_ids(self):
        for order in self:
            order.portal_all_payment_proof_ids = (
                order.portal_payment_proof_ids
                | order.portal_batch_payment_proof_ids
            )
