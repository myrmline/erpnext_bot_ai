"""Guard rails. Everything the chatbot reads passes through this module.

Design rules:
  * The chatbot never builds SQL. It only calls frappe.get_list(), which applies
    role permissions, user permissions, sharing and field-level (permlevel) rules
    for the *current session user*.
  * DocTypes must be on an admin allow-list AND off a hard block-list.
  * Field names, operators and values are validated against the DocType meta.
  * There is no write/delete/submit code path anywhere in this app.
"""
import re

import frappe
from frappe.utils import (
	add_days,
	add_months,
	cint,
	get_first_day,
	get_first_day_of_week,
	get_last_day,
	getdate,
	nowdate,
)

from .messages import t

PROVIDER_BUILTIN = "Built-in (no external AI)"


class ChatbotError(Exception):
	"""Error whose message is safe to show to the end user."""


class ChatbotDenied(ChatbotError):
	"""The user (or configuration) does not allow this data to be read."""


DEFAULT_ALLOWED_DOCTYPES = [
	"Customer", "Supplier", "Item", "Item Price", "Bin", "Sales Invoice", "Purchase Invoice",
	"Sales Order", "Purchase Order", "Quotation", "Delivery Note", "Purchase Receipt",
	"Payment Entry", "Lead", "Opportunity", "Task", "Project",
]

BLOCKED_DOCTYPES = frozenset({
	"User", "Role", "Has Role", "DocPerm", "Custom DocPerm", "User Permission", "DocShare",
	"Session Default", "Session Default Settings", "OAuth Client", "OAuth Bearer Token",
	"OAuth Authorization Code", "OAuth Provider Settings", "Token Cache", "Social Login Key",
	"System Settings", "Email Account", "Email Domain", "Access Log", "Activity Log", "Error Log",
	"Scheduled Job Log", "Integration Request", "Webhook", "Webhook Request Log", "Connected App",
	"Google Settings", "LDAP Settings", "Server Script", "Client Script", "System Console",
	"Data Import", "Deleted Document", "Console Log", "API Request Log", "Prepared Report",
	"AI Chatbot Settings", "AI Chatbot Log", "Version", "Communication", "Email Queue",
})

IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SENSITIVE_FIELD = re.compile(r"(password|passwd|secret|token|api_key|private_key|otp)", re.I)

SAFE_FIELDTYPES = {
	"Data", "Link", "Dynamic Link", "Select", "Int", "Float", "Currency", "Percent", "Date",
	"Datetime", "Time", "Check", "Small Text", "Read Only", "Duration", "Rating", "Autocomplete",
	"Phone", "Text",
}
NUMERIC_TYPES = {"Int", "Float", "Currency", "Percent"}
DATE_TYPES = {"Date", "Datetime"}
GROUPABLE_TYPES = {"Link", "Select", "Data", "Date", "Check", "Int", "Dynamic Link", "Autocomplete"}

STANDARD_FIELDS = {
	"name": ("ID", "Data", None),
	"owner": ("Created By", "Link", "User"),
	"creation": ("Created On", "Datetime", None),
	"modified": ("Last Modified On", "Datetime", None),
	"docstatus": ("Document Status", "Int", None),
}

OPERATORS = {"=", "!=", ">", "<", ">=", "<=", "like", "not like", "in", "not in", "between", "is", "period"}
MAX_FILTERS = 8
MAX_LIST_VALUES = 50
MAX_VALUE_LENGTH = 200

PERIOD_TOKENS = {
	"today", "yesterday", "this_week", "last_week", "this_month", "last_month",
	"this_quarter", "this_year", "last_year", "last_7_days", "last_30_days",
}


# --------------------------------------------------------------------- config
def get_settings():
	return frappe.get_cached_doc("AI Chatbot Settings")


def llm_enabled(settings=None):
	settings = settings or get_settings()
	return bool(
		settings.provider
		and settings.provider != PROVIDER_BUILTIN
		and settings.get_password("api_key", raise_exception=False)
	)


def max_rows():
	return min(max(cint(get_settings().max_rows) or 50, 1), 500)


def set_statement_timeout(seconds=15):
	"""Best effort: stop runaway queries at the database level."""
	try:
		if frappe.db.db_type == "mariadb":
			frappe.db.sql(f"SET SESSION max_statement_time={int(seconds)}")
		elif frappe.db.db_type == "postgres":
			frappe.db.sql(f"SET statement_timeout = {int(seconds) * 1000}")
	except Exception:
		pass


# ------------------------------------------------------------------- doctypes
def configured_doctypes():
	raw = (get_settings().allowed_doctypes or "").strip() or "\n".join(DEFAULT_ALLOWED_DOCTYPES)
	out = []
	for name in re.split(r"[\n,]+", raw):
		name = name.strip()
		if not name or name in out or name in BLOCKED_DOCTYPES:
			continue
		if not frappe.db.exists("DocType", name):
			continue
		meta = frappe.get_meta(name)
		if meta.issingle or meta.istable or meta.is_virtual:
			continue
		out.append(name)
	return out


def readable_doctypes():
	"""Allow-listed DocTypes the *current user* may read."""
	return [dt for dt in configured_doctypes() if frappe.has_permission(dt, "read")]


