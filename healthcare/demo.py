"""Training demo data: one login per Healthcare role and a clinic day already in progress.

	bench --site <site> execute healthcare.demo.install
	bench --site <site> execute healthcare.demo.install --kwargs "{'company': 'My Co', 'password': 'Secret#123'}"
	bench --site <site> execute healthcare.demo.remove

Every record install creates is listed in a global default (REGISTRY). remove deletes those
plus whatever they generated (orders, invoices, customers, contacts, notifications), so
masters that already existed on the site are reused and never deleted.
"""

import json
from collections import defaultdict

import frappe
from frappe.utils import add_days, add_to_date, now_datetime, today

import erpnext

REGISTRY = "healthcare_demo_records"
DEFAULT_PASSWORD = "Demo@Health2026"
EMAIL = "{}.demo@example.com"

# key, first name, last name, roles, default workspace
USERS = [
	("admin", "Hope", "Atuhaire", ["Healthcare Administrator", "HR Manager", "HR User"], "Healthcare"),
	("reception", "Ivan", "Mukasa", ["Healthcare Receptionist"], "Reception Desk"),
	("doctor", "Daniel", "Opio", ["Physician"], "Doctor Desk"),
	("paediatrician", "Ruth", "Nansubuga", ["Physician"], "Doctor Desk"),
	("nurse", "Grace", "Achieng", ["Nursing User"], "Nursing Desk"),
	("lab", "Moses", "Ochieng", ["Laboratory User", "LabTest Approver"], "Lab Desk"),
	("pharmacist", "Sarah", "Namubiru", ["Healthcare Pharmacist"], "Pharmacy Desk"),
	("tv", "Waiting Room", "TV", ["Queue Display"], None),
]

# first name, last name, sex, date of birth
PATIENTS = [
	("Amina", "Nakato", "Female", "1992-03-14"),
	("John", "Okello", "Male", "1985-07-22"),
	("Esther", "Atim", "Female", "1978-11-05"),
	("Brian", "Kato", "Male", "2001-01-30"),
	("Joy", "Nabirye", "Female", "2019-06-12"),
	("Samuel", "Wasswa", "Male", "2016-09-03"),
	("Peter", "Ssemakula", "Male", "1969-04-18"),
	("Mary", "Auma", "Female", "1995-12-25"),
]

# patient index, practitioner, days from today, time, minutes waiting since check-in (None = not here yet)
APPOINTMENTS = [
	(0, "doctor", 0, "09:00", 40),
	(1, "doctor", 0, "09:30", 15),
	(2, "doctor", 0, "11:00", None),
	(3, "doctor", 0, "14:30", None),
	(4, "paediatrician", 0, "09:15", 5),
	(5, "paediatrician", 0, "10:30", None),
	(7, "doctor", 1, "10:00", None),
]
SEEN_PATIENT = 6  # already seen today; the encounter's orders wait in the lab, nursing and pharmacy queues


def install(company=None, password=DEFAULT_PASSWORD):
	if frappe.db.get_global(REGISTRY):
		print("Demo data is already installed. Run healthcare.demo.remove first.")
		return

	created = []
	try:
		make_demo(created, company or erpnext.get_default_company(), password)
	except Exception:
		frappe.db.rollback()
		# some controllers commit on their own, so record whatever survived for remove
		save_registry([r for r in created if frappe.db.exists(*r)])
		frappe.db.commit()
		print("Install failed. Anything it saved is recorded: run healthcare.demo.remove to clean up.")
		raise

	# the appointment alerts queued emails to the demo doctors, whose addresses don't exist
	delete_queued_emails(created)
	save_registry(created)
	frappe.db.commit()
	print(f"Demo data installed ({len(created)} records). Logins, all with password {password}:")
	for key, first, last, roles, _workspace in USERS:
		print(f"  {EMAIL.format(key):32} {first} {last} ({', '.join(roles)})")


