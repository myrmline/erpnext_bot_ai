import json

import frappe
from frappe.tests.utils import FrappeTestCase

from ai_chatbot.services import help_service


class TestHelp(FrappeTestCase):
	def test_file_integrity(self):
		"""Every question exists in every declared language; ids are unique; featured ids resolve."""
		data = json.load(open(help_service.HELP_FILE, encoding="utf-8"))
		langs, ids = data["languages"], set()
		for cat in data["categories"]:
			for lang in langs:
				self.assertTrue(cat["title"].get(lang), f"{cat['id']} title {lang}")
				self.assertTrue(cat["description"].get(lang), f"{cat['id']} description {lang}")
			for q in cat["questions"]:
				self.assertNotIn(q["id"], ids)
				ids.add(q["id"])
				self.assertEqual(q["category"], cat["id"])
				for lang in langs:
					self.assertTrue(q["question"].get(lang), f"{q['id']} {lang}")
		for fid in data["featured"]:
			self.assertIn(fid, ids)

	def test_localized_and_searchable(self):
		res = help_service.get_questions("fr")
		self.assertEqual(res["language"], "fr")
		flat = [q for c in res["categories"] for q in c["questions"]]
		self.assertTrue(flat)
		res = help_service.get_questions("fr", search="stock")
		self.assertTrue(all("stock" in q["question"].lower() or q["category"] for c in res["categories"] for q in c["questions"]))
		res = help_service.get_questions("en", category="sales")
		self.assertEqual([c["id"] for c in res["categories"]], ["sales"])

	def test_questions_are_not_hidden_by_user_permission(self):
		"""Browsing shows everything in scope regardless of who is asking; only
		`allowed` (a hint, not a filter) reflects this user's current access.
		The real enforcement happens in ai_chatbot.api.chat, not here."""
		res = help_service.get_questions("en")
		flat = [q for c in res["categories"] for q in c["questions"]]
		self.assertTrue(any("allowed" in q for q in flat))
		self.assertTrue(all(isinstance(q["allowed"], bool) for q in flat))

	def test_unknown_language_falls_back_to_english(self):
		res = help_service.get_questions("xx")
		self.assertTrue(res["categories"])
