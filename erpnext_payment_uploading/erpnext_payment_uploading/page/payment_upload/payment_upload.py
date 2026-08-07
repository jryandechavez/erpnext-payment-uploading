import csv
import io
from collections import OrderedDict
from decimal import Decimal, InvalidOperation

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate


@frappe.whitelist()
def preview(file_url):
    _require_create_permission()
    rows = _read_rows(file_url)
    if not rows:
        frappe.throw(_("The uploaded file has no payment rows."))

    names = list({row.invoice_no for row in rows if row.invoice_no})
    invoices = {
        row.name: row
        for row in frappe.get_all(
            "Sales Invoice",
            filters={"name": ["in", names]},
            fields=["name", "customer", "customer_name", "outstanding_amount", "currency", "docstatus"],
        )
    }
    uploaded_by_invoice = {}
    for row in rows:
        uploaded_by_invoice[row.invoice_no] = uploaded_by_invoice.get(row.invoice_no, Decimal("0")) + row.invoice_amount

    result = []
    for row in rows:
        invoice = invoices.get(row.invoice_no)
        errors, warnings = [], []
        if not row.cheque_no:
            errors.append(_("Check # is required"))
        if not row.invoice_no:
            errors.append(_("Invoice # is required"))
        elif not invoice:
            errors.append(_("Sales Invoice was not found"))
        elif invoice.docstatus != 1:
            errors.append(_("Sales Invoice is not submitted"))
        elif flt(invoice.outstanding_amount) <= 0:
            errors.append(_("Sales Invoice has no outstanding balance"))
        if invoice and uploaded_by_invoice[row.invoice_no] > Decimal(str(invoice.outstanding_amount or 0)):
            errors.append(_("Uploaded invoice amount exceeds the current outstanding balance"))
        if abs(row.invoice_amount - row.ewt_amount - row.cheque_amount) > Decimal("0.02"):
            errors.append(_("Check amount does not equal invoice amount less EWT"))
        if invoice and abs(row.invoice_amount - Decimal(str(invoice.outstanding_amount or 0))) > Decimal("0.02"):
            warnings.append(_("Uploaded amount differs from current outstanding"))

        result.append(
            {
                **row,
                "invoice_amount": float(row.invoice_amount),
                "ewt_amount": float(row.ewt_amount),
                "cheque_amount": float(row.cheque_amount),
                "customer": invoice.customer if invoice else None,
                "customer_name": invoice.customer_name if invoice else None,
                "currency": invoice.currency if invoice else None,
                "outstanding": flt(invoice.outstanding_amount) if invoice else 0,
                "status": "Invalid" if errors else ("Warning" if warnings else "Valid"),
                "message": "; ".join(errors + warnings),
            }
        )
    result.sort(key=lambda row: (row.get("customer") or "", row.get("cheque_no") or "", row.get("row_no") or 0))
    return {"rows": result, "invalid_rows": sum(r["status"] == "Invalid" for r in result)}


