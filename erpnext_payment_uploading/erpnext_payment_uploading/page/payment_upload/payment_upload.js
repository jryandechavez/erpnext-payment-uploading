frappe.pages["payment-upload"].on_page_load = (wrapper) => {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Cheque Journal Entry Upload"), single_column: true });
	new PaymentUpload(page);
};

class PaymentUpload {
	constructor(page) {
		this.page = page;
		this.rows = [];
		this.debit_rows = [];
		this.make();
	}

	make() {
		this.$body = $(`<div class="payment-upload">
			<div class="frappe-card p-4 mb-4"><div class="row"></div></div>
			<div class="summary mb-3"></div><div class="preview"></div>
			<div class="debit-section mt-4"></div>
		</div>`).appendTo(this.page.main);
		const $row = this.$body.find(".row");
		this.company = this.control($row, "Link", "company", __("Company"), true, "Company");
		this.posting_date = this.control($row, "Date", "posting_date", __("Posting Date"), true);
		this.posting_date.set_value(frappe.datetime.get_today());
		this.ewt_account = this.control($row, "Link", "ewt_account", __("EWT Account"), true, "Account", {
			get_query: () => ({ filters: { company: this.company.get_value(), is_group: 0 } }),
			onchange: () => this.update_balance_state(),
		});
		this.write_off = this.control($row, "Link", "write_off_account", __("Write-off Account"), false, "Account", {
			get_query: () => ({ filters: { company: this.company.get_value(), is_group: 0 } }),
			onchange: () => this.update_balance_state(),
		});
		this.file = this.control($row, "Attach", "payment_file", __("CSV / XLSX File"), true, null, {
			onchange: () => this.preview(),
		});
		this.create_button = this.page.add_inner_button(__("Create Journal Entries"), () => this.confirm_create());
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
			this.sync_debit_rows();
			this.render(message.invalid_rows);
			this.update_balance_state(message.invalid_rows);
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
		const rows = this.rows.map((r) => `<tr class="${r.status === "Invalid" ? "text-danger" : ""}" title="${esc(r.message || "")}">
			<td>${esc(r.customer || "")}</td><td>${esc(r.invoice_no || "")}</td><td>${esc(r.cheque_no || "")}</td>
			<td class="text-right">${format_currency(r.invoice_amount, r.currency)}</td>
			<td class="text-right">${format_currency(r.ewt_amount, r.currency)}</td>
			<td class="text-right">${format_currency(r.outstanding, r.currency)}</td>
			<td class="text-right">${format_currency(r.write_off_amount, r.currency)}</td></tr>`).join("");
		const issues = this.rows.filter((r) => r.message).map((r) =>
			`<li class="${r.status === "Invalid" ? "text-danger" : "text-warning"}">${esc(r.invoice_no)}: ${esc(r.message)}</li>`
		).join("");
		this.$body.find(".preview").html(`<div class="table-responsive"><table class="table table-bordered table-hover">
			<thead><tr><th>${__("Customer")}</th><th>${__("Sales Invoice No")}</th><th>${__("Customer Ref No")}</th>
			<th>${__("Paid Amount")}</th><th>${__("EWT")}</th><th>${__("Outstanding")}</th><th>${__("Write-off")}</th>
			</tr></thead><tbody>${rows}</tbody>
		</table></div>${issues ? `<div class="mt-2"><strong>${__("Validation Notes")}</strong><ul>${issues}</ul></div>` : ""}`);
		this.render_debits();
	}

	sync_debit_rows() {
		const cheques = [...new Set(this.rows.map((row) => row.cheque_no))];
		this.debit_rows = this.debit_rows.filter((row) => cheques.includes(row.cheque_no));
		for (const cheque_no of cheques) {
			if (!this.debit_rows.some((row) => row.cheque_no === cheque_no)) {
				const cheque_rows = this.rows.filter((row) => row.cheque_no === cheque_no);
				const supplied = cheque_rows.reduce((total, row) => total + flt(row.invoice_amount), 0);
				this.debit_rows.push({ cheque_no, amount: supplied, role: __("Column E Debit"), controls: null });
			}
		}
	}

	add_debit(cheque_no) {
		this.debit_rows.push({ cheque_no, amount: 0, controls: null });
		this.render_debits();
	}

	render_debits() {
		const $section = this.$body.find(".debit-section").empty();
		if (!this.rows.length) return;
		$section.append(`<div class="d-flex justify-content-between align-items-center mb-2">
			<h4 class="m-0">${__("Debit Entries and Balance Check")}</h4>
			<span class="text-muted">${__("Add bank, EWT, receivable, or other debit lines per cheque.")}</span>
		</div>`);
		for (const cheque_no of [...new Set(this.rows.map((row) => row.cheque_no))]) {
			const $card = $(`<div class="frappe-card p-3 mb-3">
				<div class="d-flex justify-content-between"><strong>${__("Cheque")} ${frappe.utils.escape_html(cheque_no)}</strong>
				<button class="btn btn-xs btn-default add-debit">${__("Add Debit")}</button></div>
				<div class="debit-rows mt-2"></div><div class="balance mt-2"></div>
			</div>`).appendTo($section);
			$card.find(".add-debit").on("click", () => this.add_debit(cheque_no));
			for (const row of this.debit_rows.filter((value) => value.cheque_no === cheque_no)) {
				this.render_debit_row($card.find(".debit-rows"), row);
			}
		}
		this.update_balance_state();
	}