def make_demo(created, company, password):
	def make(doc, key=()):
		"""Insert doc, or reuse (and leave untracked) a record matching the `key` fields."""
		name = key and frappe.db.exists(doc["doctype"], {k: doc[k] for k in key})
		if name:
			return frappe.get_doc(doc["doctype"], name)
		doc = frappe.get_doc(doc).insert(ignore_permissions=True)
		created.append((doc.doctype, doc.name))
		return doc

	def track_items(doc, item_codes):
		"""Items (and their prices) that a new template or medication created for itself."""
		if (doc.doctype, doc.name) not in created:
			return
		for code in item_codes:
			if frappe.db.exists("Item", code):
				created.append(("Item", code))
				created.extend(
					("Item Price", p) for p in frappe.get_all("Item Price", {"item_code": code}, pluck="name")
				)

	users = {}
	for key, first, last, roles, workspace in USERS:
		email = EMAIL.format(key)
		if frappe.db.exists("User", email):
			users[key] = email
			continue
		make(
			{
				"doctype": "User",
				"email": email,
				"first_name": first,
				"last_name": last,
				"send_welcome_email": 0,
				"new_password": password,
				"default_workspace": workspace
				if workspace and frappe.db.exists("Workspace", workspace)
				else None,
				"roles": [{"role": role} for role in roles if frappe.db.exists("Role", role)],
			}
		)
		users[key] = email

	# masters: reused when the site already has them
	for department in ("General Medicine", "Paediatrics", "Pathology"):
		make({"doctype": "Medical Department", "department": department}, ["department"])
	for diagnosis in ("Malaria", "Upper Respiratory Tract Infection"):
		make({"doctype": "Diagnosis", "diagnosis": diagnosis}, ["diagnosis"])

	make(
		{
			"doctype": "Healthcare Service Unit Type",
			"service_unit_type": "Consultation Room",
			"allow_appointments": 1,
		},
		["service_unit_type"],
	)
	root_unit = frappe.db.get_value(
		"Healthcare Service Unit",
		{"company": company, "is_group": 1, "parent_healthcare_service_unit": ["is", "not set"]},
	)
	rooms = [
		make(
			{
				"doctype": "Healthcare Service Unit",
				"healthcare_service_unit_name": f"Consultation Room {n}",
				"parent_healthcare_service_unit": root_unit,
				"service_unit_type": "Consultation Room",
				"allow_appointments": 1,
				"company": company,
			},
			["healthcare_service_unit_name", "company"],
		).name
		for n in (1, 2)
	]

	for name, minutes, colour in (
		("General Consultation", 15, "#29CD42"),
		("Follow-up Visit", 10, "#5E64FF"),
	):
		make(
			{
				"doctype": "Appointment Type",
				"appointment_type": name,
				"allow_booking_for": "Practitioner",
				"default_duration": minutes,
				"color": colour,
			},
			["appointment_type"],
		)

	make(
		{
			"doctype": "Practitioner Schedule",
			"schedule_name": "Demo Clinic Hours",
			"time_slots": [
				{
					"day": day,
					"from_time": f"{h:02d}:{m:02d}:00",
					"to_time": f"{h + (m + 30) // 60:02d}:{(m + 30) % 60:02d}:00",
				}
				for day in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")
				for h in range(8, 17)
				for m in (0, 30)
			],
		},
		["schedule_name"],
	)

	practitioners = {}
	for key, department, room in (
		("doctor", "General Medicine", rooms[0]),
		("paediatrician", "Paediatrics", rooms[1]),
	):
		first, last = next((u[1], u[2]) for u in USERS if u[0] == key)
		practitioners[key] = make(
			{
				"doctype": "Healthcare Practitioner",
				"first_name": f"Dr. {first}",
				"last_name": last,
				"gender": "Male" if key == "doctor" else "Female",
				"status": "Active",
				"department": department,
				"user_id": users[key],
				"practitioner_schedules": [{"schedule": "Demo Clinic Hours", "service_unit": room}],
			},
			["user_id"],
		)

	# lab, procedure, medication and nursing masters
	make({"doctype": "Lab Test Sample", "sample": "Whole Blood"}, ["sample"])
	lab_templates = [
		{
			"lab_test_name": "Malaria Test (mRDT)",
			"lab_test_template_type": "Descriptive",
			"lab_test_rate": 10000,
			"sample": "Whole Blood",
			"sample_qty": 1,
			"descriptive_test_templates": [
				{"particulars": "Result"},
				{"particulars": "Parasite density", "allow_blank": 1},
			],
		},
		{
			"lab_test_name": "Complete Blood Count",
			"lab_test_template_type": "Compound",
			"lab_test_rate": 25000,
			"sample": "Whole Blood",
			"sample_qty": 3,
			"normal_test_templates": [
				{"lab_test_event": "Haemoglobin", "lab_test_uom": "gm %", "normal_range": "12 - 17"},
				{
					"lab_test_event": "White Blood Cells",
					"lab_test_uom": "Cells / cumm",
					"normal_range": "4000 - 11000",
				},
				{
					"lab_test_event": "Platelets",
					"lab_test_uom": "Lakhs Cells / cumm",
					"normal_range": "1.5 - 4.5",
				},
			],
		},
		{
			"lab_test_name": "Fasting Blood Sugar",
			"lab_test_template_type": "Single",
			"lab_test_rate": 8000,
			"lab_test_uom": "mg / dl",
			"lab_test_normal_range": "70 - 100",
		},
	]
	for template in lab_templates:
		lab_template = make(
			{
				"doctype": "Lab Test Template",
				"lab_test_code": template["lab_test_name"],
				"lab_test_group": "Laboratory",
				"department": "Pathology",
				"is_billable": 1,
				**template,
			},
			["lab_test_name"],
		)
		track_items(lab_template, [template["lab_test_name"]])
	procedure = make(
		{
			"doctype": "Clinical Procedure Template",
			"template": "Wound Dressing",
			"item_code": "Wound Dressing",
			"item_group": "Services",
			"description": "Clean and dress a wound",
			"medical_department": "General Medicine",
			"is_billable": 1,
			"rate": 15000,
		},
		["template"],
	)
	track_items(procedure, ["Wound Dressing"])

	price_list = frappe.db.get_single_value("Selling Settings", "selling_price_list") or frappe.db.get_value(
		"Price List", {"selling": 1, "enabled": 1}
	)
	medications = {}
	for generic, strength, form, medication_class, item_code, rate in (
		("Artemether-Lumefantrine", 120, "Tablet", "Antimalarials", "Coartem 20/120mg Tablet", 6000),
		("Paracetamol", 500, "Tablet", "Non-Opioid Analgesics", "Paracetamol 500mg Tablet", 200),
		("Amoxicillin", 500, "Capsule", "Penicillins", "Amoxicillin 500mg Capsule", 500),
	):
		medications[generic] = make(
			{
				"doctype": "Medication",
				"generic_name": generic,
				"strength": strength,
				"strength_uom": "Milligram",
				"dosage_form": form,
				"medication_class": medication_class,
				"price_list": price_list,
				"linked_items": [
					{
						"item_code": item_code,
						"item_group": "Drug",
						"stock_uom": "Nos",
						"is_billable": 1,
						"rate": rate,
					}
				],
			},
			["generic_name", "strength", "dosage_form"],
		)
		track_items(medications[generic], [item_code])

	make(
		{
			"doctype": "Healthcare Activity",
			"activity": "Vital Signs Check",
			"role": "Nursing User",
			"task_doctype": "Vital Signs",
			"activity_duration": 900,
		},
		["activity"],
	)

	# Employees for the Employee -> Healthcare Practitioner buttons: one with a user, one without
	for first, last, user in (("Grace", "Achieng", users["nurse"]), ("Peter", "Mugisha", None)):
		frappe.db.savepoint("demo_employee")
		try:
			make(
				{
					"doctype": "Employee",
					"first_name": first,
					"last_name": last,
					"gender": "Female" if first == "Grace" else "Male",
					"date_of_birth": "1990-05-01",
					"date_of_joining": add_days(today(), -365),
					"company": company,
					"status": "Active",
					"user_id": user,
				}
			)
		except Exception as e:
			frappe.db.rollback(save_point="demo_employee")
			print(f"Skipped demo employee {first} {last} (this site's Employee needs more fields): {e}")

	# today's clinic
	patients = []
	for i, (first, last, sex, dob) in enumerate(PATIENTS):
		patient = make(
			{
				"doctype": "Patient",
				"first_name": first,
				"last_name": last,
				"sex": sex,
				"dob": dob,
				"mobile": f"+25670000{i:04d}",
			}
		)
		patient.db_set(
			"status", "Active"
		)  # Healthcare Settings may disable patients until a registration fee is paid
		patients.append(patient.name)

	def book(patient, practitioner, days, time):
		doctor = practitioners[practitioner]
		return make(
			{
				"doctype": "Patient Appointment",
				"patient": patient,
				"practitioner": doctor.name,
				"department": doctor.department,
				"service_unit": doctor.practitioner_schedules[0].service_unit,
				"appointment_type": "General Consultation",
				"appointment_for": "Practitioner",
				"appointment_date": add_days(today(), days),
				"appointment_time": f"{time}:00",
				"duration": 15,
				"company": company,
			}
		)

	for index, practitioner, days, time, waiting in APPOINTMENTS:
		appointment = book(patients[index], practitioner, days, time)
		if waiting is not None:
			appointment.status = "Checked In"
			appointment.save(ignore_permissions=True)
			appointment.db_set("checked_in_at", add_to_date(now_datetime(), minutes=-waiting))

	seen = book(patients[SEEN_PATIENT], "doctor", 0, "08:00")
	encounter = frappe.get_doc(
		{
			"doctype": "Patient Encounter",
			"patient": seen.patient,
			"appointment": seen.name,
			"appointment_type": seen.appointment_type,
			"practitioner": seen.practitioner,
			"medical_department": seen.department,
			"encounter_date": today(),
			"encounter_time": "08:15:00",
			"company": company,
			"diagnosis": [{"diagnosis": "Malaria"}],
			"lab_test_prescription": [
				{"lab_test_code": "Malaria Test (mRDT)"},
				{"lab_test_code": "Complete Blood Count"},
			],
			"procedure_prescription": [{"procedure": "Wound Dressing", "no_of_sessions": 1}],
			"drug_prescription": [
				{
					"medication": m.name,
					"drug_code": m.linked_items[0].item_code,
					"dosage": "1-0-1",
					"period": "3 Day",
					"dosage_form": m.dosage_form,
				}
				for m in (medications["Artemether-Lumefantrine"], medications["Paracetamol"])
			],
		}
	).insert(ignore_permissions=True)
	created.append(("Patient Encounter", encounter.name))
	encounter.submit()  # creates the Service Requests and Medication Requests (removed through the patient)

	vitals = make(
		{
			"doctype": "Vital Signs",
			"patient": patients[0],
			"signs_date": today(),
			"signs_time": "09:05:00",
			"temperature": "38.4",
			"pulse": "96",
			"respiratory_rate": "20",
			"bp_systolic": "122",
			"bp_diastolic": "78",
			"height": 1.62,
			"weight": 58,
			"company": company,
		}
	)
	vitals.submit()

	for patient, user in ((patients[1], users["nurse"]), (patients[4], None)):
		make(
			{
				"doctype": "Nursing Task",
				"activity": "Vital Signs Check",
				"status": "Requested",
				"patient": patient,
				"user": user,
				"company": company,
				"date": today(),
				"requested_start_time": now_datetime(),
			}
		)

	make(
		{
			"doctype": "Lab Test",
			"patient": patients[0],
			"patient_sex": "Female",
			"template": "Fasting Blood Sugar",
			"practitioner": practitioners["doctor"].name,
			"company": company,
		}
	)


