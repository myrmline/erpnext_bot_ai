"""Built-in, offline question understanding for English, French and Arabic.

It only produces *plans* (see query_engine.py); the plans go through exactly the
same validation and permission checks as plans produced by an LLM."""
from frappe import _

from .messages import normalize, t


def _k(*words):
	return tuple(normalize(w) for w in words)


def _has(text, kws):
	return any(k in text for k in kws)


GREETINGS = _k("hi", "hello", "hey", "help", "bonjour", "salut", "bonsoir", "aide", "مرحبا", "اهلا", "السلام عليكم", "مساعدة")
COUNT_KW = _k("how many", "combien", "nombre", "number of", "count", "كم", "عدد")
UNPAID_KW = _k("unpaid", "outstanding", "overdue", "not paid", "impaye", "non paye", "en retard", "retard", "غير مدفوع", "غير المدفوع", "غير مسدد", "غير المسدد", "مستحق", "متأخر", "متاخر")
OVERDUE_KW = _k("overdue", "en retard", "retard", "متأخر", "متاخر")
STOCK_KW = _k("stock", "inventory", "inventaire", "مخزون", "المخزون", "رصيد")
TOP_KW = _k("top", "best", "biggest", "meilleur", "meilleurs", "principaux", "أفضل", "اكثر", "أكثر", "أكبر")
SALES_KW = _k("sales", "sale", "revenue", "turnover", "vente", "ventes", "chiffre d affaires", "مبيعات", "المبيعات", "إيرادات")
PURCHASE_KW = _k("purchase", "purchases", "buying", "achat", "achats", "مشتريات", "المشتريات", "شراء")
SUPPLIER_KW = _k("supplier", "suppliers", "fournisseur", "fournisseurs", "مورد", "موردين", "موردون")
INVOICE_KW = _k("invoice", "invoices", "facture", "factures", "فاتورة", "فواتير")

PERIODS = [
	("yesterday", _k("yesterday", "hier", "أمس")),
	("today", _k("today", "aujourd hui", "aujourdhui", "اليوم")),
	("last_week", _k("last week", "semaine derniere", "semaine passee", "الأسبوع الماضي", "الأسبوع الفائت")),
	("this_week", _k("this week", "cette semaine", "هذا الأسبوع", "الأسبوع الحالي")),
	("last_month", _k("last month", "mois dernier", "dernier mois", "mois precedent", "الشهر الماضي", "الشهر الفائت", "الشهر السابق")),
	("this_month", _k("this month", "ce mois", "mois en cours", "هذا الشهر", "الشهر الحالي")),
	("last_year", _k("last year", "annee derniere", "l annee passee", "السنة الماضية", "العام الماضي")),
	("this_year", _k("this year", "cette annee", "annee en cours", "هذه السنة", "هذا العام", "السنة الحالية")),
	("last_7_days", _k("last 7 days", "7 derniers jours", "آخر 7 أيام")),
	("last_30_days", _k("last 30 days", "30 derniers jours", "آخر 30 يوم")),
	("this_month", _k("month", "mois", "شهر")),
	("this_year", _k("year", "annee", "سنة", "عام")),
]

PERIOD_LABELS = {
	"today": "Today", "yesterday": "Yesterday", "this_week": "This week", "last_week": "Last week",
	"this_month": "This month", "last_month": "Last month", "this_quarter": "This quarter",
	"this_year": "This year", "last_year": "Last year", "last_7_days": "Last 7 days", "last_30_days": "Last 30 days",
}

DATE_FIELDS = {
	"Sales Invoice": "posting_date", "Purchase Invoice": "posting_date", "Delivery Note": "posting_date",
	"Purchase Receipt": "posting_date", "Payment Entry": "posting_date", "Sales Order": "transaction_date",
	"Purchase Order": "transaction_date", "Quotation": "transaction_date",
}

ENTITIES = [
	("Sales Invoice", ["sales invoice", "sales invoices", "facture de vente", "factures de vente", "facture client", "factures clients", "فاتورة مبيعات", "فواتير المبيعات", "فواتير مبيعات"]),
	("Purchase Invoice", ["purchase invoice", "purchase invoices", "facture d achat", "factures d achat", "facture fournisseur", "factures fournisseurs", "فاتورة شراء", "فواتير الشراء", "فواتير المشتريات", "فاتورة مشتريات"]),
	("Sales Order", ["sales order", "sales orders", "commande client", "commandes clients", "commande de vente", "commandes de vente", "أمر بيع", "أوامر البيع", "اوامر بيع"]),
	("Purchase Order", ["purchase order", "purchase orders", "commande fournisseur", "commandes fournisseurs", "commande d achat", "commandes d achat", "أمر شراء", "أوامر الشراء", "اوامر شراء"]),
	("Delivery Note", ["delivery note", "delivery notes", "bon de livraison", "bons de livraison", "إذن تسليم", "اذون التسليم", "إذون التسليم"]),
	("Purchase Receipt", ["purchase receipt", "purchase receipts", "bon de reception", "bons de reception", "إذن استلام", "اذون الاستلام"]),
	("Quotation", ["quotation", "quotations", "devis", "عرض سعر", "عروض الأسعار", "عروض الاسعار"]),
	("Payment Entry", ["payment entry", "payment entries", "payment", "payments", "paiement", "paiements", "دفعة", "دفعات", "مدفوعات"]),
	("Customer", ["customer", "customers", "client", "clients", "عميل", "عملاء", "زبون", "زبائن"]),
	("Supplier", ["supplier", "suppliers", "fournisseur", "fournisseurs", "مورد", "موردين", "موردون"]),
	("Item", ["item", "items", "product", "products", "article", "articles", "produit", "produits", "صنف", "أصناف", "اصناف", "منتج", "منتجات"]),
	("Lead", ["lead", "leads", "prospect", "prospects", "عميل محتمل", "عملاء محتملين"]),
	("Opportunity", ["opportunity", "opportunities", "opportunite", "opportunites", "فرصة", "فرص"]),
	("Task", ["task", "tasks", "tache", "taches", "مهمة", "مهام"]),
	("Project", ["project", "projects", "projet", "projets", "مشروع", "مشاريع"]),
]
_ENTITY_INDEX = sorted(
	((normalize(s), dt) for dt, syns in ENTITIES for s in syns), key=lambda x: len(x[0]), reverse=True
)


