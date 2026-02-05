<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import ThemeSwitcher from './ThemeSwitcher.svelte';

	export let neighborhood: string;
	export let jurisdiction: string;

	const dispatch = createEventDispatcher<{ neighborhoodChange: string }>();

	const neighborhoods = [
		'Downtown',
		'Gerstle Park',
		'Sun Valley',
		'Terra Linda',
		'San Rafael Meadows',
		'Peacock Gap',
		'Dominican',
		'Bret Harte',
		'All San Rafael'
	];

	let showDropdown = false;

	function selectNeighborhood(n: string) {
		dispatch('neighborhoodChange', n);
		showDropdown = false;
	}

	function getTimeframe(): string {
		const now = new Date();
		const day = now.toLocaleDateString('en-US', { weekday: 'long' });
		const date = now.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
		return `${day}, ${date}`;
	}
</script>

<header class="city-pulse-header">
	<div class="location-selector">
		<button
			class="location-button"
			on:click={() => (showDropdown = !showDropdown)}
			aria-expanded={showDropdown}
		>
			<span class="location-icon">📍</span>
			<span class="location-text">
				<span class="neighborhood">{neighborhood}</span>
				<span class="separator">·</span>
				<span class="timeframe">This Week</span>
			</span>
			<span class="edit-icon">✎</span>
		</button>

		{#if showDropdown}
			<div class="dropdown" role="listbox">
				{#each neighborhoods as n}
					<button
						class="dropdown-item"
						class:selected={n === neighborhood}
						on:click={() => selectNeighborhood(n)}
						role="option"
						aria-selected={n === neighborhood}
					>
						{n}
					</button>
				{/each}
			</div>
		{/if}
	</div>

	<div class="header-right">
		<ThemeSwitcher />
		<div class="jurisdiction-info">
			<span class="jurisdiction-name">{jurisdiction}</span>
			<span class="date">{getTimeframe()}</span>
		</div>
	</div>
</header>

<!-- Click outside to close dropdown -->
{#if showDropdown}
	<button class="backdrop" on:click={() => (showDropdown = false)} aria-label="Close menu"></button>
{/if}

<style>
	.city-pulse-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 0.75rem 0;
		border-bottom: 1px solid var(--border-color, #e0e0e0);
		margin-bottom: 0.5rem;
	}

	.location-selector {
		position: relative;
	}

	.location-button {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.5rem 0.75rem;
		background: var(--surface-color, #f5f5f5);
		border: 1px solid var(--border-color, #e0e0e0);
		border-radius: 8px;
		cursor: pointer;
		font-size: 0.875rem;
		transition: background 0.15s;
	}

	.location-button:hover {
		background: var(--hover-color, #ebebeb);
	}

	.location-icon {
		font-size: 1rem;
	}

	.location-text {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.neighborhood {
		font-weight: 500;
		color: var(--text-primary, #333);
	}

	.separator {
		color: var(--text-secondary, #999);
	}

	.timeframe {
		color: var(--text-secondary, #666);
	}

	.edit-icon {
		color: var(--text-secondary, #999);
		font-size: 0.875rem;
	}

	.dropdown {
		position: absolute;
		top: calc(100% + 4px);
		left: 0;
		min-width: 200px;
		background: var(--surface-color, #fff);
		border: 1px solid var(--border-color, #e0e0e0);
		border-radius: 8px;
		box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
		z-index: 100;
		overflow: hidden;
	}

	.dropdown-item {
		display: block;
		width: 100%;
		padding: 0.75rem 1rem;
		text-align: left;
		background: none;
		border: none;
		cursor: pointer;
		font-size: 0.875rem;
		color: var(--text-primary, #333);
		transition: background 0.15s;
	}

	.dropdown-item:hover {
		background: var(--hover-color, #f5f5f5);
	}

	.dropdown-item.selected {
		background: var(--primary-color-light, #eff6ff);
		color: var(--primary-color, #3b82f6);
		font-weight: 500;
	}

	.header-right {
		display: flex;
		align-items: center;
		gap: 1rem;
	}

	.jurisdiction-info {
		display: flex;
		flex-direction: column;
		align-items: flex-end;
		gap: 0.125rem;
	}

	.jurisdiction-name {
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-secondary, #666);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.date {
		font-size: 0.75rem;
		color: var(--text-secondary, #999);
	}

	.backdrop {
		position: fixed;
		inset: 0;
		background: transparent;
		border: none;
		cursor: default;
		z-index: 99;
	}

	@media (max-width: 640px) {
		.city-pulse-header {
			flex-direction: column;
			align-items: flex-start;
			gap: 0.5rem;
		}

		.header-right {
			width: 100%;
			justify-content: space-between;
		}

		.jurisdiction-info {
			align-items: flex-start;
		}
	}
</style>
