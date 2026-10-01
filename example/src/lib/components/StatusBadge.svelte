<script lang="ts">
	import type { RunStatus } from '$lib/types';

	let { status, label = null }: { status: RunStatus; label?: string | null } = $props();

	const config: Record<RunStatus, { label: string; classes: string; pulse?: boolean }> = {
		processing: {
			label: 'Processing',
			classes: 'bg-violet-500/10 text-violet-300 ring-violet-500/30',
			pulse: true
		},
		done: { label: 'Done', classes: 'bg-emerald-500/10 text-emerald-300 ring-emerald-500/30' },
		error: { label: 'Failed', classes: 'bg-rose-500/10 text-rose-300 ring-rose-500/30' }
	};

	const current = $derived(config[status]);
</script>

<span
	class="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-sm font-medium ring-1 ring-inset {current.classes}"
>
	<span class="h-2 w-2 rounded-full bg-current" class:animate-pulse={current.pulse}></span>
	{label ?? current.label}
</span>
