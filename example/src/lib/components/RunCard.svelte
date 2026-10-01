<script lang="ts">
	import { RotateCcw, Trash2 } from '@lucide/svelte';
	import type { Run } from '$lib/types';
	import { MODELS } from '$lib/presets';
	import { formatMs } from '$lib/format';
	import StatusBadge from './StatusBadge.svelte';

	let {
		run,
		now,
		selected = false,
		onselect,
		onrerun,
		ondelete
	}: {
		run: Run;
		now: number; // ticks while processing, for the live elapsed time
		selected?: boolean;
		onselect: (run: Run) => void;
		onrerun: (run: Run) => void;
		ondelete: (run: Run) => void;
	} = $props();

	const busy = $derived(run.status === 'processing');
	const modelLabel = $derived(MODELS.find((m) => m.value === run.options.model)?.label);
	const badgeLabel = $derived(
		busy
			? `Processing ${Math.floor((now - run.startedAt) / 1000)}s`
			: run.status === 'done'
				? formatMs(run.clientMs)
				: null
	);
</script>

<div
	class="group rounded-xl border p-3 transition {selected
		? 'border-violet-500/60 bg-violet-500/5'
		: 'border-zinc-800 bg-zinc-900/40 hover:border-zinc-700'}"
>
	<div class="flex gap-3">
		<button
			type="button"
			onclick={() => onselect(run)}
			class="relative h-16 w-16 shrink-0 overflow-hidden rounded-lg ring-1 ring-zinc-800 {run.cutoutUrl
				? 'bg-checker'
				: 'bg-black'}"
			aria-label="Select {run.file.name}"
		>
			<img
				src={run.cutoutUrl ?? run.originalUrl}
				alt=""
				class="h-full w-full object-contain"
				class:opacity-40={busy}
			/>
		</button>

		<div class="min-w-0 flex-1">
			<button type="button" onclick={() => onselect(run)} class="block w-full text-left">
				<p class="truncate text-base font-medium text-zinc-100" title={run.file.name}>
					{run.file.name}
				</p>
			</button>
			<p class="mt-0.5 text-sm text-zinc-500">
				{modelLabel} · {run.options.resolution}px · {run.options.format.toUpperCase()}
			</p>
			<div class="mt-1.5 flex items-center justify-between gap-2">
				<StatusBadge status={run.status} label={badgeLabel} />
				<div class="flex gap-1 opacity-60 transition group-hover:opacity-100">
					<button
						type="button"
						onclick={() => onrerun(run)}
						disabled={busy}
						class="rounded-md p-1.5 text-zinc-400 transition hover:bg-zinc-800 hover:text-zinc-100 disabled:opacity-40"
						title="Run again with the current options"
						aria-label="Run {run.file.name} again"
					>
						<RotateCcw class="h-4 w-4" />
					</button>
					<button
						type="button"
						onclick={() => ondelete(run)}
						disabled={busy}
						class="rounded-md p-1.5 text-zinc-400 transition hover:bg-zinc-800 hover:text-rose-400 disabled:opacity-40"
						aria-label="Remove {run.file.name}"
					>
						<Trash2 class="h-4 w-4" />
					</button>
				</div>
			</div>
		</div>
	</div>
</div>
