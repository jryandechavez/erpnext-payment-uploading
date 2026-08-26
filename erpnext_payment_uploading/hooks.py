app_name = "erpnext_payment_uploading"
app_title = "ERPNext Payment Uploading"
app_publisher = "Tic and Terry"
app_description = "Review cheque allocations and create ERPNext Payment Entries"
app_email = ""
app_license = "MIT"

required_apps = ["erpnext"]

# Keep the invoice-level write-off tag available on both fresh installs and
# upgrades. ``after_migrate`` handles existing production sites after pull +
# ``bench migrate``.
after_install = "erpnext_payment_uploading.setup.install.ensure_custom_fields"
after_migrate = "erpnext_payment_uploading.setup.install.ensure_custom_fields"