	render_debit_row($parent, row) {
		const $row = $('<div class="row align-items-end border-top pt-2 mb-2"></div>').appendTo($parent);
		$(`<div class="col-12 text-muted small mb-1">${frappe.utils.escape_html(row.role || __("Additional Debit"))}</div>`).appendTo($row);
		const make = (fieldtype, fieldname, label, options, width = "col-lg-2") => {
			const $cell = $(`<div class="col-sm-6 ${width}"></div>`).appendTo($row);
			return frappe.ui.form.make_control({ parent: $cell, df: { fieldtype, fieldname, label, options }, render_input: true });
		};
		const account = make("Link", "account", __("Account"), "Account", "col-lg-3");
		account.get_query = () => ({ filters: { company: this.company.get_value(), is_group: 0 } });
		const party_type = make("Select", "party_type", __("Party Type"), "\nCustomer\nSupplier\nEmployee");
		const party = make("Link", "party", __("Party"), row.party_type || "Customer", "col-lg-3");
		const amount = make("Currency", "amount", __("Debit Amount"), null, "col-lg-2");
		const $remove = $('<div class="col-lg-2"><button class="btn btn-xs btn-danger mb-2">Remove</button></div>').appendTo($row);

		account.set_value(row.account || "");
		party_type.set_value(row.party_type || "");
		party.set_value(row.party || "");
		amount.set_value(row.amount || 0);
		row.controls = { account, party_type, party, amount };
		const changed = () => this.update_balance_state();
		account.df.onchange = changed;
		amount.df.onchange = changed;
		party_type.df.onchange = () => {
			party.df.options = party_type.get_value() || "Customer";
			party.set_value("");
			party.refresh();
			changed();
		};
		party.df.onchange = changed;
		$remove.find("button").on("click", () => {
			this.debit_rows = this.debit_rows.filter((value) => value !== row);
			this.render_debits();
		});
	}

	get_debits() {
		return this.debit_rows.map((row) => ({
			cheque_no: row.cheque_no,
			account: row.controls?.account.get_value() || row.account || "",
			party_type: row.controls?.party_type.get_value() || row.party_type || "",
			party: row.controls?.party.get_value() || row.party || "",
			amount: flt(row.controls?.amount.get_value() ?? row.amount),
			remark: row.role || "",
		}));
	}

	update_balance_state(invalid_rows) {
		const invalid = invalid_rows ?? this.rows.filter((row) => row.status === "Invalid").length;
		let balanced = Boolean(this.rows.length);
		for (const cheque_no of [...new Set(this.rows.map((row) => row.cheque_no))]) {
			const invoice_credits = new Map();
			this.rows.filter((row) => row.cheque_no === cheque_no)
				.forEach((row) => invoice_credits.set(row.invoice_no, flt(row.outstanding)));
			const credits = [...invoice_credits.values()].reduce((sum, amount) => sum + amount, 0);
			const paid_debits = this.get_debits().filter((row) => row.cheque_no === cheque_no).reduce((sum, row) => sum + flt(row.amount), 0);
			const ewt = Math.round((this.rows.filter((row) => row.cheque_no === cheque_no)
				.reduce((sum, row) => sum + flt(row.ewt_amount), 0) + Number.EPSILON) * 100) / 100;
			const debits = paid_debits + ewt;
			const difference = debits - credits;
			const can_write_off = Math.abs(difference) < 0.005 || Boolean(this.write_off.get_value());
			const has_ewt_account = !ewt || Boolean(this.ewt_account.get_value());
			const complete = this.get_debits().filter((row) => row.cheque_no === cheque_no)
				.every((row) => row.account && row.amount > 0 && ((!row.party_type && !row.party) || (row.party_type && row.party)));
			balanced = balanced && can_write_off && has_ewt_account && complete;
			this.$body.find(".debit-section .frappe-card").filter((_, card) => $(card).find("strong").text().endsWith(cheque_no))
				.find(".balance").html(`<span class="indicator ${can_write_off ? "green" : "orange"}">
				${__("Paid Debits")}: ${format_currency(paid_debits)} · ${__("EWT")}: ${format_currency(ewt)} ·
				${__("Invoice Credits")}: ${format_currency(credits)} ·
				${__("Write-off")}: ${format_currency(Math.abs(difference))} ${difference >= 0 ? __("Credit") : __("Debit")}</span>`);
		}
		this.create_button.prop("disabled", invalid > 0 || !balanced);
	}

	confirm_create() {
		for (const field of [this.company, this.posting_date, this.ewt_account, this.file]) {
			if (!field.get_value()) {
				frappe.msgprint(__("Please complete all required fields."));
				return;
			}
		}
		frappe.confirm(__("Create balanced draft Journal Entries and open the first entry?"), async () => {
			const { message } = await frappe.call({
				method: "erpnext_payment_uploading.erpnext_payment_uploading.page.payment_upload.payment_upload.create_journal_entries",
				args: {
					rows: this.rows, debits: this.get_debits(), company: this.company.get_value(),
					posting_date: this.posting_date.get_value(), ewt_account: this.ewt_account.get_value(),
					write_off_account: this.write_off.get_value(),
				},
				freeze: true, freeze_message: __("Creating draft Journal Entries..."),
			});
			frappe.msgprint(__("Created {0} draft Journal Entries: {1}", [message.count, message.journal_entries.join(", ")]));
			if (message.journal_entries.length) frappe.set_route("Form", "Journal Entry", message.journal_entries[0]);
		});
	}
}
