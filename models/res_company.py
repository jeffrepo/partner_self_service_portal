from odoo import fields, models


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
