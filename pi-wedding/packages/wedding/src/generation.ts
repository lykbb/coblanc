import { Type } from "typebox";
import { Agent, type AgentTool } from "../../agent/src/index.ts";
import type { JsonValue } from "../../ai/src/index.ts";
import { assistantStream, bridgeModel, type PythonBridge, type StartInput } from "./protocol.ts";

const candidateSchema = Type.Object(
	{
		slot: Type.Integer({ minimum: 0 }),
		seed: Type.Integer({ minimum: 0, maximum: 2147483647 }),
	},
	{ additionalProperties: false },
);

/** Pi's parallel tool loop executes the confirmed plan; Python owns image APIs and retries. */
export class GenerationAgent extends Agent {
	constructor(input: StartInput, bridge: PythonBridge) {
		const jobs = input.jobs?.map((job) => ({ ...job }));
		if (!jobs?.length || jobs.length > input.max_steps || new Set(jobs.map((job) => job.slot)).size !== jobs.length) {
			throw new Error("Invalid candidate plan");
		}
		const tool: AgentTool<typeof candidateSchema, JsonValue> = {
			name: "generate_candidate",
			label: "生成一张候选婚纱照",
			description: "执行已确认的生图计划，参数由 Python 校验，返回候选生成记录",
			parameters: candidateSchema,
			execute: async (_id, arguments_) => {
				if (!jobs.some((job) => job.slot === arguments_.slot && job.seed === arguments_.seed)) {
					throw new Error("Candidate is outside the confirmed plan");
				}
				const value = await bridge.request("tool", { name: "generate_candidate", arguments: arguments_ });
				return { content: [{ type: "text", text: JSON.stringify(value) }], details: value };
			},
		};
		let dispatched = false;
		super({
			role: "generation",
			maxToolCalls: input.max_steps,
			maxTurns: 2,
			initialState: {
				systemPrompt: input.system,
				model: bridgeModel(input.model),
				tools: [tool],
				thinkingLevel: "off",
			},
			toolExecution: "parallel",
			streamFn: async (model, context) => {
				if (!dispatched) {
					dispatched = true;
					return assistantStream(
						model,
						jobs.map((job) => ({
							type: "toolCall",
							id: `image-${job.slot}`,
							name: "generate_candidate",
							arguments: job,
						})),
						"toolUse",
					);
				}
				if (context.messages.some((message) => message.role === "toolResult" && message.isError)) {
					throw new Error("Candidate failed");
				}
				return assistantStream(model, [{ type: "text", text: "生成计划已执行" }]);
			},
		});
	}
	async run(): Promise<JsonValue> {
		await this.prompt("执行已确认的婚纱照生成计划");
		const final = this.state.messages.filter((message) => message.role === "assistant").at(-1);
		if (!final || final.stopReason !== "stop") throw new Error("Generation failed");
		return { completed: true };
	}
}