def detect_period(text):
	for token, kws in PERIODS:
		if _has(text, kws):
			return token
	return None


def detect_entity(text):
	for syn, dt in _ENTITY_INDEX:
		if syn in text:
			return dt
	if _has(text, INVOICE_KW):
		return "Purchase Invoice" if (_has(text, PURCHASE_KW) or _has(text, SUPPLIER_KW)) else "Sales Invoice"
	return None


def _period_filter(doctype, period):
	return [{"field": DATE_FIELDS.get(doctype, "creation"), "op": "period", "value": period}] if period else []


def _plabel(period, lang):
	return t(PERIOD_LABELS[period], lang)


# ------------------------------------------------------------------- plans
def _summary(doctype, party, kind_title, top_title, period, lang):
	filters = [{"field": "docstatus", "op": "=", "value": 1}, {"field": "posting_date", "op": "period", "value": period}]
	steps = [{
		"tool": "aggregate", "doctype": doctype, "metric": "sum", "field": "base_grand_total", "filters": filters,
		"title": f"{t(kind_title, lang)} – {_plabel(period, lang)}",
	}]
	if period in ("today", "yesterday"):
		steps.append({
			"tool": "list", "doctype": doctype, "fields": ["name", party, "posting_date", "currency", "grand_total", "status"],
			"filters": filters, "order_by": {"field": "creation", "direction": "desc"}, "limit": 20,
			"title": t("Latest {0}", lang, _(doctype, lang=lang)),
		})
	else:
		steps.append({
			"tool": "aggregate", "doctype": doctype, "metric": "sum", "field": "base_grand_total", "group_by": party,
			"filters": filters, "order": "desc", "limit": 10, "title": t(top_title, lang),
		})
	return {"steps": steps}


def _unpaid(text, lang):
	purchase = _has(text, PURCHASE_KW) or _has(text, SUPPLIER_KW)
	doctype, party = ("Purchase Invoice", "supplier") if purchase else ("Sales Invoice", "customer")
	overdue = _has(text, OVERDUE_KW)
	filters = [{"field": "docstatus", "op": "=", "value": 1}, {"field": "outstanding_amount", "op": ">", "value": 0}]
	if overdue:
		filters.append({"field": "due_date", "op": "<", "value": "today"})
	title = t(("Overdue " if overdue else "Unpaid ") + ("purchase" if purchase else "sales") + " invoices", lang)
	return {"steps": [
		{"tool": "aggregate", "doctype": doctype, "metric": "sum", "field": "outstanding_amount", "filters": filters, "title": title},
		{"tool": "list", "doctype": doctype, "fields": ["name", party, "posting_date", "due_date", "currency", "grand_total", "outstanding_amount"],
		 "filters": filters, "order_by": {"field": "due_date", "direction": "asc"}, "limit": 20, "title": title},
	]}


def _stock(lang):
	return {"steps": [
		{"tool": "aggregate", "doctype": "Bin", "metric": "sum", "field": "actual_qty", "group_by": "item_code",
		 "filters": [{"field": "actual_qty", "op": ">", "value": 0}], "order": "desc", "limit": 20, "title": t("Stock by item", lang)},
		{"tool": "count", "doctype": "Bin", "filters": [{"field": "actual_qty", "op": "<=", "value": 0}],
		 "title": t("Stock lines at zero or negative quantity", lang)},
	]}


def build_plan(message, lang="en"):
	text = normalize(message)
	if not text:
		return None
	period = detect_period(text)
	entity = detect_entity(text)

	if text in GREETINGS or (len(text.split()) <= 2 and _has(text, GREETINGS)):
		return {"steps": [], "reply": t("Hello! I can answer questions about your ERPNext data. Try one of the examples below.", lang)}

	if _has(text, UNPAID_KW):
		return _unpaid(text, lang)
	if _has(text, STOCK_KW) and entity in (None, "Item"):
		return _stock(lang)

	if _has(text, TOP_KW) and entity in ("Customer", "Supplier"):
		doctype, party, title = ("Purchase Invoice", "supplier", "Top suppliers by purchases") if entity == "Supplier" else ("Sales Invoice", "customer", "Top customers by sales")
		filters = [{"field": "docstatus", "op": "=", "value": 1}] + _period_filter(doctype, period)
		return {"steps": [{"tool": "aggregate", "doctype": doctype, "metric": "sum", "field": "base_grand_total", "group_by": party,
						   "filters": filters, "order": "desc", "limit": 10, "title": t(title, lang)}]}

	if entity:
		filters = _period_filter(entity, period)
		if _has(text, COUNT_KW):
			return {"steps": [{"tool": "count", "doctype": entity, "filters": filters}]}
		return {"steps": [{"tool": "list", "doctype": entity, "filters": filters, "limit": 20,
						   "order_by": {"field": "creation", "direction": "desc"}}]}

	if _has(text, SALES_KW):
		return _summary("Sales Invoice", "customer", "Sales", "Top customers by sales", period or "this_month", lang)
	if _has(text, PURCHASE_KW):
		return _summary("Purchase Invoice", "supplier", "Purchases", "Top suppliers by purchases", period or "this_month", lang)
	return None
