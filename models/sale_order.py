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
    portal_project_name = fields.Char(
        related="portal_order_request_id.customer_reference",
        string="Proyecto",
        store=True,
        readonly=True,
    )
    portal_requested_by_id = fields.Many2one(
        related="portal_order_request_id.requested_by_id",
        string="Solicitado por",
        store=True,
        readonly=True,
    )
    portal_requested_by_name = fields.Char(
        related="portal_order_request_id.requested_by_id.name",
        string="Solicitado por",
        store=True,
        readonly=True,
    )
    portal_authorized_by_id = fields.Many2one(
        related="portal_order_request_id.authorized_by_id",
        string="Autorizado por",
        store=True,
        readonly=True,
    )
    portal_authorized_by_name = fields.Char(
        related="portal_order_request_id.authorized_by_id.name",
        string="Autorizado por",
        store=True,
        readonly=True,
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
    portal_invoice_payment_state = fields.Selection(
        selection=[
            ("not_invoiced", "Sin factura"),
            ("pending", "Pendiente"),
            ("paid", "Pagada"),
        ],
        string="Estado de pago",
        compute="_compute_portal_invoice_payment_state",
    )

    @api.depends("portal_payment_proof_ids", "portal_batch_payment_proof_ids")
    def _compute_portal_all_payment_proof_ids(self):
        for order in self:
            order.portal_all_payment_proof_ids = (
                order.portal_payment_proof_ids
                | order.portal_batch_payment_proof_ids
            )

    @api.depends(
        "invoice_ids.move_type",
        "invoice_ids.state",
        "invoice_ids.amount_residual",
        "invoice_ids.currency_id",
    )
    def _compute_portal_invoice_payment_state(self):
        for order in self:
            customer_invoices = order.invoice_ids.filtered(
                lambda invoice: (
                    invoice.move_type == "out_invoice"
                    and invoice.state != "cancel"
                )
            )
            if not customer_invoices:
                order.portal_invoice_payment_state = "not_invoiced"
            elif all(
                invoice.currency_id.is_zero(invoice.amount_residual)
                for invoice in customer_invoices
            ):
                order.portal_invoice_payment_state = "paid"
            else:
                order.portal_invoice_payment_state = "pending"

    def _is_portal_payment_proof_eligible(self):
        self.ensure_one()
        return (
            self.state == "sale"
            and self.portal_invoice_payment_state != "paid"
        )
