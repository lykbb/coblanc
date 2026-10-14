import { createInterface } from "node:readline";
import type { WeddingRole } from "../../agent/src/index.ts";
import type { JsonObject, JsonValue } from "../../ai/src/index.ts";
import { GenerationAgent } from "./generation.ts";
import { PhotographerAgent } from "./photographer.ts";
import { isObject, type PythonBridge, parseStart, type StartInput } from "./protocol.ts";

/** One NDJSON connection per invocation; no shared sessions, credentials or image bytes. */
export async function runCli(role: WeddingRole): Promise<void> {
	const lines = createInterface({ input: process.stdin });
	const emit = (value: JsonObject) => process.stdout.write(`${JSON.stringify(value)}\n`);
	let startResolve!: (input: StartInput) => void;
	let startReject!: (error: Error) => void;
	const initial = new Promise<StartInput>((resolve, reject) => {
		startResolve = resolve;
		startReject = reject;
	});
	const pending = new Map<string, { resolve: (value: JsonValue) => void; reject: (error: Error) => void }>();
	let started = false;
	let sequence = 0;
	let closing = false;
	let disconnected = false;
	const fail = () => {
		disconnected = true;
		const error = new Error("Python connection failed");
		startReject(error);
		for (const request of pending.values()) request.reject(error);
		pending.clear();
	};
	lines.on("line", (line) => {
		try {
			if (Buffer.byteLength(line, "utf8") > 1048576) throw new Error("Message too large");
			const value = JSON.parse(line) as JsonValue;
			if (!started) {
				const input = parseStart(value);
				started = true;
				startResolve(input);
			} else {
				if (!isObject(value) || typeof value.id !== "string") throw new Error("Invalid RPC reply");
				const request = pending.get(value.id);
				if (!request) throw new Error("Unknown RPC reply");
				pending.delete(value.id);
				if (typeof value.error === "string") request.reject(new Error("Business tool failed"));
				else if ("value" in value) request.resolve(value.value);
				else request.reject(new Error("Missing RPC result"));
			}
		} catch {
			fail();
			lines.close();
		}
	});
	lines.on("close", () => {
		if (!closing) fail();
	});
	const bridge: PythonBridge = {
		request(type, payload) {
			if (disconnected) return Promise.reject(new Error("Python connection closed"));
			const id = String(++sequence);
			const result = new Promise<JsonValue>((resolve, reject) => pending.set(id, { resolve, reject }));
			emit({ type, id, ...payload });
			return result;
		},
	};
	try {
		const input = await initial;
		const result =
			role === "photographer"
				? await new PhotographerAgent(input, bridge).run(input.input ?? null)
				: await new GenerationAgent(input, bridge).run();
		emit({ type: "result", value: result });
	} catch {
		emit({ type: "error", message: "Pi wedding agent failed" });
		process.exitCode = 1;
	} finally {
		closing = true;
		lines.close();
		process.stdin.pause();
		fail();
	}
}
