/** Fixed business tool sets replace Pi's coding-agent tools in this source fork. */
export type WeddingRole = "photographer" | "generation";

export function allowedToolNames(role: WeddingRole): readonly string[] {
	if (role === "photographer") return ["search_assets"];
	if (role === "generation") return ["generate_candidate"];
	throw new Error("Unknown wedding agent role");
}

export function validateWeddingTools(role: WeddingRole, tools: readonly { name: string }[]): void {
	const allowed = allowedToolNames(role);
	const names = new Set<string>();
	for (const tool of tools) {
		if (!allowed.includes(tool.name) || names.has(tool.name)) {
			throw new Error("Tool is outside this wedding agent's tool set");
		}
		names.add(tool.name);
	}
}
