"""Whitelisted HTTP API. Every endpoint runs as the logged-in session user.

Both endpoints are declared allow_guest=True on purpose: if we left Frappe's
default (logged-in users only), an expired session, a stray request sent
before login finishes, or a cookie/proxy hiccup makes Frappe reject the call
*before* our code runs, with a raw, untranslated "Not permitted" error and a
full traceback shown to the user. By allowing the guest call through and
checking the session ourselves, we always return our own clean, translated,
JSON-shaped answer instead - the endpoint is exactly as protected (no data
operation ever runs for a non-System-User), just the failure looks like part
of the chat instead of a crash."""
import json

import frappe

from ai_chatbot.services import chatbot, security
from ai_chatbot.services.messages import detect_language, t


class NotLoggedIn(Exception):
	pass


def _check_access(lang):
	user = frappe.session.user
	if user == "Guest":
		raise NotLoggedIn(t("Your session has expired. Please refresh the page and sign in again.", lang))
	if frappe.get_cached_value("User", user, "user_type") != "System User":
		raise NotLoggedIn(t("You do not have permission to use the chatbot.", lang))


@frappe.whitelist(methods=["POST"], allow_guest=True)
def chat(message=None, history=None, use_llm=None):
	"""Answer a natural-language question. Never raises: always returns
	{"ok": bool, "reply": str, "blocks": [...], "lang": str, "mode": str}.
	use_llm: "1"/"0" (or omitted) lets the user force advanced AI mode or the
	built-in engine for this message; omitted keeps the admin's default."""
	lang = detect_language(frappe.utils.cstr(message), frappe.local.lang)
	try:
		_check_access(lang)
	except NotLoggedIn as e:
		return {"ok": False, "reply": str(e), "error": str(e), "lang": lang, "mode": "auth", "auth_required": True}
	return chatbot.handle_message(message, _parse_history(history), _parse_use_llm(use_llm))


@frappe.whitelist(methods=["GET"], allow_guest=True)
def get_config():
	lang = frappe.local.lang or "en"
	try:
		_check_access(lang)
	except NotLoggedIn as e:
		return {"enabled": False, "mode": "rules", "llm_available": False, "max_rows": 0, "auth_required": True, "error": str(e)}
	settings = security.get_settings()
	llm_available = security.llm_enabled(settings)
	return {
		"enabled": bool(settings.enabled),
		"mode": "llm" if llm_available else "rules",
		"llm_available": llm_available,
		"max_rows": settings.max_rows,
		"help_auto_send": bool(settings.help_auto_send),
	}


def _parse_use_llm(value):
	if value in (None, "", "null", "undefined"):
		return None
	return bool(frappe.utils.cint(value))


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
