# ERPNext Payment Uploading

Frappe/ERPNext v15 Desk Page for reviewing cheque allocations from CSV/XLSX before creating draft Payment Entries.

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

The page checks live Sales Invoice outstanding balances and creates draft Payment Entries only after review. Rows are grouped first by `Sales Invoice.customer`, then by cheque number, so a reused cheque number under different customers creates separate drafts. Company, bank account, mode of payment, and EWT account are selected on the page.

The preview and validation use the exact `Sales Invoice.customer` value. `customer_name` is not used to group invoices because separate Customer records can share the same display name.
