frappe.provide("ai_chatbot");

frappe.pages["ai-chat"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("AI Chatbot"),
		single_column: true,
	});
	wrapper.ai_chat = new ai_chatbot.Chat(page, wrapper);
};

frappe.pages["ai-chat"].on_page_show = function (wrapper) {
	if (wrapper.ai_chat) wrapper.ai_chat.focus();
};

ai_chatbot.Chat = class Chat {
	constructor(page, wrapper) {
		this.page = page;
		this.wrapper = wrapper;
		this.busy = false;
		this.enabled = true;
		this.storage_key = `ai_chatbot_history:${frappe.session.user}`;
		this.llm_pref_key = `ai_chatbot_use_llm:${frappe.session.user}`;
		this.messages = this.load();
		this.help_auto_send = false;
		this.llm_available = false;
		this.use_llm = false;
		this.featured = [];
		this.help = new ai_chatbot.Help({ on_select: (q) => this.use_question(q) });

		this.make();
		this.render_all();
		this.page.set_secondary_action(__("New chat"), () => this.reset(), "refresh");
		this.load_config();
		this.load_featured();
	}

	// ---------------------------------------------------------------- layout
	make() {
		this.$main = $(this.wrapper).find(".layout-main-section").first();
		this.$main.html(`
			<div class="aic">
				<div class="aic-messages" role="log" aria-live="polite"></div>
				<div class="aic-options">
					<label class="aic-llm-toggle" title="${frappe.utils.escape_html(__("When off, questions are answered by the built-in rule-based engine only (no data leaves your server). When on, a configured AI provider is used to understand free-form questions."))}">
						<input type="checkbox" class="aic-llm-checkbox" disabled>
						<span>${frappe.utils.escape_html(__("Advanced AI (LLM)"))}</span>
					</label>
					<span class="aic-llm-status text-muted small"></span>
				</div>
				<div class="aic-composer">
					<button class="btn btn-default aic-help-btn" type="button" title="${frappe.utils.escape_html(__("Browse example questions"))}" aria-label="${frappe.utils.escape_html(__("Browse example questions"))}">
						${ai_chatbot.icon(["es-line-help", "es-line-question", "help"], "sm", "<b>?</b>")}
						<span class="aic-help-label">${frappe.utils.escape_html(__("Help"))}</span>
					</button>
					<textarea class="form-control aic-input" dir="auto" rows="1" maxlength="500"
						placeholder="${frappe.utils.escape_html(__("Ask a question about your ERPNext data..."))}"></textarea>
					<button class="btn btn-primary aic-send" type="button" aria-label="${frappe.utils.escape_html(__("Send"))}">
						${ai_chatbot.icon(["es-line-arrow-up-right", "es-line-arrow-up"], "sm", "&#10148;")}
					</button>
				</div>
				<div class="aic-hint text-muted small">
					${frappe.utils.escape_html(__("Answers only include data you are allowed to see. The chatbot is read-only."))}
				</div>
			</div>`);
		this.$messages = this.$main.find(".aic-messages");
		this.$input = this.$main.find(".aic-input");
		this.$send = this.$main.find(".aic-send");
		this.$llm_checkbox = this.$main.find(".aic-llm-checkbox");
		this.$llm_status = this.$main.find(".aic-llm-status");

		this.$send.on("click", () => this.send());
		this.$main.find(".aic-help-btn").on("click", () => this.help.open());
		this.$llm_checkbox.on("change", () => {
			this.use_llm = this.$llm_checkbox.prop("checked");
			try {
				localStorage.setItem(this.llm_pref_key, this.use_llm ? "1" : "0");
			} catch (e) {
				/* storage full or disabled: preference just won't persist across reloads */
			}
			this.update_llm_status();
		});
		this.$input.on("keydown", (e) => {
			if (e.key === "Enter" && !e.shiftKey && !e.originalEvent.isComposing) {
				e.preventDefault();
				this.send();
			}
		});
		this.$input.on("input", () => {
			const el = this.$input[0];
			el.style.height = "auto";
			el.style.height = Math.min(el.scrollHeight, 140) + "px";
		});
	}

	focus() {
		if (this.$input) this.$input.trigger("focus");
	}

	load_config() {
		frappe.call({
			method: "ai_chatbot.api.get_config",
			type: "GET",
			no_spinner: true,
			callback: (r) => {
				const c = r.message || {};
				this.help_auto_send = !!c.help_auto_send;
				if (c.auth_required) {
					this.enabled = false;
					this.set_busy(true);
					this.page.set_indicator(__("Session expired"), "red");
					this.append({ role: "bot", text: c.error || __("Your session has expired. Please refresh the page and sign in again."), error: true, reload: true }, false);
					return;
				}
				this.enabled = !!c.enabled;
				this.llm_available = !!c.llm_available;

				// per-user preference persists across sessions; falls back to the admin's default the first time
				let pref = null;
				try {
					pref = localStorage.getItem(this.llm_pref_key);
				} catch (e) {
					/* storage disabled: just use the admin's default every time */
				}
				this.use_llm = this.llm_available && (pref === null ? c.mode === "llm" : pref === "1");
				this.$llm_checkbox.prop("checked", this.use_llm).prop("disabled", !this.llm_available);
				this.update_llm_status();

				if (!this.enabled) {
					this.page.set_indicator(__("Disabled"), "red");
					this.set_busy(true);
					this.append({ role: "bot", text: __("The chatbot is disabled. Please contact your administrator."), error: true }, false);
				}
			},
			error: () => {
				// network/server error fetching config: don't block the composer, just skip the indicator
			},
		});
	}

	update_llm_status() {
		if (!this.llm_available) {
			this.$llm_status.text(__("Ask your administrator to configure an AI provider to enable this."));
		} else {
			this.$llm_status.text("");
		}
		this.set_mode_indicator(this.use_llm ? "llm" : "rules");
	}

	set_mode_indicator(mode) {
		if (!this.enabled) return;
		this.page.set_indicator(mode === "llm" ? __("AI-assisted") : __("Built-in engine"), mode === "llm" ? "green" : "blue");
	}

	load_featured() {
		ai_chatbot.Help.fetch({ language: frappe.boot.lang })
			.then((res) => {
				this.featured = (res && res.featured) || [];
				if (!this.messages.length) this.render_all();
			})
			.catch(() => {});
	}

	// Help never runs anything itself: it only fills the input (or sends if the admin enabled it).
	use_question(q) {
		if (this.help_auto_send) return this.send(q);
		this.$input.val(q).trigger("input");
		this.focus();
	}

	// --------------------------------------------------------------- history
	load() {
		try {
			return JSON.parse(localStorage.getItem(this.storage_key) || "[]");
		} catch (e) {
			return [];
		}
	}

	save() {
		try {
			localStorage.setItem(this.storage_key, JSON.stringify(this.messages.slice(-30)));
		} catch (e) {
			/* storage full or disabled: history just won't persist */
		}
	}

	reset() {
		frappe.confirm(__("Clear the conversation?"), () => {
			this.messages = [];
			this.save();
			this.render_all();
		});
	}

	history_for_server() {
		return this.messages
			.filter((m) => !m.error && m.text)
			.slice(-6)
			.map((m) => ({ role: m.role, text: String(m.text).slice(0, 500) }));
	}

	// ------------------------------------------------------------- rendering
	render_all() {
		this.$messages.empty();
		if (!this.messages.length) return this.render_welcome();
		this.messages.forEach((m) => this.$messages.append(this.render_message(m)));
		this.scroll();
	}

	render_welcome() {
		const $w = $(`<div class="aic-welcome"></div>`);
		$w.append(this.render_message({
			role: "bot",
			text: __("Hello! I can answer questions about your ERPNext data. Try one of the examples below."),
		}, true));
		if (this.featured.length) {
			const $chips = $(`<div class="aic-chips"></div>`);
			this.featured.forEach((f) => {
				$(`<button type="button" class="aic-chip" dir="auto"></button>`).text(f.question).on("click", () => this.send(f.question)).appendTo($chips);
			});
			$w.append($chips);
		}
		this.$messages.append($w);
	}

	render_message(m, no_time) {
		const $row = $(`<div class="aic-row aic-${m.role}${m.error ? " aic-error" : ""}"></div>`);
		if (m.role === "bot") {
			$row.append(`<div class="aic-avatar" aria-hidden="true">${ai_chatbot.icon("es-line-chat-alt", "sm", "AI")}</div>`);
		}
		const $bubble = $(`<div class="aic-bubble" dir="auto"></div>`);
		if (m.text) $bubble.append(`<div class="aic-text">${this.md(m.text)}</div>`);
		(m.blocks || []).forEach((b) => $bubble.append(this.render_block(b)));
		if (m.error && m.reload) {
			$(`<button type="button" class="btn btn-xs btn-primary aic-retry"></button>`)
				.text(__("Reload page"))
				.on("click", () => window.location.reload())
				.appendTo($bubble);
		} else if (m.error && m.retry) {
			$(`<button type="button" class="btn btn-xs btn-default aic-retry"></button>`)
				.text(__("Retry"))
				.on("click", () => this.send(m.retry))
				.appendTo($bubble);
		}
		$row.append($bubble);
		return $row;
	}

	// minimal, XSS-safe markdown: everything is escaped first
	md(text) {
		return frappe.utils
			.escape_html(text || "")
			.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
			.replace(/`([^`]+)`/g, "<code>$1</code>")
			.replace(/\n/g, "<br>");
	}

	render_block(b) {
		const esc = frappe.utils.escape_html;
		if (b.type === "stats") {
			const cards = (b.items || [])
				.map((i) => `<div class="aic-stat"><div class="aic-stat-value">${esc(i.value)}</div><div class="aic-stat-label">${esc(i.label)}</div></div>`)
				.join("");
			return $(`<div class="aic-stats">${cards}</div>`);
		}
		const numeric = ["Currency", "Float", "Int", "Percent"];
		const head = b.columns.map((c) => `<th class="${numeric.includes(c.fieldtype) ? "aic-num" : ""}">${esc(c.label)}</th>`).join("");
		const body = b.rows
			.map((row) => "<tr>" + row.map((val, i) => {
				const col = b.columns[i];
				const cls = numeric.includes(col.fieldtype) ? ' class="aic-num"' : "";
				const cell = col.link && val && val !== "—"
					? `<a href="/app/${frappe.router.slug(col.link)}/${encodeURIComponent(val)}">${esc(val)}</a>`
					: esc(val);
				return `<td${cls}>${cell}</td>`;
			}).join("") + "</tr>")
			.join("");
		const $t = $(`
			<div class="aic-table-block">
				<div class="aic-table-head">
					<span class="aic-table-title">${esc(b.title || "")}</span>
					<button type="button" class="btn btn-xs btn-default aic-csv">${esc(__("Download CSV"))}</button>
				</div>
				<div class="aic-table-wrap"><table class="table table-sm aic-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>
				${b.footer ? `<div class="aic-table-foot text-muted small">${esc(b.footer)}</div>` : ""}
			</div>`);
		$t.find(".aic-csv").on("click", () => this.download_csv(b));
		return $t;
	}

	download_csv(b) {
		const q = (v) => `"${String(v).replace(/"/g, '""')}"`;
		const rows = [b.columns.map((c) => c.label), ...b.rows];
		const blob = new Blob(["\ufeff" + rows.map((r) => r.map(q).join(",")).join("\n")], { type: "text/csv;charset=utf-8" });
		const a = document.createElement("a");
		a.href = URL.createObjectURL(blob);
		a.download = `${(b.title || "chatbot").replace(/[^\w\-]+/g, "_")}.csv`;
		a.click();
		URL.revokeObjectURL(a.href);
	}

	scroll() {
		const el = this.$messages[0];
		el.scrollTop = el.scrollHeight;
	}

	append(m, persist = true) {
		this.$messages.find(".aic-welcome").remove();
		this.messages.push(m);
		this.$messages.append(this.render_message(m));
		if (persist) this.save();
		this.scroll();
	}

	set_busy(busy) {
		this.busy = busy;
		this.$send.prop("disabled", busy);
		this.$input.prop("disabled", busy && !this.enabled);
	}

	show_typing() {
		const $t = $(`<div class="aic-row aic-bot aic-typing" aria-label="${frappe.utils.escape_html(__("Thinking..."))}">
			<div class="aic-avatar">${ai_chatbot.icon("es-line-chat-alt", "sm", "AI")}</div>
			<div class="aic-bubble"><span class="aic-dot"></span><span class="aic-dot"></span><span class="aic-dot"></span></div></div>`);
		this.$messages.append($t);
		this.scroll();
		return $t;
	}

	// ------------------------------------------------------------------ send
	send(text) {
		text = (text || this.$input.val() || "").trim();
		if (!text || this.busy || !this.enabled) return;
		const history = this.history_for_server();

		this.$input.val("").trigger("input");
		this.append({ role: "user", text });
		this.set_busy(true);
		const $typing = this.show_typing();

		frappe.call({
			method: "ai_chatbot.api.chat",
			type: "POST",
			args: { message: text, history: JSON.stringify(history), use_llm: this.use_llm ? 1 : 0 },
			no_spinner: true,
			callback: (r) => {
				const m = r.message || {};
				if (m.ok) {
					this.append({ role: "bot", text: m.reply, blocks: m.blocks || [] });
					if (m.mode === "llm" || m.mode === "rules") this.set_mode_indicator(m.mode);
				} else if (m.auth_required) {
					this.enabled = false;
					this.page.set_indicator(__("Session expired"), "red");
					this.append({ role: "bot", text: m.error || m.reply, error: true, reload: true });
				} else {
					this.append({ role: "bot", text: m.error || m.reply || __("Something went wrong while processing your request. Please try again."), error: true, retry: text });
				}
			},
			error: () => {
				this.append({ role: "bot", text: __("Something went wrong while processing your request. Please try again."), error: true, retry: text });
			},
			always: () => {
				$typing.remove();
				this.set_busy(false);
				this.focus();
			},
		});
	}
};
