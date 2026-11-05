// extends erpnext's Employee listview_settings instead of replacing it
const employee_list = (frappe.listview_settings["Employee"] ||= {});
const employee_list_onload = employee_list.onload;

employee_list.onload = function (listview) {
	employee_list_onload?.(listview);
	listview.page.add_actions_menu_item(__("Create Healthcare Practitioner"), () => {
		const employees = listview.get_checked_items(true);
		if (!employees.length) {
			frappe.throw(__("Select at least one employee"));
		}
		healthcare.create_practitioners_from_employees(employees);
	});
};
