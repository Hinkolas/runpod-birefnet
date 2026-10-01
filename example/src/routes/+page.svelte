<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { ImageOff } from '@lucide/svelte';
	import type { RemovalOptions, RemovalResponse, Run } from '$lib/types';
	import { DEFAULT_OPTIONS, MODELS } from '$lib/presets';
	import { formatBytes, formatMs } from '$lib/format';
	import OptionsPanel from '$lib/components/OptionsPanel.svelte';
	import RunCard from '$lib/components/RunCard.svelte';
	import UploadDrop from '$lib/components/UploadDrop.svelte';
	import Viewer from '$lib/components/Viewer.svelte';

	// Runs live only in this tab: images and results are object URLs in browser memory.
	let runs = $state<Run[]>([]);
	let selectedId = $state<string | null>(null);
	let options = $state<RemovalOptions>(DEFAULT_OPTIONS);
	let now = $state(Date.now());

	const selected = $derived(runs.find((r) => r.id === selectedId) ?? null);
	const hasPending = $derived(runs.some((r) => r.status === 'processing'));
	const MAX_BYTES = 10 * 1024 * 1024;
	const OPTIONS_KEY = 'removal-options';

	onMount(() => {
		const saved = localStorage.getItem(OPTIONS_KEY);
		if (saved) {
			try {
				options = { ...DEFAULT_OPTIONS, ...JSON.parse(saved) };
			} catch {
				/* ignore corrupt options */
			}
		}
	});

	function saveOptions(next: RemovalOptions) {
		options = next;
		localStorage.setItem(OPTIONS_KEY, JSON.stringify(next));
	}

	// Tick a clock only while something is in flight, for the live elapsed time.
	let clock: ReturnType<typeof setInterval> | null = null;
	$effect(() => {
		if (hasPending && !clock) {
			clock = setInterval(() => (now = Date.now()), 250);
		} else if (!hasPending && clock) {
			clearInterval(clock);
			clock = null;
		}
	});
	onDestroy(() => {
		if (clock) clearInterval(clock);
		for (const run of runs) revoke(run);
	});

	function patch(id: string, changes: Partial<Run>) {
		runs = runs.map((r) => (r.id === id ? { ...r, ...changes } : r));
	}

	function revoke(run: Run) {
		URL.revokeObjectURL(run.originalUrl);
		if (run.maskUrl) URL.revokeObjectURL(run.maskUrl);
		if (run.cutoutUrl) URL.revokeObjectURL(run.cutoutUrl);
	}

	function base64ToUrl(data: string, type: string): string {
		const bytes = Uint8Array.from(atob(data), (c) => c.charCodeAt(0));
		return URL.createObjectURL(new Blob([bytes], { type }));
	}

	async function process(id: string, file: File, opts: RemovalOptions) {
		const startedAt = Date.now();
		now = startedAt;
		patch(id, { status: 'processing', startedAt, options: opts, error: null });
		try {
			const params = new URLSearchParams({
				model: opts.model,
				resolution: String(opts.resolution),
				format: opts.format
			});
			const res = await fetch(`/api/remove-background?${params}`, {
				method: 'POST',
				headers: { 'content-type': file.type || 'application/octet-stream' },
				body: file
			});
			const body = await res.json().catch(() => ({ message: `HTTP ${res.status}` }));
			if (!res.ok) throw new Error(body.message ?? `HTTP ${res.status}`);

			const response = body as RemovalResponse;
			const urls: Record<string, string> = {};
			for (const output of response.result.outputs) {
				if (output.data) urls[output.kind] = base64ToUrl(output.data, `image/${output.format}`);
				delete output.data; // don't keep megabytes of base64 around
			}
			const previous = runs.find((r) => r.id === id);
			if (previous?.maskUrl) URL.revokeObjectURL(previous.maskUrl);
			if (previous?.cutoutUrl) URL.revokeObjectURL(previous.cutoutUrl);
			patch(id, {
				status: 'done',
				response,
				maskUrl: urls.mask ?? null,
				cutoutUrl: urls.cutout ?? null,
				clientMs: Date.now() - startedAt
			});
		} catch (error) {
			patch(id, {
				status: 'error',
				error: error instanceof Error ? error.message : 'Background removal failed'
			});
		}
	}

	function addFiles(files: File[]) {
		for (const file of files) {
			const id = crypto.randomUUID();
			const run: Run = {
				id,
				file,
				originalUrl: URL.createObjectURL(file),
				maskUrl: null,
				cutoutUrl: null,
				options,
				status: 'processing',
				startedAt: Date.now(),
				clientMs: null,
				response: null,
				error: null
			};
			runs = [run, ...runs];
			selectedId = id;
			if (file.size > MAX_BYTES) {
				patch(id, { status: 'error', error: `${formatBytes(file.size)} exceeds the 10 MB limit` });
				continue;
			}
			process(id, file, options);
		}
	}

	function rerun(run: Run) {
		selectedId = run.id;
		process(run.id, run.file, options);
	}

	function remove(run: Run) {
		revoke(run);
		runs = runs.filter((r) => r.id !== run.id);
		if (selectedId === run.id) selectedId = runs[0]?.id ?? null;
	}

	function handlePaste(event: ClipboardEvent) {
		const files = [...(event.clipboardData?.files ?? [])].filter((f) =>
			f.type.startsWith('image/')
		);
		if (files.length) {
			event.preventDefault();
			addFiles(files);
		}
	}

	const result = $derived(selected?.response?.result ?? null);
	const output = $derived(result?.outputs.find((o) => o.kind === 'cutout') ?? null);
	const stages: { key: string; label: string }[] = [
		{ key: 'downloadMs', label: 'Download' },
		{ key: 'decodeMs', label: 'Decode' },
		{ key: 'preprocessMs', label: 'Preprocess' },
		{ key: 'inferenceMs', label: 'Inference' },
		{ key: 'postprocessMs', label: 'Postprocess' },
		{ key: 'encodeMs', label: 'Encode' }
	];
