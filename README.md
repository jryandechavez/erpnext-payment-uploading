# ERPNext Cheque Journal Entry Uploading

Frappe/ERPNext v15 Desk Page for reviewing cheque allocations from CSV/XLSX before creating draft Journal Entries.

## Recommended installation

Run as a user with permission to manage the Bench (normally `root` on a production server):

```bash
curl -fsSL https://raw.githubusercontent.com/jryandechavez/erpnext-payment-uploading/codex/payment-upload/install.sh \
  -o /tmp/install-erpnext-payment-uploading.sh
sudo bash /tmp/install-erpnext-payment-uploading.sh your-site.example.com
```

The installer:

- backs up and normalizes `sites/apps.txt` before `bench get-app`;
- prevents concatenated or duplicate app names;
- skips the unnecessary asset build for this standard Desk Page;
- safely resumes a partially cloned installation;
- installs, migrates, clears cache, and restarts the Bench.

The default Bench path is `/home/frappe/frappe-bench`. Pass a different path as the second argument if necessary.

## Manual installation

```bash
sed -i -e '$a\' sites/apps.txt
bench get-app --skip-assets --branch codex/payment-upload https://github.com/jryandechavez/erpnext-payment-uploading.git
bench --site your-dev-site install-app erpnext_payment_uploading
bench --site your-dev-site migrate
bench --site your-dev-site clear-cache
bench restart
```

Open `/app/payment-upload`. The expected columns are `check #`, `check date`, `invoice #`, `invoice amount`, `ewt1%`, and `check amount`.

The page checks live Sales Invoice outstanding balances and creates one draft Journal Entry per cheque only after review. Users can add multiple debit rows per cheque, including accounts and optional parties. Each invoice is credited to its own receivable account and exact `Sales Invoice.customer`; any remaining balance is posted to the selected write-off account. The completed draft opens in ERPNext for final review and submission.

The Journal Entry header User Remark contains one tab-separated line per invoice: cheque number, posting date, cheque date, uploaded invoice number, a blank column, and invoice amount.

For the headerless `Sheet1` upload layout, only columns B (cheque number), D (Sales Invoice), and E (amount) are required. The page calculates G–J as `G = E × 1.01`, `H = G × 1%`, `I = G − H`, and `J = E − I`. It prefills one debit from column E and a second debit from calculated EWT (column H); users select the accounts and may add more debit rows.

The preview and validation use the exact `Sales Invoice.customer` value. `customer_name` is not used to group invoices because separate Customer records can share the same display name.
