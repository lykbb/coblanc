import { Type } from "typebox";
import { Agent, type AgentTool } from "../../agent/src/index.ts";
import type { JsonValue } from "../../ai/src/index.ts";
import { assistantStream, bridgeModel, isObject, type PythonBridge, type StartInput } from "./protocol.ts";

const searchSchema = Type.Object(
	{
		kind: Type.Union([Type.Literal("pose"), Type.Literal("background")]),
		tags: Type.Array(Type.String()),
	},
	{ additionalProperties: false },
);

/** Wedding adaptation of the downloaded Pi Agent, with one asset-library tool. */
export class PhotographerAgent extends Agent {
	constructor(input: StartInput, bridge: PythonBridge) {
		const tool: AgentTool<typeof searchSchema, JsonValue> = {
			name: "search_assets",
			label: "寻找摄影参考素材",
			description: "从项目资产库查找姿态或背景，只能选择返回的素材",
			parameters: searchSchema,
			execute: async (_id, arguments_) => {
				const value = await bridge.request("tool", { name: "search_assets", arguments: arguments_ });
				return { content: [{ type: "text", text: JSON.stringify(value) }], details: value };
			},
		};
		let searches = 0;
		let turns = 0;
		super({
			role: "photographer",
			maxToolCalls: input.max_steps,
			maxTurns: input.max_steps + 1,
			initialState: {
				systemPrompt: input.system,
				model: bridgeModel(input.model),
				tools: [tool],
				thinkingLevel: "off",
			},
			toolExecution: "sequential",
			streamFn: async (model, context) => {
				const decision = await bridge.request("decision", {
					history: context.messages as unknown as JsonValue,
					remaining_steps: input.max_steps - searches,
				});
				if (!isObject(decision)) throw new Error("Invalid photographer decision");
				turns++;
				if (decision.action === "search_assets") {
					searches++;
					return assistantStream(
						model,
						[
							{
								type: "toolCall",
								id: `search-${turns}`,
								name: "search_assets",
								arguments: { kind: decision.kind ?? "pose", tags: decision.tags ?? [] },
							},
						],
						"toolUse",
					);
				}
				if (decision.action !== "final" || !decision.shot) throw new Error("Missing photographer plan");
				return assistantStream(model, [{ type: "text", text: JSON.stringify(decision) }]);
			},
		});
	}
	async run(input: JsonValue): Promise<JsonValue> {
		await this.prompt(JSON.stringify(input));
		const final = this.state.messages.filter((message) => message.role === "assistant").at(-1);
		if (!final || final.stopReason !== "stop") throw new Error("Photographer failed");
		const text = final.content.find((block) => block.type === "text");
		if (!text) throw new Error("Missing photographer result");
		return JSON.parse(text.text) as JsonValue;
	}
}
