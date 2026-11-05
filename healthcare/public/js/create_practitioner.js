// Shared by the Employee form button (employee.js) and list bulk action (employee_list.js)
frappe.provide("healthcare");

healthcare.create_practitioners_from_employees = function (employees) {
	frappe
		.xcall(
			"healthcare.healthcare.doctype.healthcare_practitioner.healthcare_practitioner.create_from_employees",
			{ employees },
		)
		.then(({ created, existing, missing_user }) => {
			const link = name =>
				frappe.utils.get_form_link("Healthcare Practitioner", name, true);
			const block = (title, items) =>
				items.length
					? `<p><b>${title}</b></p><ul><li>${items.join("</li><li>")}</li></ul>`
					: "";
			frappe.msgprint({
				title: __("Healthcare Practitioners"),
				indicator: missing_user.length ? "orange" : "green",
				message:
					block(__("Created"), created.map(link)) +
					block(__("Already exists"), existing.map(link)) +
					block(
						__(
							"The following employees couldn't get a Healthcare Practitioner record because their system user account is missing",
						),
						missing_user.map(frappe.utils.escape_html),
					),
			});
		});
};
