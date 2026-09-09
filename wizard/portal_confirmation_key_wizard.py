from odoo import _, fields, models
from odoo.exceptions import ValidationError


class PortalConfirmationKeyWizard(models.TransientModel):
    _name = "partner.portal.confirmation.key.wizard"
    _description = "Configurar clave de confirmación del portal"

    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Contacto",
        required=True,
        readonly=True,
    )
    confirmation_key = fields.Char(
        string="Nueva clave",
        required=True,
        size=128,
        copy=False,
    )
    confirmation_key_repeat = fields.Char(
        string="Confirmar clave",
        required=True,
        size=128,
        copy=False,
    )

    def action_set_confirmation_key(self):
        self.ensure_one()
        if self.partner_id.is_company:
            raise ValidationError(
                _("La clave debe configurarse en el contacto que utiliza el portal.")
            )
        if self.confirmation_key != self.confirmation_key_repeat:
            raise ValidationError(_("Las claves ingresadas no coinciden."))
        partner = self.partner_id
        confirmation_key = self.confirmation_key
        partner._set_portal_confirmation_key(confirmation_key)
        self.unlink()
        return {"type": "ir.actions.act_window_close"}
