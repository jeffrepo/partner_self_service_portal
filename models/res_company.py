from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = "res.company"

    portal_notification_user_ids = fields.Many2many(
        comodel_name="res.users",
        relation="res_company_portal_notification_user_rel",
        column1="company_id",
        column2="user_id",
        string="Usuarios a notificar desde el portal",
        domain="[('share', '=', False), ('active', '=', True)]",
        help=(
            "Usuarios internos que recibirán correo y una actividad cuando un cliente "
            "confirme una solicitud o adjunte un comprobante de pago."
        ),
    )
    portal_payment_notification_partner_ids = fields.Many2many(
        comodel_name="res.partner",
        relation="res_company_portal_payment_notification_partner_rel",
        column1="company_id",
        column2="partner_id",
        string="Contactos externos para comprobantes del portal",
        domain=[
            ("active", "=", True),
            ("email", "!=", False),
            ("type", "=", "contact"),
            ("user_ids", "=", False),
        ],
        help=(
            "Contactos sin usuario de Odoo que recibirán por correo los "
            "comprobantes de pago enviados desde el portal."
        ),
    )

    @api.constrains("portal_payment_notification_partner_ids")
    def _check_portal_payment_notification_partners(self):
        for company in self:
            partners = company.portal_payment_notification_partner_ids
            if any(not partner.email for partner in partners):
                raise ValidationError(
                    _("Todos los contactos de notificación deben tener correo electrónico.")
                )
            linked_users = (
                self.env["res.users"]
                .sudo()
                .with_context(active_test=False)
                .search([("partner_id", "in", partners.ids)], limit=1)
            )
            if linked_users:
                raise ValidationError(
                    _(
                        "Los destinatarios externos no pueden estar vinculados a "
                        "usuarios de Odoo."
                    )
                )
