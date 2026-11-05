# Live alerts for doctors, nurses and lab staff: bell notification + sound in open desk tabs
# (see public/js/healthcare_alert.js), plus an email to the doctor for new appointments.

import frappe
from frappe import _
from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification
from frappe.utils import format_date, format_time, get_url_to_form
from frappe.utils.user import get_users_with_role

# which role gets pinged when an encounter order (Service Request) is submitted
ORDER_ROLES = {
	"Lab Test Template": "Laboratory User",
	"Observation Template": "Laboratory User",
	"Clinical Procedure Template": "Nursing User",
	"Therapy Type": "Nursing User",
}


def alert(users, doc, subject):
	users = list({user for user in users if user and user != frappe.session.user})
	if not users:
		return

	enqueue_create_notification(
		users,
		{
			"type": "Alert",
			"document_type": doc.doctype,
			"document_name": doc.name,
			"subject": subject,
			"from_user": frappe.session.user,
		},
	)
	for user in users:
		frappe.publish_realtime(
			"healthcare_alert",
			{"subject": subject, "doctype": doc.doctype, "name": doc.name},
			user=user,
			after_commit=True,
		)


def appointment_assigned(doc, method=None):
	"""Patient Appointment on_update: runs on insert and when the practitioner is changed."""
	before = doc.get_doc_before_save()
	if not doc.practitioner or doc.status == "Cancelled":
		return
	# on insert, after_insert's db_set already loaded the new row as "before", so ignore it then
	if not doc.flags.in_insert and before and before.practitioner == doc.practitioner:
		return

	user, email = frappe.db.get_value("Healthcare Practitioner", doc.practitioner, ["user_id", "email_id"])
	if (user or email) == frappe.session.user:
		return

	subject = _("New appointment: {0} on {1} at {2}").format(
		doc.patient_name, format_date(doc.appointment_date), format_time(doc.appointment_time)
	)
	alert([user], doc, subject)

	if user or email:
		frappe.sendmail(
			recipients=[user or email],
			subject=subject,
			message=_(
				"Patient: {0}<br>Date: {1}<br>Time: {2}<br>Department: {3}<br>Service Unit: {4}<br>"
				"Notes: {5}<br><br><a href='{6}'>Open appointment</a>"
			).format(
				doc.patient_name,
				format_date(doc.appointment_date),
				format_time(doc.appointment_time),
				doc.department or "-",
				doc.service_unit or "-",
				doc.notes or "-",
				get_url_to_form(doc.doctype, doc.name),
			),
			reference_doctype=doc.doctype,
			reference_name=doc.name,
		)


def encounter_created(doc, method=None):
	"""Patient Encounter after_insert: tell the doctor when someone else (e.g. a nurse) opens one for them."""
	user = doc.practitioner and frappe.db.get_value("Healthcare Practitioner", doc.practitioner, "user_id")
	alert([user], doc, _("New encounter: {0}").format(doc.patient_name))


def order_submitted(doc, method=None):
	"""Service Request on_submit: encounter lab orders go to lab staff, procedures/therapies to nurses."""
	role = ORDER_ROLES.get(doc.template_dt)
	if role:
		subject = _("New order: {0} for {1}").format(doc.template_dn, doc.patient_name)
		alert(get_users_with_role(role), doc, subject)


def medication_ordered(doc, method=None):
	"""Medication Request on_submit: encounter prescriptions go to pharmacists."""
	medication = doc.medication or doc.medication_item
	subject = _("New prescription: {0} for {1}").format(medication, doc.patient_name)
	alert(get_users_with_role("Healthcare Pharmacist"), doc, subject)


def nursing_task_created(doc, method=None):
	"""Nursing Task after_insert: the assigned nurse, else every Nursing User."""
	users = [doc.user] if doc.user else get_users_with_role("Nursing User")
	alert(users, doc, _("New nursing task: {0} for {1}").format(doc.activity, doc.patient_name))


def lab_test_created(doc, method=None):
	"""Lab Test after_insert: ordered tests were already alerted via their Service Request."""
	if not doc.service_request:
		alert(
			get_users_with_role("Laboratory User"),
			doc,
			_("New lab test: {0} for {1}").format(doc.lab_test_name, doc.patient_name),
		)
