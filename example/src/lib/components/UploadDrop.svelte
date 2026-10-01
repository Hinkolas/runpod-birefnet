<script lang="ts">
	import { ImageUp } from '@lucide/svelte';

	let { onfiles }: { onfiles: (files: File[]) => void } = $props();

	let dragging = $state(false);
	let input = $state<HTMLInputElement | null>(null);

	function handleDrop(event: DragEvent) {
		event.preventDefault();
		dragging = false;
		const files = [...(event.dataTransfer?.files ?? [])].filter((f) => f.type.startsWith('image/'));
		if (files.length) onfiles(files);
	}

	function handlePick(event: Event) {
		const target = event.currentTarget as HTMLInputElement;
		if (target.files?.length) onfiles([...target.files]);
		target.value = '';
	}
</script>

<button
	type="button"
	class="group flex w-full flex-col items-center gap-2 rounded-2xl border border-dashed px-4 py-7 text-center transition
		{dragging
		? 'border-violet-400 bg-violet-500/5'
		: 'border-zinc-700 hover:border-zinc-500 hover:bg-zinc-900/50'}"
	ondragover={(e) => {
		e.preventDefault();
		dragging = true;
	}}
	ondragleave={() => (dragging = false)}
	ondrop={handleDrop}
	onclick={() => input?.click()}
>
	<ImageUp class="h-7 w-7 text-zinc-500 transition group-hover:text-violet-400" strokeWidth={1.7} />
	<div>
		<p class="text-base font-medium text-zinc-200">Drop, paste or click to add images</p>
		<p class="mt-1 text-sm text-zinc-500">JPEG, PNG, WebP — up to 10 MB each</p>
	</div>
</button>

<input
	bind:this={input}
	type="file"
	accept="image/*"
	multiple
	class="hidden"
	onchange={handlePick}
/>
