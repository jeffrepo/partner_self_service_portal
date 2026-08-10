from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tools.float_utils import float_compare


class PortalOrderRequest(models.Model):
    _name = "partner.portal.order.request"
    _description = "Solicitud de compra desde el portal"
    _inherit = ["portal.mixin", "mail.thread", "mail.activity.mixin"]
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
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Compañía cliente",
        required=True,
        readonly=True,
        index=True,
        tracking=True,
    )
    requested_by_id = fields.Many2one(
        comodel_name="res.partner",
        string="Solicitado por",
        required=True,
        readonly=True,
        index=True,
        tracking=True,
    )
    warehouse_id = fields.Many2one(
        comodel_name="stock.warehouse",
        string="Almacén",
        required=True,
        readonly=True,
        check_company=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Compañía de Odoo",
        required=True,
        readonly=True,
        index=True,
    )
    currency_id = fields.Many2one(
        related="company_id.currency_id",
        readonly=True,
    )
    customer_reference = fields.Char(
        string="Proyecto",
        tracking=True,
    )
    note = fields.Text(string="Notas", tracking=True)
    state = fields.Selection(
        selection=[
            ("draft", "Borrador"),
            ("confirmed", "Confirmada"),
        ],
        string="Estado",
        required=True,
        default="draft",
        readonly=True,
        copy=False,
        index=True,
        tracking=True,
    )
    line_ids = fields.One2many(
        comodel_name="partner.portal.order.request.line",
        inverse_name="request_id",
        string="Productos",
        copy=True,
    )
    total_requested_qty = fields.Float(
        string="Cantidad total solicitada",
        compute="_compute_total_requested_qty",
    )
    confirmed_at = fields.Datetime(
        string="Fecha de confirmación",
        readonly=True,
        copy=False,
        tracking=True,
    )
    sale_order_id = fields.Many2one(
        comodel_name="sale.order",
        string="Orden de venta",
        readonly=True,
        copy=False,
        index=True,
        tracking=True,
    )

    _sql_constraints = [
        (
            "portal_order_request_name_uniq",
            "unique(name)",
            "El correlativo de la solicitud debe ser único.",
        ),
    ]

    @api.depends("line_ids.product_uom_qty")
    def _compute_total_requested_qty(self):
        for request_record in self:
            request_record.total_requested_qty = sum(
                request_record.line_ids.mapped("product_uom_qty")
            )

    @api.model_create_multi
    def create(self, vals_list):
        normalized_vals_list = []
        for values in vals_list:
            values = dict(values)
            partner = self.env["res.partner"].browse(values.get("partner_id")).exists()
            warehouse = self.env["stock.warehouse"].browse(
                values.get("warehouse_id")
            ).exists()
            requested_by = self.env["res.partner"].browse(
                values.get("requested_by_id")
            ).exists()

            if not partner or partner != partner.commercial_partner_id or not partner.is_company:
                raise ValidationError(_("La solicitud debe pertenecer a una compañía cliente."))
            if not requested_by or requested_by.commercial_partner_id != partner:
                raise ValidationError(
                    _("El solicitante debe ser un contacto de la compañía cliente.")
                )
            if not warehouse:
                raise ValidationError(_("La solicitud requiere un almacén válido."))

            values["company_id"] = warehouse.company_id.id
            if not values.get("name") or values["name"] == _("Nuevo"):
                values["name"] = self.env["ir.sequence"].next_by_code(
                    "partner.portal.order.request"
                ) or _("Nuevo")
            normalized_vals_list.append(values)
        return super().create(normalized_vals_list)

    @api.constrains("warehouse_id", "company_id")
    def _check_warehouse_company(self):
        for request_record in self:
            if request_record.warehouse_id.company_id != request_record.company_id:
                raise ValidationError(
                    _("El almacén y la compañía de Odoo deben coincidir.")
                )

    def _compute_access_url(self):
        super()._compute_access_url()
        for request_record in self:
            request_record.access_url = (
                f"/my/purchase-requests/{request_record.id}"
            )

    def action_open_sale_order(self):
        self.ensure_one()
        if not self.sale_order_id:
            raise UserError(_("La solicitud todavía no tiene una orden de venta."))
        return {
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "res_id": self.sale_order_id.id,
            "view_mode": "form",
        }

    def _check_stock_before_confirmation(self):
        self.ensure_one()
        if not self.line_ids:
            raise ValidationError(_("Agrega al menos un producto antes de confirmar."))

        available_by_product = self.warehouse_id._get_portal_available_quantities(
            self.line_ids.product_id.ids
        )
        for line in self.line_ids:
            available = available_by_product.get(line.product_id.id, 0.0)
            if float_compare(
                line.product_uom_qty,
                available,
                precision_rounding=line.product_uom_id.rounding,
            ) > 0:
                raise ValidationError(
                    _(
                        "El producto %(product)s ya no tiene inventario suficiente. "
                        "Disponible: %(available)s %(uom)s.",
                        product=line.product_id.display_name,
                        available=available,
                        uom=line.product_uom_id.name,
                    )
                )

    def _validate_sale_order_pickings(self, sale_order):
        """Reserve and validate every transfer generated by the portal sale."""
        self.ensure_one()
        validated_pickings = self.env["stock.picking"]
        if not sale_order.picking_ids:
            raise ValidationError(
                _(
                    "La orden %(order)s no generó ninguna transferencia de "
                    "inventario. Revisa las rutas de sus productos.",
                    order=sale_order.display_name,
                )
            )

        while True:
            pending_pickings = sale_order.picking_ids.sudo().filtered(
                lambda picking: picking.state not in ("done", "cancel")
            )
            if not pending_pickings:
                return validated_pickings

            made_progress = False
            for picking in pending_pickings.sorted("id"):
                if picking.state in (
                    "waiting",
                    "confirmed",
                    "partially_available",
                ):
                    picking.action_assign()
                if picking.state != "assigned":
                    continue

                incomplete_moves = picking.move_ids.filtered(
                    lambda move: move.state not in ("done", "cancel")
                    and float_compare(
                        move.quantity,
                        move.product_uom_qty,
                        precision_rounding=move.product_uom.rounding,
                    )
                    < 0
                )
                if incomplete_moves:
                    products = ", ".join(
                        incomplete_moves.product_id.mapped("display_name")
                    )
                    raise ValidationError(
                        _(
                            "No fue posible reservar completamente la transferencia "
                            "%(picking)s. Revisa las existencias de: %(products)s.",
                            picking=picking.display_name,
                            products=products,
                        )
                    )

                picking.with_context(skip_backorder=True).button_validate()
                if picking.state != "done":
                    raise ValidationError(
                        _(
                            "La transferencia %(picking)s requiere una operación "
                            "manual antes de poder validarse.",
                            picking=picking.display_name,
                        )
                    )
                validated_pickings |= picking
                made_progress = True

            if not made_progress:
                blocked_names = ", ".join(pending_pickings.mapped("display_name"))
                raise ValidationError(
                    _(
                        "No fue posible preparar las transferencias %(pickings)s. "
                        "Revisa la ruta y las reglas de abastecimiento del almacén.",
                        pickings=blocked_names,
                    )
                )

    def action_confirm(self):
        for request_record in self:
            self.env.cr.execute(
                "SELECT id FROM partner_portal_order_request "
                "WHERE id = %s FOR UPDATE",
                [request_record.id],
            )
            request_record.invalidate_recordset(["state", "sale_order_id"])
            if request_record.state != "draft":
                raise UserError(_("Solo las solicitudes en borrador pueden confirmarse."))

            # Serialize confirmations for the assigned warehouse. Stock rules still perform
            # their own quant locking when the sales order is confirmed.
            self.env.cr.execute(
                "SELECT id FROM stock_warehouse WHERE id = %s FOR UPDATE",
                [request_record.warehouse_id.id],
            )
            request_record._check_stock_before_confirmation()

            salesperson = request_record.partner_id.user_id
            if (
                salesperson
                and request_record.company_id not in salesperson.company_ids
            ):
                salesperson = self.env["res.users"]

            sale_order = (
                self.env["sale.order"]
                .sudo()
                .with_company(request_record.company_id)
                .create(
                    {
                        "partner_id": request_record.partner_id.id,
                        "company_id": request_record.company_id.id,
                        "warehouse_id": request_record.warehouse_id.id,
                        "user_id": salesperson.id or False,
                        "origin": request_record.name,
                        "client_order_ref": request_record.customer_reference
                        or request_record.name,
                        "portal_order_request_id": request_record.id,
                    }
                )
            )
            self.env["sale.order.line"].sudo().with_company(
                request_record.company_id
            ).create(
                [
                    {
                        "order_id": sale_order.id,
                        "product_id": line.product_id.id,
                        "name": line.product_id.get_product_multiline_description_sale(),
                        "product_uom_qty": line.product_uom_qty,
                        "product_uom": line.product_uom_id.id,
                    }
                    for line in request_record.line_ids
                ]
            )
            sale_order.action_confirm()
            validated_pickings = request_record._validate_sale_order_pickings(
                sale_order
            )
            request_record.sudo().write(
                {
                    "state": "confirmed",
                    "confirmed_at": fields.Datetime.now(),
                    "sale_order_id": sale_order.id,
                }
            )
            request_record._notify_confirmation(sale_order, validated_pickings)
        return True

    def _notify_confirmation(self, sale_order, validated_pickings):
        self.ensure_one()
        recipients = self.company_id.portal_notification_user_ids.filtered(
            lambda user: user.active and not user.share
        )
        body = Markup(
            "<p>La solicitud <strong>{request_name}</strong> fue confirmada desde el "
            "portal por {requested_by}.</p>"
            "<p>Se creó y confirmó la orden de venta "
            "<strong>{sale_order}</strong> usando el almacén {warehouse}.</p>"
            "<p>Transferencias validadas automáticamente: "
            "<strong>{pickings}</strong>.</p>"
        ).format(
            request_name=escape(self.name),
            requested_by=escape(self.requested_by_id.display_name),
            sale_order=escape(sale_order.name),
            warehouse=escape(self.warehouse_id.display_name),
            pickings=escape(", ".join(validated_pickings.mapped("name"))),
        )
        sale_order.message_post(
            body=body,
            author_id=self.requested_by_id.id,
            message_type="comment",
            subtype_xmlid="mail.mt_note",
        )
        email_recipients = recipients.filtered("partner_id.email")
        if email_recipients:
            self.env["mail.mail"].sudo().create(
                {
                    "subject": _(
                        "Solicitud %(request)s confirmada - Orden %(order)s",
                        request=self.name,
                        order=sale_order.name,
                    ),
                    "body_html": body,
                    "email_from": self.company_id.partner_id.email_formatted
                    or self.env.user.email_formatted,
                    "recipient_ids": [
                        Command.set(email_recipients.partner_id.ids)
                    ],
                    "author_id": self.requested_by_id.id,
                    "model": sale_order._name,
                    "res_id": sale_order.id,
                }
            )
        for user in recipients:
            sale_order.activity_schedule(
                "mail.mail_activity_data_todo",
                user_id=user.id,
                summary=_("Solicitud de portal confirmada: %s", self.name),
                note=body,
            )


