import assert from "node:assert/strict";
import { test } from "node:test";
import { Type } from "typebox";
import { Agent, type AgentTool, allowedToolNames, type StreamFn } from "../../agent/src/index.ts";
import type { JsonValue } from "../../ai/src/index.ts";
import { GenerationAgent } from "../src/generation.ts";
import { PhotographerAgent } from "../src/photographer.ts";
import { assistantStream, bridgeModel, type PythonBridge } from "../src/protocol.ts";

const model = bridgeModel();
const shot = { text: "平视半身，柔和侧光", pose: "keep_original", references: [] };
const schema = Type.Object({ slot: Type.Integer() }, { additionalProperties: false });

function candidate(execute: () => Promise<void> = async () => {}): AgentTool {
	return {
		name: "generate_candidate",
		label: "候选图",
		description: "候选图",
		parameters: schema,
		execute: async () => {
			await execute();
			return { content: [], details: {} };
		},
	};
}
function loopingStream(): StreamFn {
	let turn = 0;
	return async (activeModel) =>
		assistantStream(
			activeModel,
			[
				{
					type: "toolCall",
					id: String(++turn),
					name: "generate_candidate",
					arguments: { slot: 0 },
				},
			],
			"toolUse",
		);
}

test("photographer queries the asset library and returns the confirmed plan", async () => {
	const requests: string[] = [];
	const bridge: PythonBridge = {
		request: async (type, payload): Promise<JsonValue> => {
			requests.push(type);
			if (type === "tool") {
				assert.equal(payload.name, "search_assets");
				assert.deepEqual(payload.arguments, { kind: "pose", tags: ["medium"] });
				return [{ asset_id: "pose_medium_a" }];
			}
			if (requests.length === 1) return { action: "search_assets", kind: "pose", tags: ["medium"] };
			assert.ok(JSON.stringify(payload.history).includes("pose_medium_a"));
			return { action: "final", shot };
		},
	};
	const agent = new PhotographerAgent({ system: "摄影师", max_steps: 2 }, bridge);
	assert.deepEqual(await agent.run({ heights_cm: [175, 162] }), { action: "final", shot });
	assert.deepEqual(requests, ["decision", "tool", "decision"]);
});

test("generation starts four tools before waiting for their results", { timeout: 5000 }, async () => {
	let release!: () => void;
	const barrier = new Promise<void>((resolve) => {
		release = resolve;
	});
	const slots: number[] = [];
	const bridge: PythonBridge = {
		request: async (type, payload) => {
			assert.equal(type, "tool");
			assert.equal(payload.name, "generate_candidate");
			const args = payload.arguments as { slot: number; seed: number };
			slots.push(args.slot);
			if (slots.length === 4) release();
			await barrier;
			return { slot: args.slot, seed: -1, engine: "seedream" };
		},
	};
	const jobs = Array.from({ length: 4 }, (_, slot) => ({ slot, seed: slot + 7 }));
	const agent = new GenerationAgent({ system: "生图", max_steps: 6, jobs }, bridge);
	assert.deepEqual(await agent.run(), { completed: true });
	assert.deepEqual(slots, [0, 1, 2, 3]);
});

test("generation reports a failed candidate without silently repeating its request", async () => {
	let calls = 0;
	const bridge: PythonBridge = {
		request: async () => {
			calls++;
			throw new Error("test failure");
		},
	};
	const agent = new GenerationAgent({ system: "生图", max_steps: 2, jobs: [{ slot: 0, seed: 7 }] }, bridge);
	await assert.rejects(agent.run(), /Generation failed/);
	assert.equal(calls, 1);
});

test("source core rejects coding tools and the other role's tools", () => {
	assert.deepEqual(allowedToolNames("photographer"), ["search_assets"]);
	assert.deepEqual(allowedToolNames("generation"), ["generate_candidate"]);
	for (const name of ["bash", "powershell", "read", "write", "edit", "grep", "find", "ls", "search_assets"]) {
		assert.throws(
			() =>
				new Agent({
					role: "generation",
					maxToolCalls: 1,
					maxTurns: 2,
					streamFn: loopingStream(),
					initialState: { tools: [{ ...candidate(), name }] },
				}),
			/outside/,
		);
	}
});

test("source core prevents re-registering tools through the public state", () => {
	const agent = new Agent({
		role: "generation",
		maxToolCalls: 1,
		maxTurns: 2,
		streamFn: loopingStream(),
		initialState: { tools: [candidate()] },
	});
	assert.throws(() => {
		agent.state.tools = [{ ...candidate(), name: "bash" }];
	}, /outside/);
	agent.state.tools.push({ ...candidate(), name: "bash" });
	assert.deepEqual(
		agent.state.tools.map((tool) => tool.name),
		["generate_candidate"],
	);
});

test("source core stops excess tool calls before executing another paid action", async () => {
	let executed = 0;
	const agent = new Agent({
		role: "generation",
		maxToolCalls: 1,
		maxTurns: 3,
		streamFn: loopingStream(),
		initialState: {
			model,
			tools: [
				candidate(async () => {
					executed++;
				}),
			],
		},
	});
	await agent.prompt("执行");
	assert.equal(executed, 1);
	assert.match(agent.state.errorMessage || "", /tool limit/);
});

test("source core enforces the turn limit independently of the tool budget", async () => {
	let executed = 0;
	const agent = new Agent({
		role: "generation",
		maxToolCalls: 5,
		maxTurns: 1,
		streamFn: loopingStream(),
		initialState: {
			model,
			tools: [
				candidate(async () => {
					executed++;
				}),
			],
		},
	});
	await agent.prompt("执行");
	assert.equal(executed, 1);
	assert.match(agent.state.errorMessage || "", /turn limit/);
});

test("unknown tool calls do not reach the Python business bridge", async () => {
	let executed = 0;
	let requested = false;
	const agent = new Agent({
		role: "generation",
		maxToolCalls: 1,
		maxTurns: 2,
		initialState: {
			model,
			tools: [
				candidate(async () => {
					executed++;
				}),
			],
		},
		streamFn: async (activeModel) => {
			if (requested) return assistantStream(activeModel, [{ type: "text", text: "结束" }]);
			requested = true;
			return assistantStream(activeModel, [{ type: "toolCall", id: "x", name: "bash", arguments: {} }], "toolUse");
		},
	});
	await agent.prompt("执行");
	assert.equal(executed, 0);
	assert.ok(agent.state.messages.some((message) => message.role === "toolResult" && message.isError));
});

test("invalid tool parameters are rejected before execution", async () => {
	let executed = 0;
	const agent = new Agent({
		role: "generation",
		maxToolCalls: 1,
		maxTurns: 1,
		initialState: {
			model,
			tools: [
				candidate(async () => {
					executed++;
				}),
			],
		},
		streamFn: async (activeModel) =>
			assistantStream(
				activeModel,
				[
					{
						type: "toolCall",
						id: "x",
						name: "generate_candidate",
						arguments: { slot: "invalid" },
					},
				],
				"toolUse",
			),
	});
	await agent.prompt("执行");
	assert.equal(executed, 0);
});

test("generation rejects duplicate slots or a plan beyond the tool budget", () => {
	const bridge: PythonBridge = { request: async () => ({}) };
	for (const jobs of [
		[
			{ slot: 0, seed: 1 },
			{ slot: 0, seed: 2 },
		],
		[
			{ slot: 0, seed: 1 },
			{ slot: 1, seed: 2 },
		],
	]) {
		assert.throws(() => new GenerationAgent({ system: "生图", max_steps: 1, jobs }, bridge), /Invalid candidate plan/);
	}
});
