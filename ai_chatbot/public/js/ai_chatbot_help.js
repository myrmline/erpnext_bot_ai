// Help / example-questions browser. All content comes from the server
// (ai_chatbot.api.help.get_questions <- help/questions.json); nothing is hardcoded here.
frappe.provide("ai_chatbot");

// Use an icon from Frappe's sprite if it exists, otherwise a fallback (never a blank hole).
ai_chatbot.icon = function (candidates, size, fallback) {
	for (const name of [].concat(candidates)) {
		if (document.getElementById(`icon-${name}`)) return frappe.utils.icon(name, size || "sm");
	}
	return fallback || "";
};

ai_chatbot.Help = class Help {
	static fetch(args) {
		return frappe.xcall("ai_chatbot.api.help.get_questions", args, "GET");
	}

	constructor({ on_select }) {
		this.on_select = on_select;
		this.category = null;
		this.search = "";
		this.request_id = 0;
		this.dialog = null;
	}

	open() {
		if (!this.dialog) this.build();
		this.dialog.show();
		this.refresh();
	}

	build() {
		const esc = frappe.utils.escape_html;
		this.dialog = new frappe.ui.Dialog({
			title: __("Help"),
			size: "large",
			fields: [{ fieldtype: "HTML", fieldname: "body" }],
		});
		this.dialog.fields_dict.body.$wrapper.html(`
			<div class="aic-help">
				<input type="search" class="form-control aic-help-search" dir="auto" autocomplete="off"
					placeholder="${esc(__("Search examples..."))}" aria-label="${esc(__("Search"))}">
				<div class="aic-help-cats" role="group" aria-label="${esc(__("Categories"))}"></div>
				<div class="aic-help-list" tabindex="-1" aria-live="polite"></div>
				<div class="aic-help-tip text-muted small">
					${esc(__("Click a question to insert it into the chat box. You can edit it before sending."))}
				</div>
			</div>`);
		const $w = this.dialog.fields_dict.body.$wrapper;
		this.$search = $w.find(".aic-help-search");
		this.$cats = $w.find(".aic-help-cats");
		this.$list = $w.find(".aic-help-list");

		let timer;
		this.$search.on("input", () => {
			clearTimeout(timer);
			timer = setTimeout(() => { this.search = this.$search.val().trim(); this.refresh(); }, 200);
		});
		this.dialog.$wrapper.on("shown.bs.modal", () => this.$search.trigger("focus"));
	}

	refresh() {
		const id = ++this.request_id;
		const args = { language: frappe.boot.lang };
		if (this.category) args.category = this.category;
		if (this.search) args.search = this.search;

		this.$list.attr("aria-busy", "true");
		ai_chatbot.Help.fetch(args)
			.then((res) => {
				if (id !== this.request_id) return; // stale response
				this.render_categories(res.all_categories || []);
				this.render_list(res.categories || []);
			})
			.catch(() => {
				if (id !== this.request_id) return;
				this.$list.html(`<div class="aic-help-empty text-muted">${frappe.utils.escape_html(__("Could not load help."))}</div>`);
			})
			.finally(() => this.$list.attr("aria-busy", "false"));
	}

	category_icon(cat) {
		const letter = frappe.utils.escape_html(((cat.title || "?")[0] || "?").toUpperCase());
		return ai_chatbot.icon([`es-line-${cat.icon}`, cat.icon], "sm", `<span class="aic-help-letter" aria-hidden="true">${letter}</span>`);
	}

	render_categories(cats) {
		this.$cats.empty();
		const add = (id, label, icon_html) => {
			$(`<button type="button" class="aic-help-cat" aria-pressed="${this.category === id}"></button>`)
				.toggleClass("active", this.category === id)
				.html(`${icon_html || ""}<span></span>`)
				.find("span:last").text(label).end()
				.on("click", () => { this.category = id; this.refresh(); })
				.appendTo(this.$cats);
		};
		add(null, __("All"), "");
		cats.forEach((c) => add(c.id, c.title, this.category_icon(c)));
	}

	render_list(cats) {
		this.$list.empty();
		if (!cats.length) {
			return this.$list.html(`<div class="aic-help-empty text-muted">${frappe.utils.escape_html(__("No matching questions."))}</div>`);
		}
		cats.forEach((cat) => {
			const $s = $(`<section class="aic-help-section"></section>`);
			$s.append($(`<h6 class="aic-help-cat-title"></h6>`).html(this.category_icon(cat)).append($("<span>").text(cat.title)));
			if (cat.description) $s.append($(`<p class="aic-help-cat-desc text-muted small" dir="auto"></p>`).text(cat.description));
			const $ul = $(`<div class="aic-help-questions"></div>`);
			cat.questions.forEach((q) => {
				// "allowed" is only a hint (this user's current read access to q.doctype); it is never
				// used to hide the question. If they click it anyway and truly lack access, the chat
				// endpoint enforces that for real and answers with a clear permission-denied message.
				const $btn = $(`<button type="button" class="aic-help-q" dir="auto"></button>`)
					.text(q.question)
					.on("click", () => { this.dialog.hide(); this.on_select && this.on_select(q.question); })
					.appendTo($ul);
				if (q.allowed === false) {
					$btn.addClass("aic-help-q-restricted").attr("title", __("You may not have permission to access this data."));
					$btn.prepend(`<span class="aic-help-lock" aria-hidden="true">${ai_chatbot.icon(["es-line-lock", "es-solid-lock", "lock"], "xs", "&#128274;")}</span>`);
				}
			});
			$s.append($ul);
			this.$list.append($s);
		});
	}
};
