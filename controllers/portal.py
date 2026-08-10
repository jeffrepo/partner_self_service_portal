import base64
import math

from werkzeug.utils import secure_filename

from odoo import _, fields, http
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.http import content_disposition, request
from odoo.addons.portal.controllers.portal import (
    CustomerPortal,
    pager as portal_pager,
)
from odoo.tools.float_utils import float_compare
from odoo.tools.mimetypes import guess_mimetype


MAX_PAYMENT_PROOF_SIZE = 10 * 1024 * 1024
ALLOWED_PAYMENT_PROOF_MIMETYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
}


class PartnerSelfServicePortal(CustomerPortal):
    def _get_customer_company_partner(self):
        partner = request.env.user.partner_id
        commercial_partner = partner.commercial_partner_id
        if (
            not partner.parent_id
            or commercial_partner == partner
            or not commercial_partner.is_company
        ):
            return request.env["res.partner"]
        return commercial_partner

    def _get_customer_portal_context(self):
        partner = request.env.user.partner_id
        company_partner = self._get_customer_company_partner()
        warehouse = (
            company_partner.sudo().portal_warehouse_id
            if company_partner
            else request.env["stock.warehouse"]
        )
        if warehouse and not warehouse.active:
            warehouse = request.env["stock.warehouse"]
        return {
            "contact_partner": partner,
            "company_partner": company_partner,
            "warehouse": warehouse,
        }

    def _get_request_domain(self, company_partner):
        return [("partner_id", "=", company_partner.id)]

    def _get_payment_domain(self, company_partner):
        return [
            ("partner_id", "child_of", company_partner.id),
            ("partner_type", "=", "customer"),
            ("payment_type", "=", "inbound"),
            ("state", "in", ("in_process", "paid")),
        ]

    def _inventory_items(self, warehouse, search=None):
        available_by_product = warehouse.sudo()._get_portal_available_quantities()
        products = request.env["product.product"].sudo().browse(
            available_by_product.keys()
        )
        if search:
            normalized_search = search.strip().lower()
            products = products.filtered(
                lambda product: normalized_search
                in " ".join(
                    filter(
                        None,
                        [product.default_code, product.name, product.barcode],
                    )
                ).lower()
            )
        products = products.sorted(
            key=lambda product: (
                (product.default_code or "").lower(),
                product.display_name.lower(),
            )
        )
        return [
            {
                "product": product,
                "available": available_by_product[product.id],
            }
            for product in products
        ]

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        portal_context = self._get_customer_portal_context()
        company_partner = portal_context["company_partner"]
        warehouse = portal_context["warehouse"]

        # This module is loaded after Sale and Accounting. Keep their standard
        # counters available even though the controller extension starts from
        # portal.CustomerPortal.
        sale_order_model = request.env["sale.order"]
        if "quotation_count" in counters:
            values["quotation_count"] = (
                sale_order_model.search_count(
                    [
                        (
                            "message_partner_ids",
                            "child_of",
                            [request.env.user.partner_id.commercial_partner_id.id],
                        ),
                        ("state", "=", "sent"),
                    ]
                )
                if sale_order_model.has_access("read")
                else 0
            )
        if "order_count" in counters:
            values["order_count"] = (
                sale_order_model.search_count(
                    [
                        (
                            "message_partner_ids",
                            "child_of",
                            [request.env.user.partner_id.commercial_partner_id.id],
                        ),
                        ("state", "=", "sale"),
                    ],
                    limit=1,
                )
                if sale_order_model.has_access("read")
                else 0
            )
        account_move_model = request.env["account.move"]
        if "invoice_count" in counters:
            values["invoice_count"] = (
                account_move_model.search_count(
                    [
                        ("state", "not in", ("cancel", "draft")),
                        (
                            "move_type",
                            "in",
                            ("out_invoice", "out_refund", "out_receipt"),
                        ),
                    ],
                    limit=1,
                )
                if account_move_model.has_access("read")
                else 0
            )
        if "bill_count" in counters:
            values["bill_count"] = (
                account_move_model.search_count(
                    [
                        ("state", "not in", ("cancel", "draft")),
                        (
                            "move_type",
                            "in",
                            ("in_invoice", "in_refund", "in_receipt"),
                        ),
                    ],
                    limit=1,
                )
                if account_move_model.has_access("read")
                else 0
            )

        if "purchase_request_count" in counters:
            values["purchase_request_count"] = (
                request.env["partner.portal.order.request"]
                .sudo()
                .search_count(self._get_request_domain(company_partner))
                if company_partner
                else 0
            )
        if "portal_payment_count" in counters:
            values["portal_payment_count"] = (
                request.env["account.payment"]
                .sudo()
                .search_count(self._get_payment_domain(company_partner))
                if company_partner
                else 0
            )
        if "portal_inventory_count" in counters:
            values["portal_inventory_count"] = (
                len(warehouse.sudo()._get_portal_available_quantities())
                if warehouse
                else 0
            )
        return values

    def _base_page_values(self, page_name, portal_context=None):
        portal_context = portal_context or self._get_customer_portal_context()
        values = self._prepare_portal_layout_values()
        values.update(portal_context)
        values["page_name"] = page_name
        return values

    @http.route(
        ["/my/inventory", "/my/inventory/page/<int:page>"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_inventory(self, page=1, search=None, **kwargs):
        portal_context = self._get_customer_portal_context()
        values = self._base_page_values("portal_inventory", portal_context)
        warehouse = portal_context["warehouse"]
        if not portal_context["company_partner"] or not warehouse:
            return request.render(
                "partner_self_service_portal.portal_configuration_required",
                values,
            )

        inventory_items = self._inventory_items(warehouse, search=search)
        pager = portal_pager(
            url="/my/inventory",
            total=len(inventory_items),
            page=page,
            step=self._items_per_page,
            url_args={"search": search} if search else None,
        )
        start = pager["offset"]
        values.update(
            {
                "inventory_items": inventory_items[
                    start : start + self._items_per_page
                ],
                "pager": pager,
                "search": search or "",
            }
        )
        return request.render(
            "partner_self_service_portal.portal_my_inventory",
            values,
        )

    @http.route(
        ["/my/payments", "/my/payments/page/<int:page>"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_payments(self, page=1, **kwargs):
        portal_context = self._get_customer_portal_context()
        values = self._base_page_values("portal_payments", portal_context)
        company_partner = portal_context["company_partner"]
        if not company_partner:
            return request.render(
                "partner_self_service_portal.portal_configuration_required",
                values,
            )

        payment_model = request.env["account.payment"].sudo()
        domain = self._get_payment_domain(company_partner)
        pager = portal_pager(
            url="/my/payments",
            total=payment_model.search_count(domain),
            page=page,
            step=self._items_per_page,
        )
        payments = payment_model.search(
            domain,
            order="date desc, id desc",
            limit=self._items_per_page,
            offset=pager["offset"],
        )
        values.update({"payments": payments, "pager": pager})
        return request.render(
            "partner_self_service_portal.portal_my_payments",
            values,
        )

    @http.route(
        [
            "/my/purchase-requests",
            "/my/purchase-requests/page/<int:page>",
        ],
        type="http",
        auth="user",
        website=True,
    )
    def portal_purchase_requests(self, page=1, **kwargs):
        portal_context = self._get_customer_portal_context()
        values = self._base_page_values("portal_purchase_requests", portal_context)
        company_partner = portal_context["company_partner"]
        if not company_partner:
            return request.render(
                "partner_self_service_portal.portal_configuration_required",
                values,
            )

        request_model = request.env["partner.portal.order.request"].sudo()
        domain = self._get_request_domain(company_partner)
        pager = portal_pager(
            url="/my/purchase-requests",
            total=request_model.search_count(domain),
            page=page,
            step=self._items_per_page,
        )
        request_records = request_model.search(
            domain,
            order="create_date desc, id desc",
            limit=self._items_per_page,
            offset=pager["offset"],
        )
        request.session["my_purchase_requests_history"] = request_records.ids[:100]
        values.update(
            {
                "purchase_requests": request_records,
                "pager": pager,
            }
        )
        return request.render(
            "partner_self_service_portal.portal_my_purchase_requests",
            values,
        )

    def _get_portal_request(self, request_id, company_partner):
        if not company_partner:
            return request.env["partner.portal.order.request"]
        return (
            request.env["partner.portal.order.request"]
            .sudo()
            .search(
                [
                    ("id", "=", request_id),
                    ("partner_id", "=", company_partner.id),
                ],
                limit=1,
            )
        )

    @http.route(
        "/my/purchase-requests/<int:request_id>",
        type="http",
        auth="user",
        website=True,
    )
    def portal_purchase_request_detail(self, request_id, **kwargs):
        portal_context = self._get_customer_portal_context()
        request_record = self._get_portal_request(
            request_id, portal_context["company_partner"]
        )
        if not request_record:
            return request.redirect("/my/purchase-requests")
        values = self._base_page_values("portal_purchase_request", portal_context)
        values.update(
            {
                "purchase_request": request_record,
                "created": kwargs.get("created"),
                "confirmed": kwargs.get("confirmed"),
            }
        )
        return request.render(
            "partner_self_service_portal.portal_purchase_request_detail",
            values,
        )

    def _render_purchase_request_confirmation_error(
        self, portal_context, request_record, error_message
    ):
        values = self._base_page_values("portal_purchase_request", portal_context)
        values.update(
            {
                "purchase_request": request_record,
                "confirmation_error": error_message,
            }
        )
        return request.render(
            "partner_self_service_portal.portal_purchase_request_detail",
            values,
        )

    @http.route(
        "/my/purchase-requests/<int:request_id>/report",
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
    )
    def portal_purchase_request_report(self, request_id, **kwargs):
        portal_context = self._get_customer_portal_context()
        request_record = self._get_portal_request(
            request_id, portal_context["company_partner"]
        )
        if not request_record:
            return request.redirect("/my/purchase-requests")
        pdf_content, _content_type = (
            request.env["ir.actions.report"]
            .sudo()
            ._render_qweb_pdf(
                "partner_self_service_portal.action_report_portal_order_request",
                res_ids=request_record.ids,
            )
        )
        filename = f"{request_record.name.replace('/', '-')}.pdf"
        return request.make_response(
            pdf_content,
            headers=[
                ("Content-Type", "application/pdf"),
                ("Content-Disposition", content_disposition(filename)),
            ],
        )

    @staticmethod
    def _parse_quantity(raw_value):
        if raw_value in (None, ""):
            return 0.0
        parsed_value = float(str(raw_value).strip().replace(",", "."))
        if not math.isfinite(parsed_value):
            raise ValueError("Non-finite quantity")
        return parsed_value

    def _prepare_request_lines(self, warehouse, post):
        available_by_product = warehouse.sudo()._get_portal_available_quantities()
        lines = []
        errors = []
        for field_name, raw_value in post.items():
            if not field_name.startswith("qty_"):
                continue
            try:
                product_id = int(field_name[4:])
                quantity = self._parse_quantity(raw_value)
            except (TypeError, ValueError):
                errors.append(_("Se encontró una cantidad inválida."))
                continue
            if quantity <= 0:
                continue
            available = available_by_product.get(product_id, 0.0)
            product = request.env["product.product"].sudo().browse(product_id).exists()
            if not product or not available:
                errors.append(_("Uno de los productos ya no está disponible."))
                continue
            if float_compare(
                quantity,
                available,
                precision_rounding=product.uom_id.rounding,
            ) > 0:
                errors.append(
                    _(
                        "%(product)s: solicitaste %(requested)s, pero solo hay "
                        "%(available)s disponibles.",
                        product=product.display_name,
                        requested=quantity,
                        available=available,
                    )
                )
                continue
            lines.append(
                Command.create(
                    {
                        "product_id": product.id,
                        "product_uom_qty": quantity,
                        "available_qty_at_request": available,
                    }
                )
            )
        if not lines and not errors:
            errors.append(_("Selecciona al menos un producto y una cantidad mayor que cero."))
        return lines, errors

    def _request_form_values(
        self,
        portal_context,
        request_record=None,
        post=None,
        errors=None,
    ):
        values = self._base_page_values("portal_purchase_request_form", portal_context)
        warehouse = portal_context["warehouse"]
        current_quantities = {
            line.product_id.id: line.product_uom_qty
            for line in request_record.line_ids
        } if request_record else {}
        if post:
            for field_name, raw_value in post.items():
                if field_name.startswith("qty_"):
                    try:
                        current_quantities[int(field_name[4:])] = raw_value
                    except ValueError:
                        continue
        values.update(
            {
                "inventory_items": self._inventory_items(warehouse),
                "purchase_request": request_record,
                "current_quantities": current_quantities,
                "form_reference": (post or {}).get(
                    "customer_reference",
                    request_record.customer_reference if request_record else "",
                ),
                "form_note": (post or {}).get(
                    "note",
                    request_record.note if request_record else "",
                ),
                "errors": errors or [],
            }
        )
        return values

    @http.route(
        "/my/purchase-requests/new",
        type="http",
        auth="user",
        website=True,
        methods=["GET", "POST"],
    )
    def portal_purchase_request_new(self, **post):
        portal_context = self._get_customer_portal_context()
        company_partner = portal_context["company_partner"]
        warehouse = portal_context["warehouse"]
        if not company_partner or not warehouse:
            values = self._base_page_values(
                "portal_purchase_request_form", portal_context
            )
            return request.render(
                "partner_self_service_portal.portal_configuration_required",
                values,
            )

        if request.httprequest.method == "POST":
            lines, errors = self._prepare_request_lines(warehouse, post)
            if not errors:
                with request.env.cr.savepoint():
                    request_record = (
                        request.env["partner.portal.order.request"]
                        .sudo()
                        .create(
                            {
                                "partner_id": company_partner.id,
                                "requested_by_id": request.env.user.partner_id.id,
                                "warehouse_id": warehouse.id,
                                "customer_reference": post.get(
                                    "customer_reference", ""
                                )[:128],
                                "note": post.get("note", "")[:2000],
                                "line_ids": lines,
                            }
                        )
                    )
                return request.redirect(
                    f"/my/purchase-requests/{request_record.id}?created=1"
                )
            values = self._request_form_values(
                portal_context,
                post=post,
                errors=errors,
            )
        else:
            values = self._request_form_values(portal_context)
        return request.render(
            "partner_self_service_portal.portal_purchase_request_form",
            values,
        )

    @http.route(
        "/my/purchase-requests/<int:request_id>/edit",
        type="http",
        auth="user",
        website=True,
        methods=["GET", "POST"],
    )
    def portal_purchase_request_edit(self, request_id, **post):
        portal_context = self._get_customer_portal_context()
        request_record = self._get_portal_request(
            request_id, portal_context["company_partner"]
        )
        if not request_record or request_record.state != "draft":
            return request.redirect("/my/purchase-requests")

        if request.httprequest.method == "POST":
            lines, errors = self._prepare_request_lines(
                request_record.warehouse_id, post
            )
            if not errors:
                with request.env.cr.savepoint():
                    request_record.write(
                        {
                            "customer_reference": post.get(
                                "customer_reference", ""
                            )[:128],
                            "note": post.get("note", "")[:2000],
                            "line_ids": [Command.clear(), *lines],
                        }
                    )
                return request.redirect(
                    f"/my/purchase-requests/{request_record.id}"
                )
            values = self._request_form_values(
                portal_context,
                request_record=request_record,
                post=post,
                errors=errors,
            )
        else:
            values = self._request_form_values(
                portal_context,
                request_record=request_record,
            )
        return request.render(
            "partner_self_service_portal.portal_purchase_request_form",
            values,
        )

    @http.route(
        "/my/purchase-requests/<int:request_id>/confirm",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
    )
    def portal_purchase_request_confirm(self, request_id, **post):
        portal_context = self._get_customer_portal_context()
        request_record = self._get_portal_request(
            request_id, portal_context["company_partner"]
        )
        if not request_record:
            return request.redirect("/my/purchase-requests")
        if request_record.state != "draft":
            return request.redirect(
                f"/my/purchase-requests/{request_record.id}"
            )

        key_is_valid, key_error = (
            request.env.user.partner_id.sudo()._verify_portal_confirmation_key(
                post.get("confirmation_key")
            )
        )
        if not key_is_valid:
            return self._render_purchase_request_confirmation_error(
                portal_context,
                request_record,
                key_error,
            )

        try:
            with request.env.cr.savepoint():
                request_record.action_confirm()
        except (UserError, ValidationError) as error:
            return self._render_purchase_request_confirmation_error(
                portal_context,
                request_record,
                error.args[0],
            )
        return request.redirect(
            f"/my/purchase-requests/{request_record.id}?confirmed=1"
        )

    def _get_portal_sale_order(self, order_id, company_partner):
        if not company_partner:
            return request.env["sale.order"]
        return (
            request.env["sale.order"]
            .sudo()
            .search(
                [
                    ("id", "=", order_id),
                    ("partner_id", "child_of", company_partner.id),
                    ("state", "=", "sale"),
                ],
                limit=1,
            )
        )

    def _prepare_payment_proof_upload(self, post):
        uploaded_file = request.httprequest.files.get("payment_proof")
        if not uploaded_file or not uploaded_file.filename:
            return False, "missing"
        content = uploaded_file.read(MAX_PAYMENT_PROOF_SIZE + 1)
        if len(content) > MAX_PAYMENT_PROOF_SIZE:
            return False, "size"
        mimetype = guess_mimetype(
            content,
            default=uploaded_file.mimetype or "application/octet-stream",
        )
        if mimetype not in ALLOWED_PAYMENT_PROOF_MIMETYPES:
            return False, "type"
        try:
            amount = self._parse_quantity(post.get("amount"))
            payment_date = fields.Date.to_date(post.get("payment_date"))
        except (TypeError, ValueError):
            return False, "data"
        if amount <= 0 or not payment_date:
            return False, "data"
        return {
            "content": content,
            "filename": secure_filename(uploaded_file.filename) or "comprobante",
            "mimetype": mimetype,
            "amount": amount,
            "payment_date": payment_date,
            "note": post.get("note", "")[:2000],
        }, False

    def _create_portal_payment_proof(
        self,
        company_partner,
        sale_orders,
        upload_values,
        invoices=None,
    ):
        invoices = invoices or request.env["account.move"]
        with request.env.cr.savepoint():
            attachment = request.env["ir.attachment"].sudo().create(
                {
                    "name": upload_values["filename"],
                    "datas": base64.b64encode(upload_values["content"]),
                    "mimetype": upload_values["mimetype"],
                    "res_model": "partner.portal.payment.proof",
                    "res_id": 0,
                }
            )
            proof = request.env["partner.portal.payment.proof"].sudo().create(
                {
                    "sale_order_id": sale_orders[0].id,
                    "sale_order_ids": [Command.set(sale_orders.ids)],
                    "invoice_ids": [Command.set(invoices.ids)],
                    "partner_id": company_partner.id,
                    "uploaded_by_id": request.env.user.partner_id.id,
                    "amount": upload_values["amount"],
                    "payment_date": upload_values["payment_date"],
                    "note": upload_values["note"],
                    "attachment_id": attachment.id,
                }
            )
            attachment.write({"res_id": proof.id})
            attachment._post_add_create()
            proof.notify_internal_users()
        return proof

    @http.route(
        "/my/orders/<int:order_id>/payment-proof",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
    )
    def portal_order_payment_proof(self, order_id, **post):
        company_partner = self._get_customer_company_partner()
        sale_order = self._get_portal_sale_order(order_id, company_partner)
        if not sale_order:
            return request.redirect("/my/orders")

        upload_values, error_code = self._prepare_payment_proof_upload(post)
        if error_code:
            return request.redirect(
                f"{sale_order.get_portal_url()}?proof_error={error_code}"
            )
        self._create_portal_payment_proof(
            company_partner,
            sale_order,
            upload_values,
        )
        return request.redirect(
            f"{sale_order.get_portal_url()}?proof_submitted=1"
        )

    @http.route(
        "/my/invoices/payment-proof",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
    )
    def portal_invoice_batch_payment_proof(self, **post):
        company_partner = self._get_customer_company_partner()
        if not company_partner:
            return request.redirect("/my/invoices?batch_proof_error=access")
        try:
            invoice_ids = list(
                dict.fromkeys(
                    int(invoice_id)
                    for invoice_id in request.httprequest.form.getlist("invoice_ids")
                )
            )
        except (TypeError, ValueError):
            invoice_ids = []
        if not invoice_ids or len(invoice_ids) > 100:
            return request.redirect("/my/invoices?batch_proof_error=selection")

        invoices = request.env["account.move"].sudo().search(
            [
                ("id", "in", invoice_ids),
                ("partner_id", "child_of", company_partner.id),
                ("state", "=", "posted"),
                ("move_type", "=", "out_invoice"),
                ("amount_residual", "!=", 0),
            ]
        )
        if len(invoices) != len(invoice_ids):
            return request.redirect("/my/invoices?batch_proof_error=selection")

        sale_orders = invoices.invoice_line_ids.sale_line_ids.order_id.filtered(
            lambda order: order.state == "sale"
        )
        if not sale_orders or any(
            not invoice.invoice_line_ids.sale_line_ids.order_id & sale_orders
            for invoice in invoices
        ):
            return request.redirect("/my/invoices?batch_proof_error=orders")
        if len(sale_orders.company_id) != 1 or len(sale_orders.currency_id) != 1:
            return request.redirect("/my/invoices?batch_proof_error=currency")
        if any(
            invoice.company_id != sale_orders.company_id
            or invoice.currency_id != sale_orders.currency_id
            for invoice in invoices
        ):
            return request.redirect("/my/invoices?batch_proof_error=currency")

        upload_values, error_code = self._prepare_payment_proof_upload(post)
        if error_code:
            return request.redirect(
                f"/my/invoices?batch_proof_error={error_code}"
            )
        self._create_portal_payment_proof(
            company_partner,
            sale_orders,
            upload_values,
            invoices=invoices,
        )
        return request.redirect("/my/invoices?batch_proof_submitted=1")