</script>

<svelte:head><title>Background Remover</title></svelte:head>
<svelte:window onpaste={handlePaste} />

<div class="min-h-screen bg-zinc-950 text-zinc-100">
	<header class="sticky top-0 z-30 border-b border-zinc-800/80 bg-zinc-950/80 backdrop-blur">
		<div class="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
			<div class="flex items-center gap-3">
				<div class="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-600">
					<ImageOff class="h-5 w-5 text-white" strokeWidth={1.8} />
				</div>
				<div>
					<h1 class="text-base font-semibold">Background Remover</h1>
					<p class="text-sm text-zinc-500">RunPod worker · BiRefNet · inline base64</p>
				</div>
			</div>
			{#if hasPending}
				<span class="flex items-center gap-1.5 text-sm text-violet-300">
					<span class="h-2 w-2 animate-pulse rounded-full bg-current"></span>
					Working…
				</span>
			{/if}
		</div>
	</header>

	<main class="mx-auto grid max-w-7xl gap-6 px-6 py-6 lg:grid-cols-[1fr_380px]">
		<!-- Viewer + details -->
		<section class="min-w-0 space-y-4">
			{#if selected}
				<Viewer run={selected} />

				<div class="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-6">
					<h2 class="truncate text-xl font-semibold" title={selected.file.name}>
						{selected.file.name}
					</h2>
					<dl class="mt-5 grid grid-cols-2 gap-4 text-base sm:grid-cols-4">
						<div>
							<dt class="text-sm text-zinc-500">Source</dt>
							<dd class="mt-1 text-zinc-200">
								{output ? `${output.width}×${output.height}` : '—'} · {formatBytes(
									selected.file.size
								)}
							</dd>
						</div>
						<div>
							<dt class="text-sm text-zinc-500">Model</dt>
							<dd class="mt-1 text-zinc-200">
								{MODELS.find((m) => m.value === selected.options.model)?.label} · {selected.options
									.resolution}px
							</dd>
						</div>
						<div>
							<dt class="text-sm text-zinc-500">Cutout</dt>
							<dd class="mt-1 text-zinc-200">
								{output ? `${output.format.toUpperCase()} · ${formatBytes(output.bytes)}` : '—'}
							</dd>
						</div>
						<div>
							<dt class="text-sm text-zinc-500">GPU</dt>
							<dd class="mt-1 truncate text-zinc-200" title={result?.worker.device}>
								{result?.worker.device.replace(/^NVIDIA /, '') ?? '—'}
							</dd>
						</div>
						<div>
							<dt class="text-sm text-zinc-500">Total (browser)</dt>
							<dd class="mt-1 text-zinc-200">{formatMs(selected.clientMs)}</dd>
						</div>
						<div>
							<dt class="text-sm text-zinc-500">Queue / cold start</dt>
							<dd class="mt-1 text-zinc-200">
								{formatMs(selected.response?.delayTimeMs)}
								{#if result?.worker.coldStart}
									<span
										class="ml-1 rounded bg-sky-500/10 px-1.5 py-0.5 text-xs text-sky-300 ring-1 ring-sky-500/30 ring-inset"
										>cold</span
									>
								{/if}
							</dd>
						</div>
						<div>
							<dt class="text-sm text-zinc-500">Compute (billed)</dt>
							<dd class="mt-1 text-zinc-200">{formatMs(selected.response?.executionTimeMs)}</dd>
						</div>
						<div>
							<dt class="text-sm text-zinc-500">App</dt>
							<dd class="mt-1 text-zinc-200">
								{(result?.metadata.app as string | undefined) ?? '—'}
							</dd>
						</div>
					</dl>

					{#if result}
						<div class="mt-5 flex flex-wrap gap-2">
							{#each stages as stage (stage.key)}
								{#if result.timings[stage.key] !== undefined}
									<span class="rounded-md bg-zinc-800 px-2.5 py-1 font-mono text-sm text-zinc-300">
										{stage.label} · {formatMs(result.timings[stage.key])}
									</span>
								{/if}
							{/each}
							{#if result.worker.modelLoadMs !== null}
								<span
									class="rounded-md bg-amber-500/10 px-2.5 py-1 font-mono text-sm text-amber-300"
								>
									Model load · {formatMs(result.worker.modelLoadMs)}
								</span>
							{/if}
						</div>
					{/if}

					{#if selected.status === 'error' && selected.error}
						<p
							class="mt-5 rounded-lg border border-rose-500/30 bg-rose-500/5 px-3 py-2 font-mono text-sm break-words text-rose-300"
						>
							{selected.error}
						</p>
					{/if}
				</div>
			{:else}
				<div
					class="flex aspect-video flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-zinc-800 text-center"
				>
					<ImageOff class="h-10 w-10 text-zinc-700" strokeWidth={1.5} />
					<p class="text-base text-zinc-400">Add an image to remove its background</p>
					<p class="text-sm text-zinc-600">
						The first request after the endpoint scaled to zero pays a cold start.
					</p>
				</div>
			{/if}
		</section>

		<!-- Options + history -->
		<aside class="space-y-4">
			<UploadDrop onfiles={addFiles} />
			<OptionsPanel {options} onchange={saveOptions} />

			<h2 class="px-1 text-sm font-medium tracking-wide text-zinc-500 uppercase">
				Images · {runs.length}
			</h2>

			<div class="space-y-2.5">
				{#each runs as run (run.id)}
					<RunCard
						{run}
						{now}
						selected={run.id === selectedId}
						onselect={(r) => (selectedId = r.id)}
						onrerun={rerun}
						ondelete={remove}
					/>
				{:else}
					<p
						class="rounded-xl border border-dashed border-zinc-800 px-4 py-8 text-center text-base text-zinc-600"
					>
						No images yet. Results stay in this tab only.
					</p>
				{/each}
			</div>
		</aside>
	</main>
</div>
