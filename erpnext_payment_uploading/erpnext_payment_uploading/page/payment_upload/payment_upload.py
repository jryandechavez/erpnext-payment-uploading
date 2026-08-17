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
            fields=["name", "customer", "customer_name", "outstanding_amount", "currency", "docstatus", "debit_to"],
        )
    }
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
def create_journal_entries(rows, debits, company, posting_date, write_off_account=None):
    _require_create_permission()
    rows = frappe.parse_json(rows) if isinstance(rows, str) else rows
    debits = frappe.parse_json(debits) if isinstance(debits, str) else debits
    if not rows or not debits or not company or not posting_date:
        frappe.throw(_("Rows, debit entries, Company, and Posting Date are required."))

    input_rows = [frappe._dict(value) for value in rows]
    invoice_names = list({row.invoice_no for row in input_rows})
    all_invoices = {
        row.name: row
        for row in frappe.get_all(
            "Sales Invoice",
            filters={"name": ["in", invoice_names], "docstatus": 1, "company": company},
            fields=["name", "customer", "outstanding_amount", "currency", "debit_to"],
        )
    }
    if len(all_invoices) != len(invoice_names):
        frappe.throw(_("One or more invoices are missing, not submitted, or belong to another company."))

    company_currency = frappe.get_cached_value("Company", company, "default_currency")
    invoice_currencies = {invoice.currency for invoice in all_invoices.values()}
    if invoice_currencies != {company_currency}:
        frappe.throw(
            _("This uploader currently supports company-currency invoices only ({0}). Found: {1}").format(
                company_currency, ", ".join(sorted(invoice_currencies))
            )
        )

    account_names = {row.get("account") for row in debits if row.get("account")}
    account_names.update(invoice.debit_to for invoice in all_invoices.values())
    if write_off_account:
        account_names.add(write_off_account)
    account_currencies = {
        row.name: row.account_currency or company_currency
        for row in frappe.get_all(
            "Account",
            filters={"name": ["in", list(account_names)], "company": company, "is_group": 0},
            fields=["name", "account_currency"],
        )
    }
    if len(account_currencies) != len(account_names):
        frappe.throw(_("One or more selected accounts are invalid for company {0}.").format(company))
    foreign_accounts = [name for name, currency in account_currencies.items() if currency != company_currency]
    if foreign_accounts:
        frappe.throw(
            _("This uploader currently supports company-currency accounts only. Check: {0}").format(
                ", ".join(foreign_accounts)
            )
        )

    # Journal Entries are grouped by cheque. Each invoice credit uses the
    # exact customer and receivable account from its Sales Invoice.
    groups = OrderedDict()
    for row in sorted(
        input_rows,
        key=lambda value: (_clean_id(value.cheque_no), value.row_no or 0),
    ):
        groups.setdefault(_clean_id(row.cheque_no), []).append(row)

    debits_by_cheque = {}
    for raw_debit in debits:
        debit = frappe._dict(raw_debit)
        cheque_no = _clean_id(debit.cheque_no)
        amount = _decimal(debit.amount)
        if not cheque_no or not debit.account or amount <= 0:
            frappe.throw(_("Every debit row requires a cheque number, account, and positive amount."))
        debits_by_cheque.setdefault(cheque_no, []).append(debit)

    created = []
    for cheque_no, cheque_rows in groups.items():
        invoice_names = list({row.invoice_no for row in cheque_rows})
        invoices = {name: all_invoices[name] for name in invoice_names}

        invoice_total = Decimal("0")
        credit_by_invoice = OrderedDict()
        for row in cheque_rows:
            if row.invoice_no not in credit_by_invoice:
                outstanding = Decimal(str(invoices[row.invoice_no].outstanding_amount or 0))
                if outstanding <= 0:
                    frappe.throw(_("Cheque {0}: invoice {1} has no outstanding balance.").format(cheque_no, row.invoice_no))
                credit_by_invoice[row.invoice_no] = outstanding
                invoice_total += outstanding

        cheque_debits = debits_by_cheque.get(cheque_no, [])
        if not cheque_debits:
            frappe.throw(_("Cheque {0}: add at least one debit entry.").format(cheque_no))
        debit_total = sum((_decimal(row.amount) for row in cheque_debits), Decimal("0"))
        accounts = []
        for debit in cheque_debits:
            account_row = {
                "account": debit.account,
                "account_currency": company_currency,
                "exchange_rate": 1,
                "debit_in_account_currency": float(_decimal(debit.amount)),
                "user_remark": debit.get("remark") or _("Cheque {0}").format(cheque_no),
            }
            if debit.get("party_type") and debit.get("party"):
                account_row.update({"party_type": debit.party_type, "party": debit.party})
            accounts.append(account_row)

        for name, amount in credit_by_invoice.items():
            invoice = invoices[name]
            accounts.append(
                {
                    "account": invoice.debit_to,
                    "account_currency": company_currency,
                    "exchange_rate": 1,
                    "party_type": "Customer",
                    "party": invoice.customer,
                    "credit_in_account_currency": float(amount),
                    "reference_type": "Sales Invoice",
                    "reference_name": name,
                    "user_remark": _("Cheque {0}").format(cheque_no),
                }
            )

        difference = debit_total - invoice_total
        if abs(difference) > Decimal("0.005"):
            if not write_off_account:
                frappe.throw(
                    _("Cheque {0}: debit and invoice totals differ by {1}; select a Write-off Account.").format(
                        cheque_no, abs(difference)
                    )
                )
            write_off_row = {
                "account": write_off_account,
                "account_currency": company_currency,
                "exchange_rate": 1,
                "user_remark": _("Write-off for cheque {0}").format(cheque_no),
            }
            if difference > 0:
                write_off_row["credit_in_account_currency"] = float(difference)
            else:
                write_off_row["debit_in_account_currency"] = float(abs(difference))
            accounts.append(write_off_row)

        first = cheque_rows[0]
        remark_lines = [
            "\t".join(
                [
                    cheque_no,
                    _display_date(posting_date),
                    _display_date(row.cheque_date),
                    row.invoice_no,
                    "",
                    "{:,.2f}".format(Decimal(str(row.invoice_amount))),
                ]
            )
            for row in cheque_rows
        ]
        doc = frappe.get_doc(
            {
                "doctype": "Journal Entry",
                "voucher_type": "Bank Entry",
                "company": company,
                "posting_date": getdate(posting_date),
                "cheque_no": cheque_no,
                "cheque_date": getdate(first.cheque_date or nowdate()),
                "user_remark": "\n".join(remark_lines),
                "accounts": accounts,
            }
        )
        doc.insert()
        created.append(doc.name)
    return {"journal_entries": created, "count": len(created)}


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


def _display_date(value):
    value = getdate(value)
    return "{0}/{1}/{2}".format(value.month, value.day, value.year)


def _require_create_permission():
    if not frappe.has_permission("Journal Entry", "create"):
        frappe.throw(_("You do not have permission to create Journal Entries."), frappe.PermissionError)
