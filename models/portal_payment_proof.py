from markupsafe import Markup, escape

from odoo import SUPERUSER_ID, _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command


class PortalPaymentProof(models.Model):
    _name = "partner.portal.payment.proof"
    _description = "Comprobante de pago enviado desde el portal"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc, id desc"

    name = fields.Char(
        string="Correlativo",
        required=True,
        readonly=True,
        copy=False,
        default=lambda self: _("Nuevo"),
        index=True,
        tracking=True,
    )
    sale_order_id = fields.Many2one(
        comodel_name="sale.order",
        string="Orden de venta",
        required=True,
        readonly=True,
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    sale_order_ids = fields.Many2many(
        comodel_name="sale.order",
        relation="portal_payment_proof_sale_order_rel",
        column1="proof_id",
        column2="sale_order_id",
        string="Órdenes de venta",
        readonly=True,
        copy=False,
    )
    invoice_ids = fields.Many2many(
        comodel_name="account.move",
        relation="portal_payment_proof_account_move_rel",
        column1="proof_id",
        column2="move_id",
        string="Facturas",
        readonly=True,
        copy=False,
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Compañía cliente",
        required=True,
        readonly=True,
        index=True,
    )
    uploaded_by_id = fields.Many2one(
        comodel_name="res.partner",
        string="Adjuntado por",
        required=True,
        readonly=True,
        index=True,
    )
    company_id = fields.Many2one(
        related="sale_order_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    currency_id = fields.Many2one(
        related="sale_order_id.currency_id",
        readonly=True,
    )
    amount = fields.Monetary(
        string="Monto reportado",
        required=True,
        tracking=True,
    )
    payment_date = fields.Date(
        string="Fecha del pago",
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    note = fields.Text(string="Notas", tracking=True)
    attachment_id = fields.Many2one(
        comodel_name="ir.attachment",
        string="Comprobante",
        required=True,
        readonly=True,
        ondelete="restrict",
    )
    state = fields.Selection(
        selection=[
            ("submitted", "Enviado"),
            ("reviewed", "Revisado"),
            ("rejected", "Rechazado"),
        ],
        string="Estado",
        default="submitted",
        required=True,
        readonly=True,
        copy=False,
        index=True,
        tracking=True,
    )

    _sql_constraints = [
        (
            "portal_payment_proof_name_uniq",
            "unique(name)",
            "El correlativo del comprobante debe ser único.",
        ),
        (
            "portal_payment_proof_amount_positive",
            "check(amount > 0)",
            "El monto reportado debe ser mayor que cero.",
        ),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        normalized_vals_list = []
        for values in vals_list:
            values = dict(values)
            sale_order = self.env["sale.order"].browse(
                values.get("sale_order_id")
            ).exists()
            partner = self.env["res.partner"].browse(values.get("partner_id")).exists()
            uploaded_by = self.env["res.partner"].browse(
                values.get("uploaded_by_id")
            ).exists()
            if not sale_order or sale_order.state != "sale":
                raise ValidationError(
                    _("Solo se aceptan comprobantes para órdenes de venta confirmadas.")
                )
            if not partner or partner != sale_order.partner_id.commercial_partner_id:
                raise ValidationError(_("La compañía no corresponde a la orden de venta."))
            if not uploaded_by or uploaded_by.commercial_partner_id != partner:
                raise ValidationError(
                    _("El usuario que adjunta el comprobante no pertenece a la compañía.")
                )
            if not values.get("name") or values["name"] == _("Nuevo"):
                values["name"] = self.env["ir.sequence"].next_by_code(
                    "partner.portal.payment.proof"
                ) or _("Nuevo")
            normalized_vals_list.append(values)
        proofs = super().create(normalized_vals_list)
        for proof in proofs:
            if proof.sale_order_id not in proof.sale_order_ids:
                proof.sudo().write(
                    {"sale_order_ids": [Command.link(proof.sale_order_id.id)]}
                )
            proof._validate_linked_documents()
        return proofs

    def _validate_linked_documents(self):
        for proof in self:
            sale_orders = proof.sale_order_ids | proof.sale_order_id
            if any(order.state != "sale" for order in sale_orders):
                raise ValidationError(
                    _("Todas las órdenes relacionadas deben estar confirmadas.")
                )
            if any(
                order.partner_id.commercial_partner_id != proof.partner_id
                for order in sale_orders
            ):
                raise ValidationError(
                    _("Todas las órdenes deben pertenecer a la misma compañía cliente.")
                )
            if any(
                order.company_id != proof.company_id
                or order.currency_id != proof.currency_id
                for order in sale_orders
            ):
                raise ValidationError(
                    _("Las órdenes relacionadas deben usar la misma compañía y moneda.")
                )
            for invoice in proof.invoice_ids:
                if invoice.state != "posted" or invoice.move_type != "out_invoice":
                    raise ValidationError(
                        _("Solo se pueden reportar pagos para facturas de cliente publicadas.")
                    )
                if invoice.partner_id.commercial_partner_id != proof.partner_id:
                    raise ValidationError(
                        _("Todas las facturas deben pertenecer a la misma compañía cliente.")
                    )
                linked_orders = invoice.invoice_line_ids.sale_line_ids.order_id
                if not linked_orders or not linked_orders & sale_orders:
                    raise ValidationError(
                        _("Una factura seleccionada no corresponde a las órdenes indicadas.")
                    )

    @api.constrains(
        "sale_order_id",
        "sale_order_ids",
        "invoice_ids",
        "partner_id",
    )
    def _check_linked_documents(self):
        self._validate_linked_documents()

    def action_mark_reviewed(self):
        self.write({"state": "reviewed"})
        return True

    def action_mark_rejected(self):
        self.write({"state": "rejected"})
        return True

    def action_download_attachment(self):
        self.ensure_one()
        if not self.attachment_id:
            raise UserError(_("El comprobante no tiene un archivo adjunto."))
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{self.attachment_id.id}?download=true",
            "target": "self",
        }

    def notify_internal_users(self):
        self.ensure_one()
        internal_users = self.company_id.portal_notification_user_ids.filtered(
            lambda user: user.active and not user.share
        )
        configured_external_partners = (
            self.company_id.portal_payment_notification_partner_ids.filtered(
                lambda partner: partner.active and partner.email
            )
        )
        partners_with_users = (
            self.env["res.users"]
            .sudo()
            .with_context(active_test=False)
            .search(
                [("partner_id", "in", configured_external_partners.ids)]
            )
            .partner_id
        )
        external_partners = configured_external_partners - partners_with_users
        sale_orders = self.sale_order_ids | self.sale_order_id
        sale_order_names = ", ".join(sale_orders.mapped("name"))
        invoice_names = ", ".join(self.invoice_ids.mapped("name"))
        invoice_paragraph = (
            Markup("<p>Facturas seleccionadas: <strong>{invoices}</strong>.</p>").format(
                invoices=escape(invoice_names)
            )
            if invoice_names
            else Markup("")
        )
        body = Markup(
            "<p>{uploaded_by} reportó un pago para las órdenes de venta "
            "<strong>{sale_orders}</strong>.</p>"
            "{invoice_paragraph}"
            "<p>Comprobante: <strong>{proof}</strong><br/>"
            "Monto reportado: <strong>{amount}</strong><br/>"
            "Fecha del pago: <strong>{payment_date}</strong><br/>"
            "Archivo adjunto: <strong>{attachment}</strong></p>"
        ).format(
            uploaded_by=escape(self.uploaded_by_id.display_name),
            sale_orders=escape(sale_order_names),
            invoice_paragraph=invoice_paragraph,
            proof=escape(self.name),
            amount=escape(f"{self.amount:.2f} {self.currency_id.name}"),
            payment_date=escape(fields.Date.to_string(self.payment_date)),
            attachment=escape(self.attachment_id.name),
        )
        for sale_order in sale_orders:
            sale_order.with_user(SUPERUSER_ID).message_post(
                body=body,
                author_id=self.uploaded_by_id.id,
                attachment_ids=self.attachment_id.ids,
                message_type="comment",
                subtype_xmlid="mail.mt_note",
            )
        email_recipient_partners = (
            internal_users.filtered("partner_id.email").partner_id
            | external_partners
        )
        if email_recipient_partners:
            outgoing_mail = self.env["mail.mail"].sudo().create(
                {
                    "subject": _(
                        "Comprobante %(proof)s - %(documents)s",
                        proof=self.name,
                        documents=invoice_names or sale_order_names,
                    ),
                    "body_html": body,
                    "email_from": self.company_id.partner_id.email_formatted
                    or self.env.user.email_formatted,
                    "recipient_ids": [
                        Command.set(email_recipient_partners.ids)
                    ],
                    "author_id": self.uploaded_by_id.id,
                    "model": self.sale_order_id._name,
                    "res_id": self.sale_order_id.id,
                }
            )
            email_attachment = self.attachment_id.sudo().copy(
                {
                    "res_model": "mail.message",
                    "res_id": outgoing_mail.mail_message_id.id,
                }
            )
            outgoing_mail.write(
                {"attachment_ids": [Command.link(email_attachment.id)]}
            )
        for user in internal_users:
            for sale_order in sale_orders:
                sale_order.activity_schedule(
                    "mail.mail_activity_data_todo",
                    user_id=user.id,
                    summary=_("Comprobante de pago: %s", sale_order.name),
                    note=body,
                )
        return True
