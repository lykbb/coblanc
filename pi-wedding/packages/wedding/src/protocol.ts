import { Type } from "typebox";
import { Value } from "typebox/value";
import {
	type Api,
	type AssistantMessage,
	createAssistantMessageEventStream,
	type JsonObject,
	type JsonValue,
	type Model,
} from "../../ai/src/index.ts";

export interface GenerationJob {
	slot: number;
	seed: number;
}
export interface StartInput {
	system: string;
	model?: string;
	max_steps: number;
	input?: JsonValue;
	jobs?: GenerationJob[];
}

const startSchema = Type.Object(
	{
		type: Type.Literal("start"),
		system: Type.String(),
		model: Type.Optional(Type.String()),
		max_steps: Type.Integer({ minimum: 1, maximum: 1000 }),
		input: Type.Optional(Type.Unknown()),
		parallelism: Type.Optional(Type.Integer({ minimum: 1 })),
		jobs: Type.Optional(
			Type.Array(
				Type.Object(
					{
						slot: Type.Integer({ minimum: 0 }),
						seed: Type.Integer({ minimum: 0, maximum: 2147483647 }),
					},
					{ additionalProperties: false },
				),
				{ minItems: 1 },
			),
		),
	},
	{ additionalProperties: false },
);

export function parseStart(value: JsonValue): StartInput {
	if (!Value.Check(startSchema, value)) throw new Error("Invalid wedding agent request");
	return value as unknown as StartInput;
}
export function isObject(value: JsonValue): value is JsonObject {
	return typeof value === "object" && value !== null && !Array.isArray(value);
}
export interface PythonBridge {
	request(type: "decision" | "tool", payload: JsonObject): Promise<JsonValue>;
}
export function bridgeModel(id?: string): Model<Api> {
	return {
		id: id || "python",
		name: "Python business adapter",
		provider: "python",
		api: "python-bridge",
		baseUrl: "",
		reasoning: false,
		input: ["text"],
		cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
		contextWindow: 32768,
		maxTokens: 4096,
	};
}
export function assistantStream(
	model: Model<Api>,
	content: AssistantMessage["content"],
	reason: "stop" | "toolUse" = "stop",
) {
	const message: AssistantMessage = {
		role: "assistant",
		content,
		stopReason: reason,
		api: model.api,
		provider: model.provider,
		model: model.id,
		timestamp: Date.now(),
		usage: {
			input: 0,
			output: 0,
			cacheRead: 0,
			cacheWrite: 0,
			totalTokens: 0,
			cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
		},
	};
	const stream = createAssistantMessageEventStream();
	stream.push({ type: "start", partial: message });
	stream.push({ type: "done", reason, message });
	return stream;
}
