# ERPNext Payment Uploading

Frappe/ERPNext v15 Desk Page for reviewing cheque allocations from CSV/XLSX before creating draft Payment Entries.

## Install

```bash
bench get-app git@github.com:jryandechavez/erpnext-payment-uploading.git
bench --site your-dev-site install-app erpnext_payment_uploading
bench build --app erpnext_payment_uploading
```

Open `/app/payment-upload`. The expected columns are `check #`, `check date`, `invoice #`, `invoice amount`, `ewt1%`, and `check amount`.

The page checks live Sales Invoice outstanding balances, enforces one customer per cheque, and creates draft Payment Entries only after review. Company, bank account, mode of payment, and EWT account are selected on the page.
