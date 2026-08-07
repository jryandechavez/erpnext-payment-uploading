frappe.pages["payment-upload"].on_page_load = (wrapper) => {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Payment Upload"), single_column: true });
	new PaymentUpload(page);
};

class PaymentUpload {
	constructor(page) {
		this.page = page;
		this.rows = [];
		this.make();
	}

	make() {
		this.$body = $(`<div class="payment-upload">
			<div class="frappe-card p-4 mb-4"><div class="row"></div></div>
			<div class="summary mb-3"></div><div class="preview"></div>
		</div>`).appendTo(this.page.main);
		const $row = this.$body.find(".row");
		this.company = this.control($row, "Company", "company", __("Company"), true);
		this.mode = this.control($row, "Link", "mode_of_payment", __("Mode of Payment"), true, "Mode of Payment");
		this.mode.set_value("Cheque");
		this.paid_to = this.control($row, "Link", "paid_to", __("Bank / Cash Account"), true, "Account", {
			get_query: () => ({ filters: { company: this.company.get_value(), is_group: 0, account_type: ["in", ["Bank", "Cash"]] } }),
		});
		this.ewt = this.control($row, "Link", "ewt_account", __("EWT Account"), false, "Account", {
			get_query: () => ({ filters: { company: this.company.get_value(), is_group: 0 } }),
		});
		this.file = this.control($row, "Attach", "payment_file", __("CSV / XLSX File"), true, null, {
			onchange: () => this.preview(),
		});
		this.create_button = this.page.add_inner_button(__("Create Draft Payment Entries"), () => this.confirm_create());
		this.create_button.addClass("btn-primary").prop("disabled", true);
	}

	control(parent, fieldtype, fieldname, label, reqd, options, extra = {}) {
		const $column = $('<div class="col-sm-6 col-lg-4"></div>').appendTo(parent);
		return frappe.ui.form.make_control({
			parent: $column,
			df: { fieldtype, fieldname, label, reqd: reqd ? 1 : 0, options, ...extra },
			render_input: true,
		});
	}

	async preview() {
		if (!this.file.get_value()) return;
		frappe.dom.freeze(__("Checking invoices and outstanding balances..."));
		try {
			const { message } = await frappe.call({
				method: "erpnext_payment_uploading.erpnext_payment_uploading.page.payment_upload.payment_upload.preview",
				args: { file_url: this.file.get_value() },
			});
			this.rows = message.rows;
			this.render(message.invalid_rows);
			this.create_button.prop("disabled", message.invalid_rows > 0 || !message.rows.length);
		} finally {
			frappe.dom.unfreeze();
		}
	}

	render(invalid) {
		const valid = this.rows.length - invalid;
		this.$body.find(".summary").html(
			`<span class="indicator blue">${this.rows.length} ${__("Rows")}</span>
			 <span class="indicator green">${valid} ${__("Ready")}</span>
			 <span class="indicator red">${invalid} ${__("Blocked")}</span>`
		);
		const esc = frappe.utils.escape_html;
		const rows = this.rows.map((r) => `<tr class="${r.status === "Invalid" ? "text-danger" : ""}">
			<td>${r.row_no}</td><td>${esc(r.cheque_no || "")}</td><td>${esc(r.cheque_date || "")}</td>
			<td>${esc(r.invoice_no || "")}</td><td>${esc(r.customer_name || r.customer || "")}</td>
			<td class="text-right">${format_currency(r.outstanding, r.currency)}</td>
			<td class="text-right">${format_currency(r.invoice_amount, r.currency)}</td>
			<td class="text-right">${format_currency(r.ewt_amount, r.currency)}</td>
			<td class="text-right">${format_currency(r.cheque_amount, r.currency)}</td>
			<td>${esc(r.status)}</td><td>${esc(r.message || "")}</td></tr>`).join("");
		this.$body.find(".preview").html(`<div class="table-responsive"><table class="table table-bordered table-hover">
			<thead><tr><th>${__("Row")}</th><th>${__("Cheque #")}</th><th>${__("Date")}</th><th>${__("Invoice #")}</th>
			<th>${__("Customer")}</th><th>${__("Outstanding")}</th><th>${__("Invoice Amount")}</th><th>${__("EWT")}</th>
			<th>${__("Cheque Amount")}</th><th>${__("Status")}</th><th>${__("Message")}</th></tr></thead><tbody>${rows}</tbody>
		</table></div>`);
	}

	confirm_create() {
		for (const field of [this.company, this.mode, this.paid_to, this.file]) {
			if (!field.get_value()) {
				frappe.msgprint(__("Please complete all required fields."));
				return;
			}
		}
		if (this.rows.some((row) => row.ewt_amount && !this.ewt.get_value())) {
			frappe.msgprint(__("Select an EWT Account before creating entries."));
			return;
		}
		frappe.confirm(__("Create one draft Payment Entry per cheque?"), async () => {
			const { message } = await frappe.call({
				method: "erpnext_payment_uploading.erpnext_payment_uploading.page.payment_upload.payment_upload.create_payment_entries",
				args: {
					rows: this.rows, company: this.company.get_value(), paid_to: this.paid_to.get_value(),
					mode_of_payment: this.mode.get_value(), ewt_account: this.ewt.get_value(),
				},
				freeze: true, freeze_message: __("Creating draft Payment Entries..."),
			});
			frappe.msgprint(__("Created {0} draft Payment Entries: {1}", [message.count, message.payment_entries.join(", ")]));
		});
	}
}
