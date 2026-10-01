// Shared types used by both the browser and the server. Keep free of server-only
// imports so it can be imported anywhere.

export type ModelName = 'general' | 'lite' | 'matting';

export type ImageFormat = 'png' | 'webp';

/** What the user can pick before a run. The mask is always returned as PNG;
 * `format` applies to the cutout. */
export type RemovalOptions = {
	model: ModelName;
	resolution: number; // square inference size, multiple of 32 (256–2048)
	format: ImageFormat;
};

/** One entry of the worker's `outputs` — mirrors the worker response. */
export type WorkerOutput = {
	kind: 'mask' | 'cutout';
	format: ImageFormat;
	fileName: string;
	width: number;
	height: number;
	bytes: number;
	data?: string; // base64, inline destination only
};

/** The handler's return value (the RunPod job `output`). */
export type WorkerResult = {
	metadata: Record<string, unknown>;
	model: ModelName;
	resolution: number;
	destinationType: 'inline' | 's3' | 'http';
	outputs: WorkerOutput[];
	timings: Record<string, number>; // ms per stage, measured inside the handler
	worker: {
		device: string;
		dtype: string;
		coldStart: boolean;
		jobIndex: number;
		startupMs: number;
		uptimeMs: number;
		modelLoadMs: number | null;
	};
};

/** What `POST /api/remove-background` returns to the browser. */
export type RemovalResponse = {
	jobId: string;
	roundTripMs: number; // this server → RunPod → back, wall time
	delayTimeMs: number | null; // RunPod queue + cold start (not billed)
	executionTimeMs: number | null; // RunPod billed compute
	result: WorkerResult;
};

export type RunStatus = 'processing' | 'done' | 'error';

/** One image the user submitted, as tracked in the browser (session only). */
export type Run = {
	id: string;
	file: File; // kept so the run can be repeated with other options
	originalUrl: string; // object URLs for display + download
	maskUrl: string | null;
	cutoutUrl: string | null;
	options: RemovalOptions;
	status: RunStatus;
	startedAt: number;
	clientMs: number | null; // browser wall time, incl. upload and download
	response: RemovalResponse | null; // `outputs[].data` stripped
	error: string | null;
};
