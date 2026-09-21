"""Whitelisted HTTP API. Every endpoint runs as the logged-in session user."""
import json

import frappe
from frappe import _

from ai_chatbot.services import chatbot, security


def _require_desk_user():
	user = frappe.session.user
	if user == "Guest" or frappe.get_cached_value("User", user, "user_type") != "System User":
		frappe.throw(_("You do not have permission to use the chatbot."), frappe.PermissionError)


@frappe.whitelist(methods=["POST"])
def chat(message=None, history=None):
	"""Answer a natural-language question. Never raises for expected problems:
	returns {"ok": bool, "reply": str, "blocks": [...], "lang": str, "mode": str}."""
	_require_desk_user()
	return chatbot.handle_message(message, _parse_history(history))


@frappe.whitelist(methods=["GET"])
def get_config():
	_require_desk_user()
	settings = security.get_settings()
	return {
		"enabled": bool(settings.enabled),
		"mode": "llm" if security.llm_enabled(settings) else "rules",
		"max_rows": settings.max_rows,
	}


def _parse_history(history):
	if isinstance(history, str):
		try:
			history = json.loads(history)
		except ValueError:
			return []
	if not isinstance(history, list):
		return []
	out = []
	for item in history[-6:]:
		if isinstance(item, dict) and item.get("role") in ("user", "bot"):
			out.append({"role": item["role"], "text": str(item.get("text") or "")[:500]})
	return out
