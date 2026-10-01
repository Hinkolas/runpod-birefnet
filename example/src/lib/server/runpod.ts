// Talks to the RunPod serverless endpoint. The image travels inline: we send it as
// base64 in the job input and get the mask + cutout back as base64 in the job
// output, so the worker never needs to reach this server (no public URL, no tunnel).

import { env } from '$env/dynamic/private';
import type { RemovalOptions, RemovalResponse, WorkerResult } from '$lib/types';

const API = 'https://api.runpod.ai/v2';
const POLL_INTERVAL_MS = 1000;

function requireEnv(name: string): string {
	const value = env[name];
	if (!value) throw new Error(`${name} is not set`);
	return value;
}

/** Identifies which app/customer a job belongs to, for usage attribution. */
export function appId(): string {
	return env.APP_ID || 'demo-ui';
}

/** Build the worker job `input`: base64 source, no destination ⇒ inline results. */
export function buildRemovalInput(image: Uint8Array, options: RemovalOptions) {
	return {
		source: { type: 'base64', data: Buffer.from(image).toString('base64') },
		model: options.model,
		resolution: options.resolution,
		outputs: [
			{ kind: 'mask', format: 'png' },
			{ kind: 'cutout', format: options.format, quality: 90 }
		],
		// Echoed back in the result so each job is attributable to an app.
		metadata: { app: appId() }
	};
}

type RunpodStatusResponse = {
	id?: string;
	status?: string;
	delayTime?: number; // ms spent queued, incl. cold start (not billed)
	executionTime?: number; // ms of compute RunPod bills for
	output?: WorkerResult;
	error?: string;
};

const TERMINAL = new Set(['COMPLETED', 'FAILED', 'CANCELLED', 'TIMED_OUT']);

/**
 * Run one job and wait for it. `/runsync` normally returns the finished job, but
 * if it outlasts RunPod's sync window (e.g. a cold start) it hands back an
 * in-flight status, so we fall back to polling `/status` until a terminal state.
 */
export async function removeBackground(
	image: Uint8Array,
	options: RemovalOptions
): Promise<RemovalResponse> {
	const endpointId = requireEnv('RUNPOD_ENDPOINT_ID');
	const apiKey = requireEnv('RUNPOD_API_KEY');
	const timeoutMs = Number(env.RUNPOD_TIMEOUT_MS || 300_000);
	const headers = { authorization: `Bearer ${apiKey}`, 'content-type': 'application/json' };
	const base = `${API}/${endpointId}`;

	const started = performance.now();
	const response = await fetch(`${base}/runsync`, {
		method: 'POST',
		headers,
		body: JSON.stringify({
			input: buildRemovalInput(image, options),
			policy: { executionTimeout: timeoutMs, ttl: timeoutMs + 60_000 }
		})
	});
	if (!response.ok) {
		throw new Error(`RunPod submit failed (${response.status}): ${await response.text()}`);
	}
	let data = (await response.json()) as RunpodStatusResponse;
	const jobId = data.id;
	if (!jobId) throw new Error('RunPod did not return a job id');

	while (!TERMINAL.has(data.status ?? '')) {
		if (performance.now() - started > timeoutMs) {
			// Don't leave an abandoned job in the queue burning a worker.
			await fetch(`${base}/cancel/${jobId}`, { method: 'POST', headers }).catch(() => {});
			throw new Error(`Job ${jobId} did not finish within ${Math.round(timeoutMs / 1000)}s`);
		}
		await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
		const poll = await fetch(`${base}/status/${jobId}`, { headers });
		if (poll.ok) data = (await poll.json()) as RunpodStatusResponse;
	}

	if (data.status !== 'COMPLETED' || !data.output) {
		throw new Error(data.error || `Job ${data.status?.toLowerCase() || 'failed'}`);
	}

	return {
		jobId,
		roundTripMs: Math.round(performance.now() - started),
		delayTimeMs: data.delayTime ?? null,
		executionTimeMs: data.executionTime ?? null,
		result: data.output
	};
}
