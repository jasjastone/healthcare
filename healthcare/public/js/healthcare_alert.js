// Sent by healthcare/healthcare/alerts.py to the assigned doctor / nurse / lab / pharmacy users.
// Browsers only allow sound after the user has clicked somewhere on the page once.
// Registered on app_ready: frappe.realtime.on is a no-op until the socket is created during desk boot.
$(document).on("app_ready", () => {
	frappe.realtime.on("healthcare_alert", data => {
		frappe.utils.play_sound("healthcare_alert");
		frappe.show_alert(
			{
				message: frappe.utils.get_form_link(
					data.doctype,
					data.name,
					true,
					frappe.utils.escape_html(data.subject),
				),
				indicator: "blue",
			},
			15,
		);
	});
});
