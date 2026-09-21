import frappe
from frappe.utils import add_days, cint, nowdate


def clear_old_logs():
	days = cint(frappe.db.get_single_value("AI Chatbot Settings", "audit_retention_days") or 90)
	frappe.db.delete("AI Chatbot Log", {"creation": ["<", add_days(nowdate(), -days)]})
