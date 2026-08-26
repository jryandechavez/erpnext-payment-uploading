import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def ensure_custom_fields():
    """Create the invoice link used by invoice-specific write-off rows."""
    create_custom_fields(
        {
            "Journal Entry Account": [
                {
                    "fieldname": "custom_write_off_customer",
                    "label": "Write-off Customer",
                    "fieldtype": "Link",
                    "options": "Customer",
                    "insert_after": "party",
                    "read_only": 1,
                    "in_list_view": 1,
                    "in_standard_filter": 1,
                    "description": "Customer associated with this write-off line.",
                },
                {
                    "fieldname": "custom_write_off_sales_invoice",
                    "label": "Write-off Sales Invoice",
                    "fieldtype": "Link",
                    "options": "Sales Invoice",
                    "insert_after": "reference_name",
                    "read_only": 1,
                    "in_list_view": 1,
                    "in_standard_filter": 1,
                    "description": "Sales Invoice associated with this write-off line.",
                }
            ]
        },
        update=True,
    )
    frappe.clear_cache(doctype="Journal Entry Account")
