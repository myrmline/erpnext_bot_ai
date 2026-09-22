"""Executes validated query plans with frappe.get_list (permission-checked).

A plan is a dict: {"steps": [step, ...]} where each step is one of
  {"tool": "count",     "doctype", "filters", "title"}
  {"tool": "list",      "doctype", "fields", "filters", "order_by", "limit", "title"}
  {"tool": "aggregate", "doctype", "metric", "field", "group_by", "filters", "order", "limit", "title"}
Nothing else can be executed.
"""
import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, fmt_money, formatdate

from . import security
from .messages import t
from .security import ChatbotError

MAX_STEPS = 4
METRICS = {"count", "sum", "avg", "min", "max"}
METRIC_LABELS = {"sum": "Total", "avg": "Average", "min": "Minimum", "max": "Maximum", "count": "Count"}


def execute_plan(plan, lang="en"):
	steps = plan.get("steps") if isinstance(plan, dict) else None
	if not isinstance(steps, list) or not steps:
		raise ChatbotError(t("The query is invalid.", lang))
	if len(steps) > MAX_STEPS:
		raise ChatbotError(t("The request is too complex.", lang))
	blocks, lines, rows = [], [], 0
	for step in steps:
		res = _run_step(step, lang)
		blocks.extend(res["blocks"])
		lines.extend(res["lines"])
		rows += res["rows"]
	return {"blocks": blocks, "text": "\n".join(lines), "rows": rows}


def _run_step(step, lang):
	if not isinstance(step, dict):
		raise ChatbotError(t("The query is invalid.", lang))
	handler = TOOLS.get(step.get("tool"))
	if not handler:
		raise ChatbotError(t("Unsupported operation: {0}", lang, cstr(step.get("tool"))[:40]))
	doctype = step.get("doctype")
	security.assert_doctype_allowed(doctype, lang)
	fmap = security.field_map(doctype)
	filters = security.clean_filters(step.get("filters"), fmap, lang)
	return handler(doctype, fmap, filters, step, lang)


# ------------------------------------------------------------------ helpers
def _title(step):
	return cstr(step.get("title") or "").strip()[:120]


def _currency():
	return frappe.defaults.get_global_default("currency")


def _money(value):
	return fmt_money(flt(value), currency=_currency())


def _fmt_cell(value, fieldtype):
	if value is None or value == "":
		return ""
	if fieldtype in ("Currency", "Float", "Percent"):
		return f"{flt(value):,.2f}"
	if fieldtype == "Int":
		return f"{cint(value):,}"
	if fieldtype == "Date":
		return formatdate(value)
	if fieldtype == "Datetime":
		return cstr(value)[:16]
	if fieldtype == "Check":
		return "✓" if cint(value) else "—"
	return cstr(value)


def _col(fieldname, fmap, doctype, lang):
	info = fmap[fieldname]
	link = None
	if fieldname == "name":
		link = doctype
	elif info["fieldtype"] == "Link" and info.get("options") and frappe.db.exists("DocType", info["options"]):
		link = info["options"]
	return {
		"fieldname": fieldname,
		"label": _(info["label"], lang=lang),
		"fieldtype": info["fieldtype"],
		"link": link,
	}


def _count_docs(doctype, filters):
	rows = frappe.get_list(
		doctype, filters=filters, fields=["count(name) as count"], limit_page_length=1,
		ignore_permissions=security.is_super(),
	)
	return cint(rows[0].get("count")) if rows else 0


def _table(title, columns, rows, footer=None):
	return {"type": "table", "title": title, "columns": columns, "rows": rows, "footer": footer}


def _stats(title, items):
	return {"type": "stats", "title": title, "items": items}


def _limit(step, default):
	return max(1, min(cint(step.get("limit")) or default, security.max_rows()))


# -------------------------------------------------------------------- tools
def _count(doctype, fmap, filters, step, lang):
	n = _count_docs(doctype, filters)
	title = _title(step) or _(doctype, lang=lang)
	return {
		"blocks": [_stats(None, [{"label": title, "value": f"{n:,}"}])],
		"lines": [f"{title}: **{n:,}**"],
		"rows": 1,
	}


