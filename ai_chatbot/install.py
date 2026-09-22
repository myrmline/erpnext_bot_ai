import json

import frappe

WORKSPACE = "AI Chatbot"


def after_install():
	ensure_workspace()


def after_migrate():
	ensure_workspace()
	from ai_chatbot.services import help_service

	help_service.clear_cache()


def before_uninstall():
	if frappe.db.exists("Workspace", WORKSPACE):
		frappe.delete_doc("Workspace", WORKSPACE, force=1, ignore_permissions=True)


def has_app_permission():
	return frappe.session.user != "Guest" and (
		frappe.get_cached_value("User", frappe.session.user, "user_type") == "System User"
	)


def ensure_workspace():
	"""Create the sidebar entry (a public Workspace with a shortcut to the chat page)."""
	if frappe.db.exists("Workspace", WORKSPACE):
		return
	content = [
		{"id": "aic_h1", "type": "header", "data": {"text": '<span class="h4"><b>AI Chatbot</b></span>', "col": 12}},
		{"id": "aic_s1", "type": "shortcut", "data": {"shortcut_name": "Open AI Chatbot", "col": 3}},
	]
	doc = frappe.get_doc(
		{
			"doctype": "Workspace",
			"name": WORKSPACE,
			"label": WORKSPACE,
			"title": WORKSPACE,
			"module": "AI Chatbot",
			"public": 1,
			"is_hidden": 0,
			"icon": "chat",
			"content": json.dumps(content),
			"shortcuts": [{"type": "Page", "label": "Open AI Chatbot", "link_to": "ai-chat", "color": "Blue"}],
		}
	)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_links = True
	doc.insert(ignore_if_duplicate=True)
	frappe.db.commit()
