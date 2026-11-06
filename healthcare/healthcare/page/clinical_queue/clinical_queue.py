# Live work queue for doctors, nurses, lab staff and pharmacists.
# Refreshed by clinical_queue.js on list_update.

import frappe
from frappe import _
from frappe.utils import today

from healthcare.healthcare.alerts import ORDER_ROLES

OPEN_APPOINTMENT = ["Scheduled", "Open", "Confirmed", "Checked In"]
OPEN_NURSING_TASK = ["Draft", "Requested", "Received", "Accepted", "Ready", "In Progress", "On Hold"]
OPEN_MEDICATION_REQUEST = ["draft-Medication Request Status", "active-Medication Request Status"]


@frappe.whitelist()
def get_queue():
	roles = set(frappe.get_roles())
	sections = []

	practitioner = frappe.db.get_value("Healthcare Practitioner", {"user_id": frappe.session.user})
	if practitioner:
		sections.append(
			section(
				_("My Appointments Today"),
				"Patient Appointment",
				{
					"practitioner": practitioner,
					"appointment_date": today(),
					"status": ("in", OPEN_APPOINTMENT),
				},
				["patient_name", "appointment_time", "status", "service_unit"],
				"appointment_time asc",
			)
		)

	order_sections = (("Laboratory User", _("New Lab Orders")), ("Nursing User", _("New Procedure Orders")))
	for role, title in order_sections:
		if role in roles:
			sections.append(
				section(
					title,
					"Service Request",
					{
						# submitting sets "active"; the Lab Test / Clinical Procedure sets "completed"
						"docstatus": 1,
						"status": "active-Request Status",
						"template_dt": ("in", [dt for dt, r in ORDER_ROLES.items() if r == role]),
					},
					["patient_name", "template_dn", "order_date", "order_time"],
				)
			)

	if "Laboratory User" in roles:
		sections.append(
			section(
				_("Lab Tests in Progress"),
				"Lab Test",
				{"docstatus": 0},
				["patient_name", "lab_test_name", "status"],
			)
		)

	if "Nursing User" in roles:
		sections.append(
			section(
				_("Nursing Tasks"),
				"Nursing Task",
				{"status": ("in", OPEN_NURSING_TASK)},
				["patient_name", "activity", "status", "requested_start_time", "user"],
				"requested_start_time asc",
			)
		)

	if "Healthcare Pharmacist" in roles:
		sections.append(
			section(
				_("New Prescriptions"),
				"Medication Request",
				{"docstatus": 1, "status": ("in", OPEN_MEDICATION_REQUEST)},
				["patient_name", "medication", "medication_item", "quantity", "order_date"],
			)
		)

	return sections


def section(title, doctype, filters, fields, order_by="creation asc"):
	meta = frappe.get_meta(doctype)
	return {
		"title": title,
		"doctype": doctype,
		"columns": [{"fieldname": f, "label": _(meta.get_label(f))} for f in fields],
		# ponytail: capped at 100 rows per section, paginate if a queue ever gets that long
		"rows": frappe.get_list(
			doctype, filters=filters, fields=["name", *fields], order_by=order_by, limit=100
		),
	}
