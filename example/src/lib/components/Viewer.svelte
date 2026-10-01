<script lang="ts">
	import { Download, LoaderCircle } from '@lucide/svelte';
	import type { Run } from '$lib/types';

	type Mode = 'compare' | 'cutout' | 'mask' | 'original';
	type Backdrop = 'checker' | 'white' | 'black';

	let { run }: { run: Run } = $props();

	let mode = $state<Mode>('compare');
	let backdrop = $state<Backdrop>('checker');
	let split = $state(50); // compare divider position, % from the left

	const modes: { value: Mode; label: string }[] = [
		{ value: 'compare', label: 'Compare' },
		{ value: 'cutout', label: 'Cutout' },
		{ value: 'mask', label: 'Mask' },
		{ value: 'original', label: 'Original' }
	];
	const backdrops: { value: Backdrop; label: string; swatch: string }[] = [
		{ value: 'checker', label: 'Transparent', swatch: 'bg-checker' },
		{ value: 'white', label: 'White', swatch: 'bg-white' },
		{ value: 'black', label: 'Black', swatch: 'bg-black' }
	];

	const done = $derived(run.status === 'done' && run.cutoutUrl && run.maskUrl);
	const shown = $derived(done ? mode : 'original');
	const backdropClass = $derived(
		shown === 'mask' || shown === 'original'
			? 'bg-black'
			: backdrops.find((b) => b.value === backdrop)!.swatch
	);
	const baseName = $derived(run.file.name.replace(/\.[^.]+$/, '') || 'image');
</script>

<div class="overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-900/40">
	<div class="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-800 px-4 py-3">
		<div class="flex gap-1 rounded-lg border border-zinc-800 p-1" role="group" aria-label="View">
			{#each modes as m (m.value)}
				<button
					type="button"
					onclick={() => (mode = m.value)}
					disabled={!done}
					aria-pressed={shown === m.value}
					class="rounded-md px-3 py-1 text-sm transition disabled:cursor-not-allowed disabled:opacity-40 {shown ===
					m.value
						? 'bg-zinc-800 text-zinc-100'
						: 'text-zinc-500 hover:text-zinc-300'}"
				>
					{m.label}
				</button>
			{/each}
		</div>

		<div class="flex items-center gap-3">
			{#if shown === 'compare' || shown === 'cutout'}
				<div class="flex gap-1.5" role="group" aria-label="Backdrop">
					{#each backdrops as b (b.value)}
						<button
							type="button"
							onclick={() => (backdrop = b.value)}
							title={b.label}
							aria-label="{b.label} backdrop"
							aria-pressed={backdrop === b.value}
							class="h-6 w-6 rounded-md ring-1 transition {b.swatch} {backdrop === b.value
								? 'ring-2 ring-violet-400'
								: 'ring-zinc-700 hover:ring-zinc-500'}"
						></button>
					{/each}
				</div>
			{/if}
			{#if done}
				<!-- Downloads point at blob: URLs, not app routes. -->
				<!-- eslint-disable svelte/no-navigation-without-resolve -->
				<a
					href={run.cutoutUrl}
					download="{baseName}-cutout.{run.options.format}"
					class="flex items-center gap-1.5 rounded-lg bg-violet-600 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-violet-500"
				>
					<Download class="h-4 w-4" /> Cutout
				</a>
				<a
					href={run.maskUrl}
					download="{baseName}-mask.png"
					class="flex items-center gap-1.5 rounded-lg border border-zinc-700 px-3 py-1.5 text-sm text-zinc-300 transition hover:border-zinc-500 hover:bg-zinc-900"
				>
					<Download class="h-4 w-4" /> Mask
				</a>
				<!-- eslint-enable svelte/no-navigation-without-resolve -->
			{/if}
		</div>
	</div>

	<div class="flex justify-center p-4">
		<div class="relative max-w-full overflow-hidden rounded-lg {backdropClass}">
			<!-- The bottom layer sizes the stage; overlays stack on top of it. -->
			<img
				src={shown === 'cutout' || shown === 'compare'
					? run.cutoutUrl
					: shown === 'mask'
						? run.maskUrl
						: run.originalUrl}
				alt={run.file.name}
				class="block max-h-[65vh] w-auto max-w-full select-none"
				class:opacity-40={run.status === 'processing'}
				draggable="false"
			/>

			{#if shown === 'compare'}
				<img
					src={run.originalUrl}
					alt=""
					class="pointer-events-none absolute inset-0 h-full w-full select-none"
					style="clip-path: inset(0 {100 - split}% 0 0)"
					draggable="false"
				/>
				<div
					class="pointer-events-none absolute inset-y-0 w-0.5 -translate-x-1/2 bg-white/90 shadow-[0_0_0_1px_rgba(0,0,0,0.3)]"
					style="left: {split}%"
				>
					<div
						class="absolute top-1/2 left-1/2 h-8 w-8 -translate-1/2 rounded-full border-2 border-white bg-zinc-950/70 backdrop-blur"
					></div>
				</div>
				<span
					class="pointer-events-none absolute top-2 left-2 rounded bg-zinc-950/70 px-2 py-0.5 text-xs text-zinc-300"
					>Original</span
				>
				<span
					class="pointer-events-none absolute top-2 right-2 rounded bg-zinc-950/70 px-2 py-0.5 text-xs text-zinc-300"
					>Cutout</span
				>
				<input
					type="range"
					min="0"
					max="100"
					step="0.1"
					bind:value={split}
					aria-label="Compare original and cutout"
					class="absolute inset-0 h-full w-full cursor-ew-resize appearance-none opacity-0"
				/>
			{/if}

			{#if run.status === 'processing'}
				<div class="absolute inset-0 flex flex-col items-center justify-center gap-2">
					<LoaderCircle class="h-8 w-8 animate-spin text-violet-300" />
					<span class="rounded bg-zinc-950/70 px-2 py-0.5 text-sm text-zinc-200">
						Removing background…
					</span>
				</div>
			{/if}
		</div>
	</div>
</div>