def assert_doctype_allowed(doctype, lang="en"):
	if not isinstance(doctype, str) or doctype in BLOCKED_DOCTYPES or doctype not in configured_doctypes():
		raise ChatbotDenied(t("This data type is not available to the chatbot: {0}", lang, str(doctype)[:60]))
	if not frappe.has_permission(doctype, "read"):
		raise ChatbotDenied(t("You do not have permission to access this data.", lang))


# --------------------------------------------------------------------- fields
def field_map(doctype):
	"""{fieldname: {label, fieldtype, options}} of fields the current user may read."""
	meta = frappe.get_meta(doctype)
	try:
		levels = {cint(x) for x in meta.get_permlevel_access("read")}
	except Exception:
		levels = {0}
	out = {k: {"label": v[0], "fieldtype": v[1], "options": v[2]} for k, v in STANDARD_FIELDS.items()}
	for df in meta.fields:
		if (
			df.fieldtype not in SAFE_FIELDTYPES
			or not df.fieldname
			or not IDENT.match(df.fieldname)
			or SENSITIVE_FIELD.search(df.fieldname)
			or cint(df.permlevel) not in levels
		):
			continue
		out[df.fieldname] = {"label": df.label or df.fieldname, "fieldtype": df.fieldtype, "options": df.options}
	return out


def default_list_fields(doctype, fmap):
	meta = frappe.get_meta(doctype)
	fields = ["name"]
	for df in meta.fields:
		if df.in_list_view and df.fieldname in fmap and df.fieldname not in fields:
			fields.append(df.fieldname)
	if len(fields) < 3:
		for extra in (meta.title_field, "creation"):
			if extra and extra in fmap and extra not in fields:
				fields.append(extra)
	return fields[:7]


# -------------------------------------------------------------------- filters
def period_range(token):
	today = getdate(nowdate())
	if token == "today":
		return today, today
	if token == "yesterday":
		d = add_days(today, -1)
		return d, d
	if token == "this_week":
		start = getdate(get_first_day_of_week(today))
		return start, add_days(start, 6)
	if token == "last_week":
		start = add_days(getdate(get_first_day_of_week(today)), -7)
		return start, add_days(start, 6)
	if token == "this_month":
		return getdate(get_first_day(today)), getdate(get_last_day(today))
	if token == "last_month":
		d = add_months(today, -1)
		return getdate(get_first_day(d)), getdate(get_last_day(d))
	if token == "this_quarter":
		start = getdate(get_first_day(today.replace(month=((today.month - 1) // 3) * 3 + 1, day=1)))
		return start, getdate(get_last_day(add_months(start, 2)))
	if token == "this_year":
		return today.replace(month=1, day=1), today.replace(month=12, day=31)
	if token == "last_year":
		y = today.year - 1
		return today.replace(year=y, month=1, day=1), today.replace(year=y, month=12, day=31)
	if token == "last_7_days":
		return add_days(today, -6), today
	if token == "last_30_days":
		return add_days(today, -29), today
	raise ChatbotError("Unknown period")


def _scalar(value, lang):
	if value is None or isinstance(value, (bool, int, float)):
		return int(value) if isinstance(value, bool) else value
	if isinstance(value, str):
		if len(value) > MAX_VALUE_LENGTH:
			raise ChatbotError(t("The query is invalid.", lang))
		if value == "today":
			return nowdate()
		return value
	raise ChatbotError(t("The query is invalid.", lang))


def clean_filters(filters, fmap, lang="en"):
	"""Validate LLM/rule generated filters and turn them into frappe filter triplets."""
	if not filters:
		return []
	if not isinstance(filters, list) or len(filters) > MAX_FILTERS:
		raise ChatbotError(t("The query is invalid.", lang))
	out = []
	for f in filters:
		if isinstance(f, dict):
			field, op, value = f.get("field"), f.get("op", "="), f.get("value")
		elif isinstance(f, (list, tuple)) and len(f) == 3:
			field, op, value = f
		else:
			raise ChatbotError(t("The query is invalid.", lang))
		if not isinstance(field, str) or field not in fmap:
			raise ChatbotError(t("Unknown field: {0}", lang, str(field)[:60]))
		op = str(op).lower().strip()
		if op not in OPERATORS:
			raise ChatbotError(t("Unsupported operator: {0}", lang, op[:20]))

		if op == "period":
			if fmap[field]["fieldtype"] not in DATE_TYPES or value not in PERIOD_TOKENS:
				raise ChatbotError(t("The query is invalid.", lang))
			start, end = period_range(value)
			out.append([field, "between", [str(start), str(end)]])
		elif op in ("in", "not in"):
			if not isinstance(value, list) or not value or len(value) > MAX_LIST_VALUES:
				raise ChatbotError(t("The query is invalid.", lang))
			out.append([field, op, [_scalar(v, lang) for v in value]])
		elif op == "between":
			if not isinstance(value, list) or len(value) != 2:
				raise ChatbotError(t("The query is invalid.", lang))
			out.append([field, op, [_scalar(v, lang) for v in value]])
		elif op == "is":
			if value not in ("set", "not set"):
				raise ChatbotError(t("The query is invalid.", lang))
			out.append([field, op, value])
		else:
			value = _scalar(value, lang)
			if op in ("like", "not like") and not isinstance(value, str):
				raise ChatbotError(t("The query is invalid.", lang))
			out.append([field, op, value])
	return out
