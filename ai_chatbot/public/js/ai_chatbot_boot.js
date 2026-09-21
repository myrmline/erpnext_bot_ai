// Makes the "AI Chatbot" sidebar item open the chat page directly
// (the sidebar entry is a Workspace; we redirect it to the page).
$(document).on("startup", () => {
	if (!frappe.router || !frappe.router.on) return;
	const targets = ["ai-chatbot", "workspaces/ai chatbot", "workspaces/ai-chatbot"];
	const check = () => {
		const route = (frappe.get_route_str() || "").toLowerCase();
		if (targets.includes(route)) frappe.set_re_route("ai-chat");
	};
	frappe.router.on("change", check);
	check();
});