def remove():
	records = json.loads(frappe.db.get_global(REGISTRY) or "[]")
	if not records:
		print("No demo data is installed.")
		return

	names = defaultdict(list)
	for doctype, name in records:
		names[doctype].append(name)
	patients, users = names["Patient"], names["User"]
	customers = [c for c in frappe.get_all("Patient", {"name": ["in", patients]}, pluck="customer") if c]
	events = [
		e for e in frappe.get_all("Patient Appointment", {"patient": ["in", patients]}, pluck="event") if e
	]

	# everything that points at a demo patient or customer, plus the payments against those customers
	generated = linked_docs("Patient", patients) | linked_docs("Customer", customers)
	generated |= {
		("Payment Entry", n)
		for n in frappe.get_all(
			"Payment Entry", {"party_type": "Customer", "party": ["in", customers]}, pluck="name"
		)
	}
	generated -= set(map(tuple, records))

	healthcare = set(
		frappe.get_all("DocType", {"module": ["in", frappe.get_module_list("healthcare")]}, pluck="name")
	)
	# ERPNext documents (invoices, payments, stock entries) are cancelled properly so their ledgers reverse.
	# Payments go first because they hold the invoices.
	others = sorted((d for d in generated if d[0] not in healthcare), key=lambda d: d[0] != "Payment Entry")
	for doctype, name in others:
		doc = frappe.get_doc(doctype, name)
		if doc.docstatus == 1:
			doc.flags.ignore_links = True
			doc.cancel()
		frappe.delete_doc(doctype, name, force=True, ignore_permissions=True, delete_permanently=True)

	for doctype, name in [d for d in generated if d[0] in healthcare] + [("Event", e) for e in events]:
		force_delete(doctype, name)

	contacts = frappe.get_all(
		"Dynamic Link",
		{
			"parenttype": ["in", ["Contact", "Address"]],
			"link_doctype": ["in", ["Patient", "Customer"]],
			"link_name": ["in", patients + customers],
		},
		["parenttype", "parent"],
		distinct=True,
	)
	for link in contacts:
		force_delete(link.parenttype, link.parent)
	for contact in frappe.get_all("Contact", {"user": ["in", users]}, pluck="name"):  # made for each new User
		force_delete("Contact", contact)
	for customer in customers:
		force_delete("Customer", customer)

	for doctype, name in reversed(records):
		if doctype == "Item" and frappe.db.exists(
			"Stock Ledger Entry", {"item_code": name, "is_cancelled": 0}
		):
			print(f"Kept Item {name}: it has stock transactions. Cancel them and delete it by hand.")
		elif doctype == "User":
			frappe.delete_doc("User", name, force=True, ignore_permissions=True, delete_permanently=True)
		else:
			force_delete(doctype, name)

	frappe.db.delete("Notification Log", {"for_user": ["in", users]})
	frappe.db.delete("User Permission", {"user": ["in", users]})
	everything = set(map(tuple, records)) | generated
	for doctype, name in everything:
		frappe.db.delete("Notification Log", {"document_type": doctype, "document_name": name})
	delete_queued_emails(everything)

	frappe.db.set_global(REGISTRY, None)
	frappe.db.commit()
	print(f"Demo data removed ({len(records)} records and {len(generated)} generated documents).")


