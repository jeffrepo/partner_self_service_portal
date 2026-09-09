/** @odoo-module **/

function setupSaleOrderBatchActions() {
    const orderCheckboxes = Array.from(
        document.querySelectorAll(".o_portal_batch_order")
    );
    const selectAll = document.getElementById("portalOrderSelectAll");
    const paymentButton = document.getElementById("portalOrderBatchPaymentButton");
    const statementButton = document.getElementById("portalOrderStatementButton");
    const paymentForm = document.getElementById("portalOrderBatchPaymentForm");
    const amountInput = document.getElementById("portal_order_batch_payment_amount");

    if (!paymentButton && !statementButton) {
        return;
    }
    if (!orderCheckboxes.length) {
        if (selectAll) {
            selectAll.disabled = true;
        }
        return;
    }

    const getSelected = () => orderCheckboxes.filter((checkbox) => checkbox.checked);
    const updateSelection = () => {
        const selected = getSelected();
        if (paymentButton) {
            paymentButton.disabled = !selected.length;
        }
        if (statementButton) {
            statementButton.disabled = !selected.length;
        }
        if (selectAll) {
            selectAll.checked = selected.length === orderCheckboxes.length;
            selectAll.indeterminate = Boolean(
                selected.length && selected.length < orderCheckboxes.length
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

    for (const checkbox of orderCheckboxes) {
        checkbox.addEventListener("change", updateSelection);
    }
    if (selectAll) {
        selectAll.addEventListener("change", () => {
            for (const checkbox of orderCheckboxes) {
                checkbox.checked = selectAll.checked;
            }
            updateSelection();
        });
    }
    if (paymentForm) {
        paymentForm.addEventListener("submit", () => {
            for (const previousInput of paymentForm.querySelectorAll(
                ".o_portal_selected_order_id"
            )) {
                previousInput.remove();
            }
            for (const checkbox of getSelected()) {
                const input = document.createElement("input");
                input.type = "hidden";
                input.name = "order_ids";
                input.value = checkbox.value;
                input.className = "o_portal_selected_order_id";
                paymentForm.appendChild(input);
            }
        });
    }
    updateSelection();
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setupSaleOrderBatchActions);
} else {
    setupSaleOrderBatchActions();
}
