/** @odoo-module **/

function setupInvoiceBatchPayment() {
    const invoiceCheckboxes = Array.from(
        document.querySelectorAll(".o_portal_batch_invoice")
    );
    const selectAll = document.getElementById("portalBatchPaymentSelectAll");
    const paymentButton = document.getElementById("portalBatchPaymentButton");
    const amountInput = document.getElementById("portal_batch_payment_amount");

    if (!paymentButton) {
        return;
    }
    if (!invoiceCheckboxes.length) {
        if (selectAll) {
            selectAll.disabled = true;
        }
        return;
    }

    const updateSelection = () => {
        const selected = invoiceCheckboxes.filter((checkbox) => checkbox.checked);
        paymentButton.disabled = !selected.length;
        if (selectAll) {
            selectAll.checked = selected.length === invoiceCheckboxes.length;
            selectAll.indeterminate = Boolean(
                selected.length && selected.length < invoiceCheckboxes.length
            );
        }
        if (amountInput) {
            const total = selected.reduce(
                (sum, checkbox) => sum + Number(checkbox.dataset.amount || 0),
                0
            );
            amountInput.value = total ? total.toFixed(2) : "";
        }
    };

    for (const checkbox of invoiceCheckboxes) {
        checkbox.addEventListener("change", updateSelection);
    }
    if (selectAll) {
        selectAll.addEventListener("change", () => {
            for (const checkbox of invoiceCheckboxes) {
                checkbox.checked = selectAll.checked;
            }
            updateSelection();
        });
    }
    updateSelection();
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setupInvoiceBatchPayment);
} else {
    setupInvoiceBatchPayment();
}