def linked_docs(doctype, names):
	"""(doctype, name) of every document with a Link field to one of `names`, including via child tables."""
	if not names:
		return set()

	found = set()
	fields = frappe.get_all("DocField", {"fieldtype": "Link", "options": doctype}, ["parent", "fieldname"])
	fields += frappe.get_all(
		"Custom Field", {"fieldtype": "Link", "options": doctype}, ["dt as parent", "fieldname"]
	)
	for field in fields:
		meta = frappe.get_meta(field.parent)
		if meta.issingle or meta.is_virtual or field.parent == doctype:
			continue
		if meta.istable:
			rows = frappe.get_all(
				field.parent, {field.fieldname: ["in", names]}, ["parenttype", "parent"], distinct=True
			)
			found |= {(r.parenttype, r.parent) for r in rows if r.parenttype}
		else:
			found |= {
				(field.parent, n)
				for n in frappe.get_all(field.parent, {field.fieldname: ["in", names]}, pluck="name")
			}
	return found


def force_delete(doctype, name):
	"""Delete without the cancel / on_trash logic: everything around it is being deleted too."""
	if not frappe.db.exists(doctype, name):
		return
	if frappe.get_meta(doctype).is_submittable:
		frappe.db.set_value(doctype, name, "docstatus", 2, update_modified=False)
	frappe.delete_doc(
		doctype, name, force=True, ignore_permissions=True, ignore_on_trash=True, delete_permanently=True
	)


def delete_queued_emails(docs):
	"""Unsent emails about these documents, e.g. the appointment alerts to demo doctors."""
	for doctype, name in docs:
		filters = {"reference_doctype": doctype, "reference_name": name, "status": "Not Sent"}
		for email in frappe.get_all("Email Queue", filters, pluck="name"):
			frappe.delete_doc("Email Queue", email, force=True, ignore_permissions=True)


def save_registry(records):
	frappe.db.set_global(REGISTRY, json.dumps(records) if records else None)
