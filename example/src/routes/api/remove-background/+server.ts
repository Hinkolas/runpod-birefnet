import { json, type RequestHandler } from '@sveltejs/kit';
import { removeBackground } from '$lib/server/runpod';
import type { ImageFormat, ModelName, RemovalOptions } from '$lib/types';

// Base64 inflates the image by ~4/3 and RunPod caps a /runsync request at 20 MB,
// so 10 MiB of raw image leaves comfortable headroom.
const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
const MODELS: ModelName[] = ['general', 'lite', 'matting'];
const FORMATS: ImageFormat[] = ['png', 'webp'];

function parseOptions(params: URLSearchParams): RemovalOptions | string {
	const model = (params.get('model') || 'general') as ModelName;
	const format = (params.get('format') || 'png') as ImageFormat;
	const resolution = Number(params.get('resolution') || 1024);
	if (!MODELS.includes(model)) return `Unknown model '${model}'`;
	if (!FORMATS.includes(format)) return `Unknown format '${format}'`;
	if (!Number.isInteger(resolution) || resolution < 256 || resolution > 2048 || resolution % 32) {
		return 'Resolution must be a multiple of 32 between 256 and 2048';
	}
	return { model, format, resolution };
}

/**
 * Remove the background of one image. The body is the raw image bytes
 * (Content-Type = the image MIME), with the options in query params. Sending it
 * as a non-form content type keeps it clear of SvelteKit's CSRF form check.
 * Waits for the job and returns the worker's result, mask and cutout inline.
 */
export const POST: RequestHandler = async ({ request, url }) => {
	const options = parseOptions(url.searchParams);
	if (typeof options === 'string') return json({ message: options }, { status: 400 });

	const contentLength = Number(request.headers.get('content-length') || 0);
	if (contentLength > MAX_UPLOAD_BYTES) {
		return json({ message: 'Image exceeds the 10 MiB demo limit' }, { status: 413 });
	}
	const bytes = new Uint8Array(await request.arrayBuffer());
	if (!bytes.byteLength) return json({ message: 'Empty upload' }, { status: 400 });
	if (bytes.byteLength > MAX_UPLOAD_BYTES) {
		return json({ message: 'Image exceeds the 10 MiB demo limit' }, { status: 413 });
	}

	try {
		return json(await removeBackground(bytes, options));
	} catch (error) {
		const message = error instanceof Error ? error.message : 'Background removal failed';
		return json({ message }, { status: 502 });
	}
};
