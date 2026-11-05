const QUEUE_DOCTYPES = [
	"Patient Appointment",
	"Service Request",
	"Lab Test",
	"Nursing Task",
	"Medication Request",
];

frappe.pages["clinical-queue"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Clinical Queue"),
		single_column: true,
	});
	const $body = $("<div>").appendTo(page.main);

	const refresh = () =>
		frappe
			.xcall("healthcare.healthcare.page.clinical_queue.clinical_queue.get_queue")
			.then(sections => $body.html(sections.map(render_section).join("")));

	page.set_primary_action(__("Refresh"), refresh);

	// any save of these doctypes (by anyone) refreshes the queue
	const debounced = frappe.utils.debounce(refresh, 1000);
	QUEUE_DOCTYPES.forEach(doctype => frappe.realtime.doctype_subscribe(doctype));
	frappe.realtime.on("list_update", data => {
		if (QUEUE_DOCTYPES.includes(data.doctype)) debounced();
	});

	refresh();
};

function render_section(section) {
	const head = section.columns.map(c => `<th>${c.label}</th>`).join("");
	const body = section.rows.length
		? section.rows
				.map(
					row =>
						`<tr><td>${frappe.utils.get_form_link(section.doctype, row.name, true)}</td>${section.columns
							.map(
								c =>
									`<td>${frappe.utils.escape_html(String(row[c.fieldname] ?? ""))}</td>`,
							)
							.join("")}</tr>`,
				)
				.join("")
		: `<tr><td colspan="${section.columns.length + 1}" class="text-muted">${__("Nothing pending")}</td></tr>`;

	return `<div class="frappe-card p-3 mb-4">
		<h5>${section.title} <span class="badge badge-secondary">${section.rows.length}</span></h5>
		<table class="table table-sm"><thead><tr><th>${__("ID")}</th>${head}</tr></thead><tbody>${body}</tbody></table>
	</div>`;
}
