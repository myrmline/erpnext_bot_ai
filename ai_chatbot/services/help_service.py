"""Loads help/questions.json (cached), localizes it, filters it and searches it.

The Help content is pure data. Nothing here executes queries or business logic:
questions only ever get typed into the chat box and go through the normal
plan -> validation -> permission pipeline."""
import json
import os

import frappe

from . import security
from .messages import normalize

HELP_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "help", "questions.json")
CACHE_KEY = "ai_chatbot:help:questions"
MAX_SEARCH_LENGTH = 100


def _cache():
	return frappe.cache() if callable(frappe.cache) else frappe.cache


def clear_cache():
	_cache().delete_value(CACHE_KEY)


def load():
	"""Parsed help file. Cached in Redis and invalidated automatically when the file changes."""
	mtime = os.path.getmtime(HELP_FILE)
	cached = _cache().get_value(CACHE_KEY)
	if cached and cached.get("mtime") == mtime:
		return cached["data"]
	with open(HELP_FILE, encoding="utf-8") as f:
		data = json.load(f)
	_cache().set_value(CACHE_KEY, {"mtime": mtime, "data": data})
	return data


def _chain(language):
	lang = (language or frappe.local.lang or "en").replace("_", "-")
	chain = [lang, lang.split("-")[0], "en"]
	return list(dict.fromkeys(chain))


def _loc(value, chain):
	"""Pick the best translation from {lang: text}, falling back along the chain."""
	if isinstance(value, str):
		return value
	if not isinstance(value, dict):
		return ""
	for code in chain:
		if value.get(code):
			return value[code]
	return next((v for v in value.values() if v), "")


def _keywords(value, chain):
	if isinstance(value, list):
		return [str(k) for k in value]
	if isinstance(value, dict):
		return [str(k) for code in chain for k in (value.get(code) or [])]
	return []


def _languages(data):
	out = []
	for code in data.get("languages") or ["en"]:
		row = frappe.db.get_value("Language", code, ["language_name", "enabled"], as_dict=True) if frappe.db.exists("Language", code) else None
		if row and not row.enabled and code != "en":
			continue
		out.append({"code": code, "name": (row.language_name if row else None) or code})
	return out


def get_questions(language=None, category=None, search=None):
	"""Everything in scope (the DocType allow-list) is shown to every user, so the
	Help browser is a full, honest menu of what the chatbot can do. Whether *this*
	user can currently get data for a given question is only a hint here
	(`allowed`); the real, enforced check happens when the question is actually
	sent to ai_chatbot.api.chat, which always re-checks permissions itself and
	answers with a clear "you do not have permission" message if denied."""
	data = load()
	chain = _chain(language)
	configured = set(security.configured_doctypes())  # in scope for the chatbot at all
	readable = set(security.readable_doctypes())  # additionally readable by *this* user right now
	tokens = normalize(str(search or "")[:MAX_SEARCH_LENGTH]).split()

	visible, by_id = [], {}
	for cat in data.get("categories", []):
		if cat.get("enabled") is False:
			continue
		title, desc = _loc(cat.get("title"), chain), _loc(cat.get("description"), chain)
		cat_kw = _keywords(cat.get("keywords"), chain)
		questions = []
		for q in cat.get("questions", []):
			if q.get("enabled") is False:
				continue
			doctype = q.get("doctype") or cat.get("doctype")
			if doctype and doctype not in configured:  # out of scope for the chatbot entirely, for anyone
				continue
			text = _loc(q.get("question"), chain)
			if not text:
				continue
			kws = _keywords(q.get("keywords"), chain)
			item = {
				"id": q["id"], "category": cat["id"], "question": text, "keywords": kws,
				"intent": q.get("intent"), "doctype": doctype,
				"allowed": (not doctype) or doctype in readable,
				"_hay": normalize(" ".join([text, title, desc, *cat_kw, *kws])),
			}
			questions.append(item)
			by_id[q["id"]] = item
		if questions:
			visible.append({"id": cat["id"], "icon": cat.get("icon"), "title": title, "description": desc, "questions": questions})

	featured = [{"id": i, "question": by_id[i]["question"]} for i in data.get("featured", []) if i in by_id]

	categories = []
	for cat in visible:
		if category and cat["id"] != category:
			continue
		qs = [q for q in cat["questions"] if all(t in q["_hay"] for t in tokens)] if tokens else cat["questions"]
		if qs:
			categories.append({**cat, "questions": [{k: v for k, v in q.items() if k != "_hay"} for q in qs]})

	return {
		"language": chain[0],
		"languages": _languages(data),
		"featured": featured,
		"all_categories": [{"id": c["id"], "icon": c["icon"], "title": c["title"]} for c in visible],
		"categories": categories,
		"total": sum(len(c["questions"]) for c in categories),
	}
