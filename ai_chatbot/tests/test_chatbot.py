import frappe
from frappe.tests.utils import FrappeTestCase

from ai_chatbot.services import intents, security
from ai_chatbot.services.messages import detect_language, normalize


class TestChatbot(FrappeTestCase):
	def test_language_detection(self):
		self.assertEqual(detect_language("كم عدد العملاء لدينا؟"), "ar")
		self.assertEqual(detect_language("Combien de clients avons-nous ?"), "fr")
		self.assertEqual(detect_language("How many customers do we have?"), "en")

	def test_normalize_arabic(self):
		self.assertEqual(normalize("أمس"), normalize("امس"))

	def test_intents_multilingual(self):
		cases = {
			"Show me today's sales.": ("aggregate", "Sales Invoice"),
			"Montre-moi les ventes d'aujourd'hui": ("aggregate", "Sales Invoice"),
			"اعرض مبيعات اليوم": ("aggregate", "Sales Invoice"),
			"How many customers do we have?": ("count", "Customer"),
			"Combien de clients avons-nous ?": ("count", "Customer"),
			"كم عدد العملاء لدينا؟": ("count", "Customer"),
			"What are the unpaid invoices?": ("aggregate", "Sales Invoice"),
			"ما هي الفواتير غير المدفوعة؟": ("aggregate", "Sales Invoice"),
			"Give me a summary of this month's purchases": ("aggregate", "Purchase Invoice"),
			"Show the stock status.": ("aggregate", "Bin"),
		}
		for question, (tool, doctype) in cases.items():
			step = intents.build_plan(question, detect_language(question))["steps"][0]
			self.assertEqual((step["tool"], step["doctype"]), (tool, doctype), question)

	def test_filters_reject_unknown_fields_and_ops(self):
		fmap = security.field_map("Customer")
		with self.assertRaises(security.ChatbotError):
			security.clean_filters([{"field": "password", "op": "=", "value": "x"}], fmap)
		with self.assertRaises(security.ChatbotError):
			security.clean_filters([{"field": "name", "op": "; DROP TABLE", "value": "x"}], fmap)

	def test_blocked_doctype(self):
		with self.assertRaises(security.ChatbotDenied):
			security.assert_doctype_allowed("User")