def _list(doctype, fmap, filters, step, lang):
	requested = step.get("fields")
	fields = ["name"]
	for f in (requested if isinstance(requested, list) and requested else security.default_list_fields(doctype, fmap)):
		if not isinstance(f, str) or f not in fmap:
			raise ChatbotError(t("Unknown field: {0}", lang, cstr(f)[:60]))
		if f not in fields:
			fields.append(f)
	fields = fields[:10]

	order = step.get("order_by") if isinstance(step.get("order_by"), dict) else {}
	ofield = order.get("field") or "modified"
	if ofield != "modified" and ofield not in fmap:
		raise ChatbotError(t("Unknown field: {0}", lang, cstr(ofield)[:60]))
	direction = "asc" if cstr(order.get("direction")).lower() == "asc" else "desc"

	limit = _limit(step, 20)
	rows = frappe.get_list(
		doctype,
		fields=fields,
		filters=filters,
		order_by=f"`tab{doctype}`.`{ofield}` {direction}",
		limit_page_length=limit,
		ignore_permissions=security.is_super(),
	)
	total = _count_docs(doctype, filters)
	title = _title(step) or _(doctype, lang=lang)
	if not rows:
		return {"blocks": [], "lines": [f"{title}: {t('No results found.', lang)}"], "rows": 0}

	columns = [_col(f, fmap, doctype, lang) for f in fields]
	data = [[_fmt_cell(r.get(f), fmap[f]["fieldtype"]) for f in fields] for r in rows]
	footer = t("Showing {0} of {1}", lang, len(rows), total)
	return {
		"blocks": [_table(title, columns, data, footer)],
		"lines": [f"{title}: {footer}"],
		"rows": len(rows),
	}


def _aggregate(doctype, fmap, filters, step, lang):
	metric = cstr(step.get("metric") or "sum").lower()
	if metric not in METRICS:
		raise ChatbotError(t("Unsupported operation: {0}", lang, metric[:20]))
	field = step.get("field")
	if metric == "count":
		expr, field = "count(name)", None
	else:
		if not isinstance(field, str) or field not in fmap or fmap[field]["fieldtype"] not in security.NUMERIC_TYPES:
			raise ChatbotError(t("Field is not numeric: {0}", lang, cstr(field)[:60]))
		expr = f"{metric}({field})"

	group_by = step.get("group_by") or None
	if group_by and (
		not isinstance(group_by, str)
		or group_by not in fmap
		or (group_by != "name" and fmap[group_by]["fieldtype"] not in security.GROUPABLE_TYPES)
	):
		raise ChatbotError(t("Unknown field: {0}", lang, cstr(group_by)[:60]))

	value_label = t(METRIC_LABELS[metric], lang) + (f" {_(fmap[field]['label'], lang=lang)}" if field else "")
	is_money = bool(field) and fmap[field]["fieldtype"] == "Currency"

	def show(v):
		if is_money:
			return _money(v)
		return f"{flt(v):,.2f}".rstrip("0").rstrip(".") if field else f"{cint(v):,}"

	if not group_by:
		rows = frappe.get_list(
			doctype, filters=filters, fields=[f"{expr} as value", "count(name) as doc_count"], limit_page_length=1,
			ignore_permissions=security.is_super(),
		)
		row = rows[0] if rows else {}
		value, n = row.get("value") or 0, cint(row.get("doc_count"))
		title = _title(step) or value_label
		return {
			"blocks": [_stats(None, [{"label": title, "value": show(value)}, {"label": t("Documents", lang), "value": f"{n:,}"}])],
			"lines": [t("{0}: **{1}** ({2} documents)", lang, title, show(value), n)],
			"rows": 1,
		}

	rows = frappe.get_list(
		doctype,
		filters=filters,
		fields=[group_by, f"{expr} as value", "count(name) as doc_count"],
		group_by=group_by,
		limit_page_length=5000,
		ignore_permissions=security.is_super(),
	)
	title = _title(step) or f"{value_label} — {_(fmap[group_by]['label'], lang=lang)}"
	if not rows:
		return {"blocks": [], "lines": [f"{title}: {t('No results found.', lang)}"], "rows": 0}
	rows.sort(key=lambda r: flt(r.get("value")), reverse=cstr(step.get("order")).lower() != "asc")
	top = rows[: _limit(step, 10)]

	gcol = _col(group_by, fmap, doctype, lang)
	columns = [
		gcol,
		{"fieldname": "value", "label": value_label, "fieldtype": "Currency" if is_money else "Float", "link": None},
		{"fieldname": "doc_count", "label": t("Documents", lang), "fieldtype": "Int", "link": None},
	]
	data = [
		[_fmt_cell(r.get(group_by), fmap[group_by]["fieldtype"]) or "—", _fmt_cell(r.get("value"), "Currency"), _fmt_cell(r.get("doc_count"), "Int")]
		for r in top
	]
	footer = t("Showing {0} of {1}", lang, len(top), len(rows))
	lines = [f"{title}: {footer}", t("Highest: {0} ({1})", lang, data[0][0], show(top[0].get("value")))]
	return {"blocks": [_table(title, columns, data, footer)], "lines": lines, "rows": len(top)}


TOOLS = {"count": _count, "list": _list, "aggregate": _aggregate}
