"""Language helpers. Bot strings use Frappe's translation system
(see ai_chatbot/translations/ar.csv and fr.csv), but are rendered in the
language of the *question*, not necessarily the desk language."""
import re
import unicodedata

from frappe import _

SUPPORTED_LANGS = ("en", "fr", "ar")

_ARABIC = re.compile(r"[\u0600-\u06FF]")
_FRENCH_ACCENTS = re.compile(r"[éèêëàâçùûôîïœ]")
_FRENCH_WORDS = {
	"combien", "montre", "montrer", "montre-moi", "affiche", "afficher", "donne", "donne-moi", "quel",
	"quels", "quelle", "quelles", "sont", "les", "des", "nous", "avons", "clients", "client", "fournisseurs",
	"factures", "facture", "ventes", "vente", "achats", "achat", "aujourd", "hui", "ce", "cette", "mois",
	"semaine", "annee", "année", "impayees", "impayées", "impaye", "liste", "resume", "résumé", "etat", "état",
	"je", "moi", "mes", "mon", "hier", "bonjour", "salut", "le", "la", "du", "de",
}


def normalize(text):
	"""Lowercase, strip Latin accents and Arabic diacritics, unify Arabic letter variants."""
	text = unicodedata.normalize("NFKD", (text or "").lower())
	text = "".join(c for c in text if not unicodedata.combining(c))
	text = text.replace("\u0640", "").replace("\u0629", "\u0647").replace("\u0649", "\u064a")
	text = re.sub(r"[’'`´]", " ", text)
	text = re.sub(r"[^\w\s%]", " ", text)
	return re.sub(r"\s+", " ", text).strip()


def detect_language(text, hint=None):
	if _ARABIC.search(text or ""):
		return "ar"
	words = set(re.findall(r"[\wéèêëàâçùûôîïœ-]+", (text or "").lower()))
	if _FRENCH_ACCENTS.search((text or "").lower()) or len(words & _FRENCH_WORDS) >= 1 and not _looks_english(words):
		return "fr"
	hint = (hint or "en")[:2]
	return hint if hint in SUPPORTED_LANGS else "en"


def _looks_english(words):
	return bool(words & {"the", "how", "many", "show", "what", "are", "do", "we", "have", "give", "me", "of", "is", "my"})


def t(msg, lang=None, *args):
	"""Translate `msg` into `lang` and apply str.format(*args)."""
	out = _(msg, lang=lang) if lang and lang != "en" else msg
	return out.format(*args) if args else out
