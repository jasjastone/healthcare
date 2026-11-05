// "Create > Healthcare Practitioner" on the Employee form; the list view bulk action is in employee_list.js
frappe.ui.form.on("Employee", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(
			__("Healthcare Practitioner"),
			() => {
				if (!frm.doc.user_id) {
					frappe.throw(
						__(
							"Set a User ID (system user account) for this employee before creating a Healthcare Practitioner.",
						),
					);
				}
				healthcare.create_practitioners_from_employees([frm.doc.name]);
			},
			__("Create"),
		);
	},
});