class PortalOrderRequestLine(models.Model):
    _name = "partner.portal.order.request.line"
    _description = "Línea de solicitud de compra desde el portal"
    _order = "id"

    request_id = fields.Many2one(
        comodel_name="partner.portal.order.request",
        string="Solicitud",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(
        related="request_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    partner_id = fields.Many2one(
        related="request_id.partner_id",
        store=True,
        readonly=True,
        index=True,
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        string="Producto",
        required=True,
        ondelete="restrict",
        check_company=True,
    )
    product_uom_id = fields.Many2one(
        related="product_id.uom_id",
        string="Unidad de medida",
        readonly=True,
    )
    product_uom_qty = fields.Float(
        string="Cantidad",
        required=True,
        digits="Product Unit of Measure",
    )
    available_qty_at_request = fields.Float(
        string="Disponible al guardar",
        digits="Product Unit of Measure",
        readonly=True,
    )

    @api.constrains("product_id", "product_uom_qty")
    def _check_product_and_quantity(self):
        for line in self:
            if line.product_uom_qty <= 0:
                raise ValidationError(_("La cantidad solicitada debe ser mayor que cero."))
            if not line.product_id.sale_ok or not line.product_id.is_storable:
                raise ValidationError(
                    _("Solo se pueden solicitar productos almacenables y disponibles para venta.")
                )
            if line.request_id.state != "draft":
                raise ValidationError(
                    _("No se pueden modificar las líneas de una solicitud confirmada.")
                )
