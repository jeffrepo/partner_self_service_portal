from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    portal_notification_user_ids = fields.Many2many(
        related="company_id.portal_notification_user_ids",
        readonly=False,
        string="Usuarios a notificar desde el portal",
    )
    portal_payment_notification_partner_ids = fields.Many2many(
        related="company_id.portal_payment_notification_partner_ids",
        readonly=False,
        string="Contactos externos para comprobantes del portal",
    )
