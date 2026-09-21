import re

import frappe
from frappe import _
from frappe.model.document import Document

from ai_chatbot.services.security import BLOCKED_DOCTYPES


class AIChatbotSettings(Document):
	def validate(self):
		self.max_rows = min(max(int(self.max_rows or 50), 1), 500)
		self.rate_limit_per_minute = min(max(int(self.rate_limit_per_minute or 20), 1), 600)

		clean = []
		for name in re.split(r"[\n,]+", self.allowed_doctypes or ""):
			name = name.strip()
			if not name or name in clean:
				continue
			if name in BLOCKED_DOCTYPES:
				frappe.msgprint(_("{0} is a protected DocType and cannot be queried by the chatbot.").format(name), alert=True)
				continue
			if not frappe.db.exists("DocType", name):
				frappe.msgprint(_("DocType {0} does not exist and was removed.").format(name), alert=True)
				continue
			clean.append(name)
		self.allowed_doctypes = "\n".join(clean)
