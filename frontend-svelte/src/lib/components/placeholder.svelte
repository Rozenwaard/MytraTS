<script lang="ts">
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle
	} from '$lib/components/ui/card';

	let {
		title,
		description = 'Заглушка — будет перенесён позже.'
	}: { title: string; description?: string } = $props();
</script>

<div class="h-full overflow-auto p-4">
	<Card>
		<CardHeader>
			<CardTitle>{title}</CardTitle>
			<CardDescription>{description}</CardDescription>
		</CardHeader>
		<CardContent class="text-sm text-muted-foreground">Раздел в разработке.</CardContent>
	</Card>
</div>
