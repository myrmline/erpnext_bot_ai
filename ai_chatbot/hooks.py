app_name = "ai_chatbot"
app_title = "AI Chatbot"
app_publisher = "Your Company"
app_description = "Read-only, permission-aware AI chatbot for ERPNext"
app_email = "dev@example.com"
app_license = "MIT"

required_apps = ["frappe", "erpnext"]

# Desk assets (styles + sidebar redirect). The chat page itself lives in
# ai_chatbot/ai_chatbot/page/ai_chat and is served at /app/ai-chat
app_include_css = "/assets/ai_chatbot/css/ai_chatbot.css"
app_include_js = "/assets/ai_chatbot/js/ai_chatbot_boot.js"

# Tile on the Frappe "Apps" screen (v15+)
add_to_apps_screen = [
	{
		"name": "ai_chatbot",
		"logo": "/assets/ai_chatbot/images/chatbot.svg",
		"title": "AI Chatbot",
		"route": "/app/ai-chat",
		"has_permission": "ai_chatbot.install.has_app_permission",
	}
]

after_install = "ai_chatbot.install.after_install"
after_migrate = "ai_chatbot.install.after_migrate"
before_uninstall = "ai_chatbot.install.before_uninstall"

scheduler_events = {
	"daily": ["ai_chatbot.tasks.clear_old_logs"],
}
