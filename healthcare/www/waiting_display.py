# TV screen for the waiting area: checked-in patients by doctor/room, numbers only (no patient names).
# Log the TV in as a user whose only role is "Queue Display".

import frappe
from frappe import _
from frappe.utils import now_datetime, time_diff_in_seconds, today

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/waiting-display"
		raise frappe.Redirect

	allowed = {"Queue Display", "Healthcare Receptionist", "Healthcare Administrator", "System Manager"}
	if not allowed & set(frappe.get_roles()):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	context.queues = get_queues()
	context.updated = now_datetime().strftime("%H:%M")


def get_queues():
	now = now_datetime()
	queues = {}
	# get_all skips permissions on purpose: the TV user has no doctype access and sees numbers only
	for appt in frappe.get_all(
		"Patient Appointment",
		filters={"status": "Checked In", "appointment_date": today()},
		fields=[
			"name",
			"practitioner_name",
			"department",
			"service_unit",
			"checked_in_at",
			"appointment_datetime",
		],
		order_by="checked_in_at asc, appointment_datetime asc",
	):
		since = appt.checked_in_at or appt.appointment_datetime or now
		queue = " · ".join(filter(None, [appt.practitioner_name or appt.department, appt.service_unit]))
		queues.setdefault(queue or _("General"), []).append(
			{
				"number": appointment_number(appt.name),
				"minutes": max(0, int(time_diff_in_seconds(now, since) // 60)),
			}
		)
	return queues


def appointment_number(name):
	"""HLC-APP-2026-00123 -> 123 (the number on the patient's appointment slip)."""
	return name.rsplit("-", 1)[-1].lstrip("0") or "0"


def test_appointment_number():
	assert appointment_number("HLC-APP-2026-00123") == "123"
	assert appointment_number("HLC-APP-2026-00000") == "0"
	assert appointment_number("CUSTOM42") == "CUSTOM42"
