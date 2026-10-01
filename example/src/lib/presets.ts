import type { ImageFormat, ModelName, RemovalOptions } from '$lib/types';

export const DEFAULT_OPTIONS: RemovalOptions = {
	model: 'general',
	resolution: 1024,
	format: 'png'
};

export const MODELS: { value: ModelName; label: string; hint: string }[] = [
	{ value: 'general', label: 'General', hint: 'Best all-round quality' },
	{ value: 'lite', label: 'Lite', hint: 'Faster, rougher edges' },
	{ value: 'matting', label: 'Matting', hint: 'Soft alpha for hair & fur' }
];

/** BiRefNet is trained at 1024; higher helps fine detail at ~quadratic cost. */
export const RESOLUTIONS = [512, 768, 1024, 1536, 2048];

export const FORMATS: { value: ImageFormat; label: string }[] = [
	{ value: 'png', label: 'PNG' },
	{ value: 'webp', label: 'WebP' }
];
