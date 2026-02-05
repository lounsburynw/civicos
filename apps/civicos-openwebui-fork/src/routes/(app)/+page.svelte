<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { toast } from 'svelte-sonner';
	import Chat from '$lib/components/chat/Chat.svelte';
	import { artifactContents, showArtifacts, showControls } from '$lib/stores';

	// Modal MCP server endpoint
	const MCP_API_URL = 'https://lounsburynw--civicos-san-rafael-mcpserver-mcp-endpoint.modal.run';

	// Loading state
	let isLoading = false;

	onMount(() => {
		if ($page.url.searchParams.get('error')) {
			toast.error($page.url.searchParams.get('error') || 'An unknown error occurred.');
		}

		// CivicOS: Listen for civic intent from chat to auto-open City Pulse
		const handleCivicIntent = () => {
			// Only trigger if not already loading and no artifact currently shown
			if (!isLoading) {
				openCityPulse();
			}
		};
		window.addEventListener('civicintent', handleCivicIntent);
		return () => window.removeEventListener('civicintent', handleCivicIntent);
	});

	// Category metadata for issue icons
	const categoryMeta: Record<string, { label: string; icon: string; color: string }> = {
		traffic_signal: { label: 'Traffic Signals', icon: '🚦', color: '#fef3c7' },
		parking: { label: 'Parking', icon: '🅿️', color: '#dbeafe' },
		illegal_dumping: { label: 'Illegal Dumping', icon: '🗑️', color: '#fee2e2' },
		trees_vegetation: { label: 'Trees & Vegetation', icon: '🌳', color: '#dcfce7' },
		operational: { label: 'City Operations', icon: '⚙️', color: '#f3f4f6' },
		stormwater: { label: 'Stormwater', icon: '🌧️', color: '#dbeafe' },
		pothole: { label: 'Potholes', icon: '🕳️', color: '#fef3c7' },
		graffiti: { label: 'Graffiti', icon: '🎨', color: '#fce7f3' },
		parks: { label: 'Parks', icon: '🏞️', color: '#dcfce7' },
		roads: { label: 'Roads & Sidewalks', icon: '🛣️', color: '#f3f4f6' },
		safety: { label: 'Public Safety', icon: '🚨', color: '#fee2e2' },
		other: { label: 'Other', icon: '📋', color: '#f3f4f6' },
	};

	// Fetch live data from Modal MCP API
	async function fetchCityPulse(): Promise<{
		decisions_this_week: Array<{ title: string; date: string; time: string }>;
		recent_outcomes: Array<{ title: string; outcome: string; date: string }>;
		community_pulse: { total_issues: number; top_types: Record<string, number> };
		jurisdiction: string;
		generated_at: string;
	}> {
		const response = await fetch(`${MCP_API_URL}/api/tools/city-pulse`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ days_ahead: 14, days_back: 30 }),
		});

		if (!response.ok) {
			throw new Error(`Failed to fetch city pulse: ${response.status}`);
		}

		const result = await response.json();
		return result.data;
	}

	// Parse date string (handles both ISO "2026-02-04" and formatted "Wed, Feb 04")
	function parseDate(dateStr: string): { day: string; month: string } {
		if (!dateStr) return { day: '--', month: '' };

		// Try ISO format first (2026-02-04)
		const isoMatch = dateStr.match(/^\d{4}-(\d{2})-(\d{2})/);
		if (isoMatch) {
			const monthNum = parseInt(isoMatch[1], 10);
			const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
			return { day: isoMatch[2], month: months[monthNum - 1] || '' };
		}

		// Try formatted "Wed, Feb 04" style
		const parts = dateStr.split(', ');
		if (parts.length >= 2) {
			const [month, day] = parts[1].split(' ');
			return { day: day || '--', month: month || '' };
		}

		return { day: '--', month: '' };
	}

	// Generate widget HTML with live data
	function generatePulseWidget(data: Awaited<ReturnType<typeof fetchCityPulse>>): string {
		const cityName = data.jurisdiction?.replace('city-', '').split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ') || 'San Rafael';

		// Transform meetings
		const meetingsHtml = data.decisions_this_week?.length > 0
			? data.decisions_this_week.slice(0, 3).map(m => {
				const { day, month } = parseDate(m.date);
				return `
				<div class="meeting-item">
					<div class="meeting-date-box">
						<div class="meeting-day">${day}</div>
						<div class="meeting-month">${month}</div>
					</div>
					<div class="meeting-content">
						<div class="meeting-title">${escapeHtml(m.title)}</div>
						<div class="meeting-time">${m.time || 'Time TBD'}</div>
					</div>
				</div>
			`}).join('')
			: '<div class="empty-state">No upcoming meetings scheduled</div>';

		// Transform recent decisions
		const decisionsHtml = data.recent_outcomes?.length > 0
			? data.recent_outcomes.slice(0, 3).map(d => `
				<div class="decision-item">
					<div class="decision-outcome ${d.outcome?.toLowerCase().includes('approved') ? 'approved' : d.outcome?.toLowerCase().includes('denied') ? 'denied' : 'other'}">
						${d.outcome?.toLowerCase().includes('approved') ? '✓' : d.outcome?.toLowerCase().includes('denied') ? '✗' : '•'}
					</div>
					<div class="decision-content">
						<div class="decision-title">${escapeHtml(d.title)}</div>
						<div class="decision-date">${d.date} · ${d.outcome || 'Decided'}</div>
					</div>
				</div>
			`).join('')
			: '<div class="empty-state">No recent decisions</div>';

		// Transform issue clusters
		const topTypes = Object.entries(data.community_pulse?.top_types || {})
			.sort(([, a], [, b]) => (b as number) - (a as number))
			.slice(0, 4);

		const issuesHtml = topTypes.length > 0
			? topTypes.map(([type, count]) => {
				const meta = categoryMeta[type] || { label: type.replace(/_/g, ' '), icon: '📍', color: '#f3f4f6' };
				return `
					<div class="issue-cluster">
						<div class="issue-icon" style="background: ${meta.color};">${meta.icon}</div>
						<div class="issue-count">${count}</div>
						<div class="issue-label">${meta.label}</div>
					</div>
				`;
			}).join('')
			: '<div class="empty-state" style="width:100%">No issue data available</div>';

		const totalIssues = data.community_pulse?.total_issues || 0;
		const upcomingCount = data.decisions_this_week?.length || 0;

		return `<!DOCTYPE html>
<html lang="en">
<head>
	<meta charset="UTF-8">
	<meta name="viewport" content="width=device-width, initial-scale=1.0">
	<title>City Pulse - ${cityName}</title>
	<style>
		:root {
			--primary: #3b82f6;
			--primary-dark: #1d4ed8;
			--success: #22c55e;
			--warning: #f59e0b;
			--danger: #ef4444;
			--text: #1a1a1a;
			--text-muted: #666;
			--text-light: #999;
			--border: #e5e5e5;
			--bg: #fafafa;
			--card-bg: white;
		}

		* { box-sizing: border-box; margin: 0; padding: 0; }

		body {
			font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
			background: var(--bg);
			color: var(--text);
			line-height: 1.5;
		}

		.widget {
			max-width: 500px;
			margin: 0 auto;
			background: var(--card-bg);
			border-radius: 16px;
			box-shadow: 0 4px 12px rgba(0,0,0,0.08);
			overflow: hidden;
		}

		.header {
			padding: 20px;
			background: linear-gradient(135deg, var(--primary-dark) 0%, var(--primary) 100%);
			color: white;
		}

		.header-top {
			display: flex;
			justify-content: space-between;
			align-items: center;
			margin-bottom: 8px;
		}

		.city-name { font-size: 20px; font-weight: 700; }

		.live-badge {
			display: flex;
			align-items: center;
			gap: 6px;
			font-size: 12px;
			font-weight: 500;
			background: rgba(255,255,255,0.2);
			padding: 4px 10px;
			border-radius: 12px;
		}

		.live-dot {
			width: 8px;
			height: 8px;
			background: #4ade80;
			border-radius: 50%;
			animation: pulse 2s infinite;
		}

		@keyframes pulse {
			0%, 100% { opacity: 1; transform: scale(1); }
			50% { opacity: 0.6; transform: scale(1.2); }
		}

		.header-subtitle { font-size: 14px; opacity: 0.9; }

		.stats-bar {
			display: flex;
			background: rgba(0,0,0,0.1);
			margin: 16px -20px -20px;
			padding: 12px 20px;
		}

		.stat { flex: 1; text-align: center; }
		.stat-value { font-size: 20px; font-weight: 700; }
		.stat-label {
			font-size: 11px;
			opacity: 0.8;
			text-transform: uppercase;
			letter-spacing: 0.5px;
		}

		.section {
			padding: 16px 20px;
			border-bottom: 1px solid var(--border);
		}
		.section:last-child { border-bottom: none; }

		.section-header {
			display: flex;
			justify-content: space-between;
			align-items: center;
			margin-bottom: 12px;
		}

		.section-title {
			font-size: 12px;
			font-weight: 600;
			text-transform: uppercase;
			letter-spacing: 0.5px;
			color: var(--text-muted);
			display: flex;
			align-items: center;
			gap: 6px;
		}

		/* Meetings */
		.meeting-item {
			display: flex;
			gap: 12px;
			padding: 12px;
			background: var(--bg);
			border-radius: 10px;
			margin-bottom: 8px;
		}
		.meeting-item:last-child { margin-bottom: 0; }

		.meeting-date-box {
			display: flex;
			flex-direction: column;
			align-items: center;
			justify-content: center;
			min-width: 48px;
			padding: 8px;
			background: var(--card-bg);
			border-radius: 8px;
			border: 1px solid var(--border);
		}

		.meeting-day {
			font-size: 18px;
			font-weight: 700;
			color: var(--primary);
			line-height: 1;
		}

		.meeting-month {
			font-size: 10px;
			text-transform: uppercase;
			color: var(--text-muted);
		}

		.meeting-content { flex: 1; min-width: 0; }
		.meeting-title {
			font-size: 14px;
			font-weight: 600;
			color: var(--text);
			margin-bottom: 2px;
		}
		.meeting-time { font-size: 12px; color: var(--text-muted); }

		/* Decisions */
		.decision-item {
			display: flex;
			gap: 12px;
			padding: 10px 12px;
			background: var(--bg);
			border-radius: 10px;
			margin-bottom: 8px;
			align-items: flex-start;
		}
		.decision-item:last-child { margin-bottom: 0; }

		.decision-outcome {
			width: 24px;
			height: 24px;
			border-radius: 50%;
			display: flex;
			align-items: center;
			justify-content: center;
			font-size: 12px;
			font-weight: 600;
			flex-shrink: 0;
		}
		.decision-outcome.approved { background: #dcfce7; color: var(--success); }
		.decision-outcome.denied { background: #fee2e2; color: var(--danger); }
		.decision-outcome.other { background: #f3f4f6; color: var(--text-muted); }

		.decision-content { flex: 1; min-width: 0; }
		.decision-title {
			font-size: 13px;
			font-weight: 500;
			color: var(--text);
			white-space: nowrap;
			overflow: hidden;
			text-overflow: ellipsis;
		}
		.decision-date { font-size: 11px; color: var(--text-muted); }

		/* Issues */
		.issues-grid {
			display: flex;
			gap: 8px;
			flex-wrap: wrap;
		}

		.issue-cluster {
			flex: 1;
			min-width: 100px;
			padding: 12px;
			background: var(--bg);
			border-radius: 10px;
			text-align: center;
		}

		.issue-icon {
			width: 36px;
			height: 36px;
			border-radius: 10px;
			display: flex;
			align-items: center;
			justify-content: center;
			font-size: 18px;
			margin: 0 auto 6px;
		}

		.issue-count {
			font-size: 18px;
			font-weight: 700;
			color: var(--text);
		}

		.issue-label {
			font-size: 11px;
			color: var(--text-muted);
		}

		.empty-state {
			text-align: center;
			padding: 16px;
			color: var(--text-muted);
			font-size: 13px;
		}

		.footer {
			padding: 12px 20px;
			background: var(--bg);
			text-align: center;
			font-size: 11px;
			color: var(--text-light);
		}

		.footer a {
			color: var(--primary);
			text-decoration: none;
		}
	</style>
</head>
<body>
	<div class="widget">
		<div class="header">
			<div class="header-top">
				<div class="city-name">${escapeHtml(cityName)}</div>
				<div class="live-badge">
					<span class="live-dot"></span>
					Live
				</div>
			</div>
			<div class="header-subtitle">Your civic pulse for ${new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}</div>

			<div class="stats-bar">
				<div class="stat">
					<div class="stat-value">${upcomingCount}</div>
					<div class="stat-label">Meetings</div>
				</div>
				<div class="stat">
					<div class="stat-value">${data.recent_outcomes?.length || 0}</div>
					<div class="stat-label">Decisions</div>
				</div>
				<div class="stat">
					<div class="stat-value">${totalIssues}</div>
					<div class="stat-label">Open Issues</div>
				</div>
			</div>
		</div>

		<div class="section">
			<div class="section-header">
				<div class="section-title">📅 Upcoming Meetings</div>
			</div>
			${meetingsHtml}
		</div>

		<div class="section">
			<div class="section-header">
				<div class="section-title">⚖️ Recent Decisions</div>
			</div>
			${decisionsHtml}
		</div>

		<div class="section">
			<div class="section-header">
				<div class="section-title">📍 Community Issues</div>
			</div>
			<div class="issues-grid">
				${issuesHtml}
			</div>
		</div>

		<div class="footer">
			Updated ${new Date(data.generated_at).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })} ·
			<a href="https://civicosproject.org" target="_blank">Powered by CivicOS</a>
		</div>
	</div>
</body>
</html>`;
	}

	// Loading widget HTML
	const loadingWidgetHtml = `<!DOCTYPE html>
<html lang="en">
<head>
	<meta charset="UTF-8">
	<style>
		* { box-sizing: border-box; margin: 0; padding: 0; }
		body {
			font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
			background: #fafafa;
			padding: 16px;
		}
		.widget {
			max-width: 500px;
			margin: 0 auto;
			background: white;
			border-radius: 16px;
			box-shadow: 0 4px 12px rgba(0,0,0,0.08);
			overflow: hidden;
		}
		.header {
			padding: 20px;
			background: linear-gradient(135deg, #1d4ed8 0%, #3b82f6 100%);
		}
		.skeleton {
			background: linear-gradient(90deg, rgba(255,255,255,0.1) 25%, rgba(255,255,255,0.2) 50%, rgba(255,255,255,0.1) 75%);
			background-size: 200% 100%;
			animation: shimmer 1.5s infinite;
			border-radius: 8px;
		}
		@keyframes shimmer {
			0% { background-position: 200% 0; }
			100% { background-position: -200% 0; }
		}
		.section { padding: 16px 20px; border-bottom: 1px solid #e5e5e5; }
		.skeleton-dark {
			background: linear-gradient(90deg, #e5e5e5 25%, #d4d4d4 50%, #e5e5e5 75%);
			background-size: 200% 100%;
			animation: shimmer 1.5s infinite;
			border-radius: 8px;
		}
		.loading-text {
			text-align: center;
			color: #666;
			font-size: 13px;
			padding: 8px 0;
		}
	</style>
</head>
<body>
	<div class="widget">
		<div class="header">
			<div class="skeleton" style="height: 24px; width: 50%; margin-bottom: 8px;"></div>
			<div class="skeleton" style="height: 16px; width: 70%;"></div>
		</div>
		<div class="section">
			<div class="skeleton-dark" style="height: 16px; width: 40%; margin-bottom: 12px;"></div>
			<div class="skeleton-dark" style="height: 60px; margin-bottom: 8px;"></div>
			<div class="skeleton-dark" style="height: 60px;"></div>
		</div>
		<div class="section">
			<div class="loading-text">Loading live data from San Rafael...</div>
		</div>
	</div>
</body>
</html>`;

	function escapeHtml(str: string | undefined | null): string {
		if (!str) return '';
		return String(str)
			.replace(/&/g, '&amp;')
			.replace(/</g, '&lt;')
			.replace(/>/g, '&gt;')
			.replace(/"/g, '&quot;');
	}

	async function openCityPulse() {
		if (isLoading) return;
		isLoading = true;

		// Show loading state immediately
		artifactContents.set([{ type: 'iframe', content: loadingWidgetHtml }]);
		showControls.set(true);
		showArtifacts.set(true);

		try {
			const data = await fetchCityPulse();
			const widgetHtml = generatePulseWidget(data);
			artifactContents.set([{ type: 'iframe', content: widgetHtml }]);
			toast.success('City Pulse loaded with live data');
		} catch (error) {
			console.error('Failed to fetch city pulse:', error);
			toast.error('Failed to load live data. Using cached view.');
			// Keep the loading state visible with error message
			artifactContents.set([{
				type: 'iframe',
				content: loadingWidgetHtml.replace(
					'Loading live data from San Rafael...',
					'Unable to connect to server. Please try again.'
				)
			}]);
		} finally {
			isLoading = false;
		}
	}
</script>

<svelte:head>
	<title>CivicOS - San Rafael</title>
</svelte:head>

<!-- Open WebUI Chat -->
<Chat />

<!-- Dev: City Pulse Button -->
<button class="city-pulse-btn" on:click={openCityPulse} disabled={isLoading}>
	{#if isLoading}
		⏳ Loading...
	{:else}
		🏛️ City Pulse
	{/if}
</button>

<style>
	.city-pulse-btn {
		position: fixed;
		bottom: 20px;
		right: 20px;
		padding: 0.75rem 1.25rem;
		background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%);
		color: white;
		border: none;
		border-radius: 12px;
		font-size: 0.875rem;
		font-weight: 600;
		cursor: pointer;
		box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4);
		z-index: 1000;
		transition: transform 0.2s, box-shadow 0.2s, opacity 0.2s;
	}

	.city-pulse-btn:hover:not(:disabled) {
		transform: translateY(-2px);
		box-shadow: 0 6px 16px rgba(59, 130, 246, 0.5);
	}

	.city-pulse-btn:disabled {
		opacity: 0.7;
		cursor: wait;
	}
</style>
