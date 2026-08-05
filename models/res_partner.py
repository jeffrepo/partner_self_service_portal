from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = "res.partner"

    portal_warehouse_id = fields.Many2one(
        comodel_name="stock.warehouse",
        string="Almacén del portal",
        help=(
            "Almacén cuyo inventario podrán consultar y solicitar los usuarios de portal "
            "asociados a contactos de esta compañía."
        ),
    )

    @api.constrains("portal_warehouse_id", "is_company")
    def _check_portal_warehouse_company_partner(self):
        for partner in self:
            if partner.portal_warehouse_id and not partner.is_company:
                raise ValidationError(
                    _(
                        "El almacén del portal solo puede asignarse a un "
                        "contacto de tipo compañía."
                    )
                )
