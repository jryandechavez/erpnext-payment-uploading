import frappe


def execute():
    """Remove the superseded custom links; standard JE fields are used now."""
    for fieldname in (
        "custom_write_off_customer",
        "custom_write_off_sales_invoice",
    ):
        name = f"Journal Entry Account-{fieldname}"
        if frappe.db.exists("Custom Field", name):
            frappe.delete_doc(
                "Custom Field",
                name,
                force=True,
                ignore_permissions=True,
            )

    frappe.clear_cache(doctype="Journal Entry Account")
