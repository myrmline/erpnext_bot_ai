"""Help / example-question API. Only serves examples; never executes queries.
allow_guest=True for the same reason as ai_chatbot.api.chat/get_config: an
expired session must produce our own clean JSON answer, not a raw Frappe
dispatch error (see the comment at the top of ai_chatbot/api/__init__.py).

Browsing the question list only needs a logged-in user - not a full Desk /
System User - because it never touches data by itself. Each question is
annotated with "allowed" (whether *this* user can currently read that
DocType), but nothing is hidden: if the user picks a question they are not
allowed to run, ai_chatbot.api.chat is what actually enforces the
permission and answers with a clear denial, not this endpoint."""
import frappe

from ai_chatbot.services import help_service
from ai_chatbot.services.messages import t


@frappe.whitelist(methods=["GET"], allow_guest=True)
def get_questions(language=None, category=None, search=None):
	"""Localized example questions, annotated with per-user access hints.

	GET /api/method/ai_chatbot.api.help.get_questions?language=fr&category=sales&search=stock
	"""
	lang = language or frappe.local.lang or "en"
	if frappe.session.user == "Guest":
		empty = {"language": lang, "languages": [], "featured": [], "all_categories": [], "categories": [], "total": 0}
		return {**empty, "auth_required": True, "error": t("Your session has expired. Please refresh the page and sign in again.", lang)}
	return help_service.get_questions(language, category, search)

