import base64
import hashlib
import hmac
import secrets
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


PORTAL_CONFIRMATION_KEY_ITERATIONS = 600_000
PORTAL_CONFIRMATION_KEY_MAX_ATTEMPTS = 5
PORTAL_CONFIRMATION_KEY_LOCK_MINUTES = 15


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
    portal_confirmation_key_hash = fields.Char(
        string="Hash de la clave de confirmación del portal",
        copy=False,
        groups="base.group_system",
    )
    portal_confirmation_key_configured = fields.Boolean(
        string="Clave de confirmación configurada",
        compute="_compute_portal_confirmation_key_configured",
        compute_sudo=True,
    )
    portal_confirmation_key_failed_attempts = fields.Integer(
        string="Intentos fallidos de la clave del portal",
        copy=False,
        default=0,
        groups="base.group_system",
    )
    portal_confirmation_key_locked_until = fields.Datetime(
        string="Clave del portal bloqueada hasta",
        copy=False,
        groups="base.group_system",
    )

    @api.depends("portal_confirmation_key_hash")
    def _compute_portal_confirmation_key_configured(self):
        for partner in self:
            partner.portal_confirmation_key_configured = bool(
                partner.sudo().portal_confirmation_key_hash
            )

    @api.model
    def _hash_portal_confirmation_key(self, confirmation_key):
        confirmation_key = (confirmation_key or "").strip()
        if len(confirmation_key) < 6:
            raise ValidationError(
                _("La clave de confirmación debe tener al menos 6 caracteres.")
            )
        if len(confirmation_key) > 128:
            raise ValidationError(
                _("La clave de confirmación no puede superar 128 caracteres.")
            )
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            confirmation_key.encode("utf-8"),
            salt,
            PORTAL_CONFIRMATION_KEY_ITERATIONS,
        )
        return "$".join(
            (
                "pbkdf2_sha256",
                str(PORTAL_CONFIRMATION_KEY_ITERATIONS),
                base64.b64encode(salt).decode("ascii"),
                base64.b64encode(digest).decode("ascii"),
            )
        )

    @api.model
    def _portal_confirmation_key_matches(self, confirmation_key, encoded_key):
        try:
            algorithm, iterations, salt, expected_digest = encoded_key.split("$", 3)
            if (
                algorithm != "pbkdf2_sha256"
                or int(iterations) != PORTAL_CONFIRMATION_KEY_ITERATIONS
            ):
                return False
            salt_bytes = base64.b64decode(salt, validate=True)
            expected_bytes = base64.b64decode(expected_digest, validate=True)
            actual_digest = hashlib.pbkdf2_hmac(
                "sha256",
                (confirmation_key or "").strip().encode("utf-8"),
                salt_bytes,
                PORTAL_CONFIRMATION_KEY_ITERATIONS,
            )
        except (TypeError, ValueError):
            return False
        return hmac.compare_digest(actual_digest, expected_bytes)

    def _set_portal_confirmation_key(self, confirmation_key):
        for partner in self:
            partner.sudo().write(
                {
                    "portal_confirmation_key_hash": self._hash_portal_confirmation_key(
                        confirmation_key
                    ),
                    "portal_confirmation_key_failed_attempts": 0,
                    "portal_confirmation_key_locked_until": False,
                }
            )
        return True

    def _verify_portal_confirmation_key(self, confirmation_key):
        """Check the contact key and persist rate limiting outside confirmation savepoints."""
        self.ensure_one()
        partner = self.sudo()
        self.env.cr.execute(
            "SELECT id FROM res_partner WHERE id = %s FOR UPDATE",
            [partner.id],
        )
        partner.invalidate_recordset(
            [
                "portal_confirmation_key_hash",
                "portal_confirmation_key_failed_attempts",
                "portal_confirmation_key_locked_until",
            ]
        )
        now = fields.Datetime.now()
        if (
            partner.portal_confirmation_key_locked_until
            and partner.portal_confirmation_key_locked_until > now
        ):
            return False, _(
                "La clave está bloqueada temporalmente por varios intentos "
                "incorrectos. Intenta de nuevo más tarde."
            )
        if (
            partner.portal_confirmation_key_locked_until
            and partner.portal_confirmation_key_locked_until <= now
        ):
            partner.write(
                {
                    "portal_confirmation_key_failed_attempts": 0,
                    "portal_confirmation_key_locked_until": False,
                }
            )
        if not partner.portal_confirmation_key_hash:
            return False, _(
                "Tu contacto todavía no tiene una clave de confirmación. "
                "Solicita a un usuario interno que la configure."
            )
        if self._portal_confirmation_key_matches(
            confirmation_key,
            partner.portal_confirmation_key_hash,
        ):
            partner.write(
                {
                    "portal_confirmation_key_failed_attempts": 0,
                    "portal_confirmation_key_locked_until": False,
                }
            )
            return True, False

        attempts = partner.portal_confirmation_key_failed_attempts + 1
        values = {"portal_confirmation_key_failed_attempts": attempts}
        if attempts >= PORTAL_CONFIRMATION_KEY_MAX_ATTEMPTS:
            values["portal_confirmation_key_locked_until"] = now + timedelta(
                minutes=PORTAL_CONFIRMATION_KEY_LOCK_MINUTES
            )
        partner.write(values)
        if attempts >= PORTAL_CONFIRMATION_KEY_MAX_ATTEMPTS:
            return False, _(
                "La clave es incorrecta y quedó bloqueada durante 15 minutos."
            )
        return False, _("La clave de confirmación es incorrecta.")

    def action_open_portal_confirmation_key_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Configurar clave de confirmación"),
            "res_model": "partner.portal.confirmation.key.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_partner_id": self.id},
        }

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
