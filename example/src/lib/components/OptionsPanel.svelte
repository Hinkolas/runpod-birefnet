<script lang="ts">
	import type { RemovalOptions } from '$lib/types';
	import { FORMATS, MODELS, RESOLUTIONS } from '$lib/presets';

	let {
		options,
		onchange
	}: { options: RemovalOptions; onchange: (options: RemovalOptions) => void } = $props();

	function set<K extends keyof RemovalOptions>(key: K, value: RemovalOptions[K]) {
		onchange({ ...options, [key]: value });
	}
</script>

<div class="space-y-4 rounded-2xl border border-zinc-800 bg-zinc-900/40 p-4">
	<fieldset>
		<legend class="text-sm text-zinc-500">Model</legend>
		<div class="mt-2 grid grid-cols-3 gap-1.5">
			{#each MODELS as model (model.value)}
				<button
					type="button"
					onclick={() => set('model', model.value)}
					aria-pressed={options.model === model.value}
					class="rounded-lg border px-2 py-2 text-left transition {options.model === model.value
						? 'border-violet-500/60 bg-violet-500/10'
						: 'border-zinc-800 hover:border-zinc-700'}"
				>
					<span class="block text-sm font-medium text-zinc-100">{model.label}</span>
					<span class="mt-0.5 block text-xs leading-snug text-zinc-500">{model.hint}</span>
				</button>
			{/each}
		</div>
	</fieldset>

	<div class="grid grid-cols-2 gap-3">
		<label class="block">
			<span class="text-sm text-zinc-500">Resolution</span>
			<select
				value={options.resolution}
				onchange={(e) => set('resolution', Number(e.currentTarget.value))}
				class="mt-2 block w-full rounded-lg border-zinc-800 bg-zinc-900 py-2 text-sm text-zinc-100 focus:border-violet-500 focus:ring-violet-500"
			>
				{#each RESOLUTIONS as resolution (resolution)}
					<option value={resolution}>
						{resolution}px{resolution === 1024 ? ' (native)' : ''}
					</option>
				{/each}
			</select>
		</label>

		<fieldset>
			<legend class="text-sm text-zinc-500">Cutout format</legend>
			<div class="mt-2 grid grid-cols-2 gap-1 rounded-lg border border-zinc-800 p-1">
				{#each FORMATS as format (format.value)}
					<button
						type="button"
						onclick={() => set('format', format.value)}
						aria-pressed={options.format === format.value}
						class="rounded-md py-1 text-sm transition {options.format === format.value
							? 'bg-zinc-800 text-zinc-100'
							: 'text-zinc-500 hover:text-zinc-300'}"
					>
						{format.label}
					</button>
				{/each}
			</div>
		</fieldset>
	</div>
</div>