@frappe.whitelist()
def create_payment_entries(rows, company, paid_to, mode_of_payment="Cheque", ewt_account=None):
    _require_create_permission()
    rows = frappe.parse_json(rows) if isinstance(rows, str) else rows
    if not rows or not company or not paid_to:
        frappe.throw(_("Rows, Company, and Bank Account are required."))

    input_rows = [frappe._dict(value) for value in rows]
    invoice_names = list({row.invoice_no for row in input_rows})
    all_invoices = {
        row.name: row
        for row in frappe.get_all(
            "Sales Invoice",
            filters={"name": ["in", invoice_names], "docstatus": 1, "company": company},
            fields=["name", "customer", "outstanding_amount", "currency"],
        )
    }
    if len(all_invoices) != len(invoice_names):
        frappe.throw(_("One or more invoices are missing, not submitted, or belong to another company."))

    # Customer is always resolved from Sales Invoice. The hierarchy is
    # Customer -> Cheque # -> invoice allocations.
    groups = OrderedDict()
    for row in sorted(
        input_rows,
        key=lambda value: (all_invoices[value.invoice_no].customer, _clean_id(value.cheque_no), value.row_no or 0),
    ):
        key = (all_invoices[row.invoice_no].customer, _clean_id(row.cheque_no))
        groups.setdefault(key, []).append(row)

    created = []
    for (customer, cheque_no), cheque_rows in groups.items():
        invoice_names = list({row.invoice_no for row in cheque_rows})
        invoices = {name: all_invoices[name] for name in invoice_names}

        allocations, gross, net, ewt = [], Decimal("0"), Decimal("0"), Decimal("0")
        by_invoice = {}
        for row in cheque_rows:
            amount = Decimal(str(row.invoice_amount))
            by_invoice[row.invoice_no] = by_invoice.get(row.invoice_no, Decimal("0")) + amount
            gross += amount
            net += Decimal(str(row.cheque_amount))
            ewt += Decimal(str(row.ewt_amount))
        for name, amount in by_invoice.items():
            if amount <= 0 or amount > Decimal(str(invoices[name].outstanding_amount or 0)):
                frappe.throw(_("Cheque {0}: invalid allocation for {1}.").format(cheque_no, name))
            allocations.append({"reference_doctype": "Sales Invoice", "reference_name": name, "allocated_amount": float(amount)})
        if ewt and not ewt_account:
            frappe.throw(_("Cheque {0}: an EWT Account is required.").format(cheque_no))

        first = cheque_rows[0]
        doc = frappe.get_doc(
            {
                "doctype": "Payment Entry",
                "payment_type": "Receive",
                "company": company,
                "party_type": "Customer",
                "party": customer,
                "posting_date": getdate(first.get("posting_date") or nowdate()),
                "mode_of_payment": mode_of_payment or "Cheque",
                "reference_no": cheque_no,
                "reference_date": getdate(first.cheque_date or nowdate()),
                "paid_to": paid_to,
                "paid_amount": float(gross),
                "received_amount": float(net),
                "references": allocations,
                "deductions": ([{"account": ewt_account, "cost_center": frappe.get_cached_value("Company", company, "cost_center"), "amount": float(ewt)}] if ewt else []),
            }
        )
        doc.set_missing_values()
        doc.insert()
        created.append(doc.name)
    return {"payment_entries": created, "count": len(created)}


def _read_rows(file_url):
    file_doc = frappe.get_doc("File", {"file_url": file_url})
    content = file_doc.get_content()
    filename = (file_doc.file_name or file_url).lower()
    if filename.endswith(".csv"):
        text = content.decode("utf-8-sig") if isinstance(content, bytes) else content
        raw = list(csv.DictReader(io.StringIO(text)))
    elif filename.endswith(".xlsx"):
        from openpyxl import load_workbook

        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        sheet = workbook["july 24 2026"] if "july 24 2026" in workbook.sheetnames else workbook.active
        values = list(sheet.iter_rows(values_only=True))
        header_index = next((i for i, values_row in enumerate(values) if "invoice #" in {_header(v) for v in values_row}), None)
        if header_index is None:
            frappe.throw(_("Could not find a row containing the Invoice # header."))
        headers = [str(v or "") for v in values[header_index]]
        raw = [dict(zip(headers, values_row)) for values_row in values[header_index + 1 :] if any(v not in (None, "") for v in values_row)]
    else:
        frappe.throw(_("Please upload a CSV or XLSX file."))

    rows = []
    for index, source in enumerate(raw, start=2):
        value = {_header(k): v for k, v in source.items()}
        try:
            invoice_amount = _decimal(value.get("invoice amount"))
            ewt_amount = _decimal(value.get("ewt1%") or value.get("ewt 1%"))
            cheque_amount = _decimal(value.get("check amount") or value.get("cheque amount"))
        except InvalidOperation:
            frappe.throw(_("Row {0} contains an invalid monetary amount.").format(index))
        rows.append(
            frappe._dict(
                row_no=index,
                cheque_no=_clean_id(value.get("check #") or value.get("cheque #")),
                cheque_date=str(getdate(value.get("check date") or value.get("cheque date"))) if value.get("check date") or value.get("cheque date") else None,
                invoice_no=_clean_id(value.get("invoice #")),
                invoice_amount=invoice_amount,
                ewt_amount=ewt_amount,
                cheque_amount=cheque_amount,
            )
        )
    return rows


def _header(value):
    return " ".join(str(value or "").strip().lower().split())


def _clean_id(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).replace("\u00a0", " ").strip()


def _decimal(value):
    return Decimal(str(value or 0).replace(",", ""))


def _require_create_permission():
    if not frappe.has_permission("Payment Entry", "create"):
        frappe.throw(_("You do not have permission to create Payment Entries."), frappe.PermissionError)
