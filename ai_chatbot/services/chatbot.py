"""Chatbot service: question -> plan -> permission-checked execution -> answer."""
import json
import time

import frappe
from frappe.utils import cint, cstr

from . import intents, llm, query_engine, security
from .messages import detect_language, t

MAX_QUESTION_LENGTH = 500


def _log():
	return frappe.logger("ai_chatbot", allow_site=True, file_count=5)


def handle_message(message, history=None, use_llm=None):
	"""use_llm: None = use the admin's configured default (existing behaviour).
	True = the user asked for advanced AI mode for this message.
	False = the user asked to force the built-in, offline engine for this message."""
	started = time.monotonic()
	user = frappe.session.user
	settings = security.get_settings()
	lang = detect_language(cstr(message), frappe.local.lang)
	out = {"ok": False, "reply": "", "blocks": [], "lang": lang, "mode": "rules"}
	status, error, plan, rows = "Error", "", None, 0

	try:
		message = cstr(message).strip()
		if not settings.enabled:
			raise security.ChatbotDenied(t("The chatbot is disabled. Please contact your administrator.", lang))
		if not message:
			raise security.ChatbotError(t("Please enter a question.", lang))
		if len(message) > MAX_QUESTION_LENGTH:
			raise security.ChatbotError(t("The question is too long.", lang))
		_check_rate_limit(settings, lang)
		security.set_statement_timeout()

		plan, mode, notice = _make_plan(message, history, settings, lang, use_llm)
		out["mode"] = mode

		if not plan.get("steps"):
			reply = cstr(plan.get("reply") or t("No results found.", lang))[:1000]
			out.update(ok=True, reply=_prefix(notice, reply))
			status = "Success"
		else:
			try:
				result = query_engine.execute_plan(plan, lang)
			except security.ChatbotDenied:
				raise
			except security.ChatbotError:
				# an LLM plan may be malformed: fall back to the built-in rules once
				fallback = intents.build_plan(message, lang) if mode == "llm" else None
				if not fallback or not fallback.get("steps"):
					raise
				plan, out["mode"] = fallback, "rules"
				result = query_engine.execute_plan(plan, lang)

			text = result["text"]
			if out["mode"] == "llm" and settings.llm_summarize and result["blocks"]:
				text = llm.summarize(message, result["blocks"], lang) or text
			rows = result["rows"]
			out.update(ok=True, reply=_prefix(notice, text), blocks=result["blocks"])
			status = "Success"

	except security.ChatbotDenied as e:
		status, error = "Denied", str(e)
		out["reply"] = str(e)
	except security.ChatbotError as e:
		error = str(e)
		out["reply"] = str(e)
	except frappe.PermissionError:
		status, error = "Denied", "PermissionError"
		out["reply"] = t("You do not have permission to access this data.", lang)
	except Exception:
		error = "Unexpected error"
		frappe.log_error(title="AI Chatbot error", message=frappe.get_traceback())
		out["reply"] = t("Something went wrong while processing your request. Please try again.", lang)
	finally:
		duration = int((time.monotonic() - started) * 1000)
		_log().info(f"user={user} status={status} mode={out['mode']} lang={lang} rows={rows} ms={duration}")
		_audit(settings, user, message, lang, out["mode"], plan, status, rows, duration, error)

	if not out["ok"]:
		out["error"] = out["reply"]
	return out


def _prefix(notice, text):
	return f"{notice}\n\n{text}" if notice else text


def _make_plan(message, history, settings, lang, use_llm):
	"""Returns (plan, mode, notice). `mode` is what actually answered the
	question ("llm" or "rules"); `notice` is an optional user-facing heads-up,
	e.g. when advanced AI mode was requested but isn't configured."""
	available = security.llm_enabled(settings)
	notice = None

	if use_llm is False:
		want_llm = False
	elif use_llm is True:
		want_llm = available
		if not available:
			notice = t(
				"Advanced AI mode is not configured by your administrator. Answering with the built-in engine instead.",
				lang,
			)
	else:  # use_llm is None: fall back to the admin's configured default
		want_llm = available

	if want_llm:
		try:
			plan = llm.plan(message, history, lang)
			if plan.get("steps") or plan.get("reply"):
				return plan, "llm", notice
		except llm.LLMError as e:
			_log().warning(f"LLM planning failed, using built-in rules: {e}")
			if use_llm is True:
				notice = t(
					"Advanced AI mode is temporarily unavailable. Answering with the built-in engine instead.",
					lang,
				)

	plan = intents.build_plan(message, lang)
	if plan:
		return plan, "rules", notice
	return {"steps": [], "reply": t(
		"Sorry, I did not understand that question. Try for example: Show me today's sales, How many customers do we have?, What are the unpaid invoices?",
		lang)}, "rules", notice


def _check_rate_limit(settings, lang):
	limit = cint(settings.rate_limit_per_minute) or 20
	key = f"ai_chatbot:rl:{frappe.session.user}:{int(time.time() // 60)}"
	cache = frappe.cache() if callable(frappe.cache) else frappe.cache
	count = cint(cache.get_value(key)) + 1
	cache.set_value(key, count, expires_in_sec=90)
	if count > limit:
		raise security.ChatbotError(t("You are sending messages too fast. Please wait a moment.", lang))


def _audit(settings, user, message, lang, mode, plan, status, rows, duration, error):
	if not settings.enable_audit_log:
		return
	try:
		frappe.get_doc({
			"doctype": "AI Chatbot Log",
			"user": user,
			"status": status,
			"mode": mode,
			"language": lang,
			"question": cstr(message)[:500],
			"plan": json.dumps(plan, ensure_ascii=False, default=str) if plan else None,
			"row_count": rows,
			"duration_ms": duration,
			"error": cstr(error)[:500],
		}).insert(ignore_permissions=True)  # system audit record only; never user-supplied data access
	except Exception:
		frappe.log_error(title="AI Chatbot audit log failed", message=frappe.get_traceback())
