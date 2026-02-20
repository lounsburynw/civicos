<script lang="ts">
  import { untrack } from 'svelte';
  import 'leaflet/dist/leaflet.css';
  import L from 'leaflet';

  // Local type (mirrors @civicos/client IssuePoint)
  interface IssuePoint {
    lat: number;
    lng: number;
    type: string;
    status: string;
    address: string;
    created_at: string;
  }

  interface ApiClient {
    getIssueGeography(limit?: number): Promise<{ points: IssuePoint[] }>;
  }

  // Props
  let {
    api,
    autoload = false,
  }: {
    api: ApiClient;
    autoload?: boolean;
  } = $props();

  // === State ===
  let issuePoints: IssuePoint[] = $state([]);
  let loading = $state(false);
  let loaded = $state(false);
  let leafletMap: L.Map | null = null;
  let mapContainer: HTMLDivElement | undefined = $state(undefined);
  let mapExpanded = $state(false);
  let mapDaysFilter: number | null = $state(null);
  let activeIssueFilters = $state(new Set(Object.keys(ISSUE_COLORS)));
  let issueLayerGroups = new Map<string, L.LayerGroup>();

  // === Constants ===
  const ISSUE_COLORS: Record<string, string> = {
    'Pothole': '#ef4444',
    'Graffiti': '#f59e0b',
    'Illegal Dumping': '#8b5cf6',
    'Sidewalk': '#3b82f6',
    'Street Light': '#eab308',
    'Tree': '#22c55e',
    'Traffic': '#f97316',
    'Other': '#6b7280',
  };

  const MAP_DAYS_OPTIONS: { label: string; value: number | null }[] = [
    { label: '7d', value: 7 },
    { label: '30d', value: 30 },
    { label: '90d', value: 90 },
    { label: 'All', value: null },
  ];

  // === Helpers ===
  function getIssueColor(type: string): string {
    for (const [key, color] of Object.entries(ISSUE_COLORS)) {
      if (type.toLowerCase().includes(key.toLowerCase())) return color;
    }
    return ISSUE_COLORS['Other'];
  }

  function getIssueCategory(type: string): string {
    for (const key of Object.keys(ISSUE_COLORS)) {
      if (type.toLowerCase().includes(key.toLowerCase())) return key;
    }
    return 'Other';
  }

  function issuesInWindow(points: IssuePoint[], days: number | null): IssuePoint[] {
    if (days === null) return points;
    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - days);
    return points.filter(pt => new Date(pt.created_at) >= cutoff);
  }

  function timeFilteredPoints(): IssuePoint[] {
    return issuesInWindow(issuePoints, mapDaysFilter);
  }

  function categoryCounts(): Map<string, number> {
    const counts = new Map<string, number>();
    for (const cat of Object.keys(ISSUE_COLORS)) counts.set(cat, 0);
    for (const pt of timeFilteredPoints()) {
      const cat = getIssueCategory(pt.type);
      counts.set(cat, (counts.get(cat) || 0) + 1);
    }
    return counts;
  }

  function issueTrend(): { pct: number; direction: 'up' | 'down' | 'flat' } | null {
    const now = new Date();
    const d30ago = new Date(); d30ago.setDate(now.getDate() - 30);
    const d60ago = new Date(); d60ago.setDate(now.getDate() - 60);
    const current = issuePoints.filter(pt => new Date(pt.created_at) >= d30ago).length;
    const previous = issuePoints.filter(pt => {
      const d = new Date(pt.created_at);
      return d >= d60ago && d < d30ago;
    }).length;
    if (previous === 0 && current === 0) return null;
    if (previous === 0) return { pct: 100, direction: 'up' };
    const pct = Math.round(((current - previous) / previous) * 100);
    if (pct === 0) return { pct: 0, direction: 'flat' };
    return { pct: Math.abs(pct), direction: pct > 0 ? 'up' : 'down' };
  }

  function filteredIssueCount(): number {
    return timeFilteredPoints().filter(pt => activeIssueFilters.has(getIssueCategory(pt.type))).length;
  }

  // === Map Operations ===
  function toggleMapExpanded() {
    mapExpanded = !mapExpanded;
    setTimeout(() => leafletMap?.invalidateSize(), 250);
  }

  function toggleIssueFilter(category: string) {
    if (activeIssueFilters.has(category)) {
      activeIssueFilters.delete(category);
      const lg = issueLayerGroups.get(category);
      if (lg && leafletMap) leafletMap.removeLayer(lg);
    } else {
      activeIssueFilters.add(category);
      const lg = issueLayerGroups.get(category);
      if (lg && leafletMap) leafletMap.addLayer(lg);
    }
    activeIssueFilters = new Set(activeIssueFilters);
  }

  function setDaysFilter(days: number | null) {
    mapDaysFilter = days;
    rebuildMapMarkers();
  }

  function rebuildMapMarkers() {
    if (!leafletMap) return;
    for (const lg of issueLayerGroups.values()) {
      leafletMap.removeLayer(lg);
    }
    issueLayerGroups.clear();
    const points = timeFilteredPoints();
    const grouped = new Map<string, L.CircleMarker[]>();
    for (const pt of points) {
      const cat = getIssueCategory(pt.type);
      const marker = L.circleMarker([pt.lat, pt.lng], {
        radius: 5,
        color: getIssueColor(pt.type),
        fillColor: getIssueColor(pt.type),
        fillOpacity: 0.7,
        weight: 1,
      }).bindPopup(`<b>${pt.type}</b><br>${pt.address}<br><small>${pt.status}</small>`);
      if (!grouped.has(cat)) grouped.set(cat, []);
      grouped.get(cat)!.push(marker);
    }
    for (const [cat, markers] of grouped) {
      const lg = L.layerGroup(markers);
      issueLayerGroups.set(cat, lg);
      if (activeIssueFilters.has(cat)) lg.addTo(leafletMap);
    }
  }

  function renderMap() {
    if (!mapContainer || issuePoints.length === 0) return;
    if (leafletMap) {
      leafletMap.invalidateSize();
      return;
    }

    leafletMap = L.map(mapContainer, {
      zoomControl: false,
      attributionControl: false,
    }).setView([37.9735, -122.5311], 13);

    L.control.zoom({ position: 'topright' }).addTo(leafletMap);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      maxZoom: 19,
    }).addTo(leafletMap);

    rebuildMapMarkers();

    if (issuePoints.length > 1) {
      const bounds = L.latLngBounds(issuePoints.map(p => [p.lat, p.lng] as [number, number]));
      leafletMap.fitBounds(bounds, { padding: [20, 20] });
    }

    setTimeout(() => leafletMap?.invalidateSize(), 200);
  }

  // === Data Loading ===
  export async function load() {
    if (loaded || loading) return;
    loading = true;
    try {
      const data = await api.getIssueGeography(500);
      issuePoints = data.points;
      loaded = true;
    } catch (e) {
      console.error('Failed to load issue map:', e);
    } finally {
      loading = false;
    }
  }

  // Render map when container becomes available
  $effect(() => {
    if (mapContainer && issuePoints.length > 0) {
      requestAnimationFrame(() => renderMap());
    }
  });

  // Auto-load when prop is set (untrack prevents circular dependency)
  $effect(() => {
    if (autoload) untrack(() => load());
  });
</script>

{#if loading}
  <div class="viz-loading">Loading issue locations...</div>
{:else if issuePoints.length === 0 && loaded}
  <div class="empty-section">No issue location data available</div>
{:else if issuePoints.length > 0}
  {@const counts = categoryCounts()}
  {@const trend = issueTrend()}
  <div class="map-time-bar">
    {#each MAP_DAYS_OPTIONS as opt}
      <button
        class="time-chip"
        class:active={mapDaysFilter === opt.value}
        onclick={() => setDaysFilter(opt.value)}
      >{opt.label}</button>
    {/each}
    {#if trend}
      <span class="trend-stat" class:trend-up={trend.direction === 'up'} class:trend-down={trend.direction === 'down'}>
        {trend.direction === 'up' ? '↑' : trend.direction === 'down' ? '↓' : '—'} {trend.pct}% past 30d
      </span>
    {/if}
  </div>
  <div class="map-filters">
    {#each Object.entries(ISSUE_COLORS) as [label, color]}
      <button
        class="filter-chip"
        class:inactive={!activeIssueFilters.has(label)}
        onclick={() => toggleIssueFilter(label)}
      >
        <span class="legend-dot" style="background:{activeIssueFilters.has(label) ? color : '#4b5563'}"></span>
        {label}
        <span class="chip-count">{counts.get(label) || 0}</span>
      </button>
    {/each}
  </div>
  <div class="map-container" class:map-expanded={mapExpanded}>
    <div class="map-wrapper" bind:this={mapContainer}></div>
    <button class="map-expand-btn" onclick={toggleMapExpanded} title={mapExpanded ? 'Collapse map' : 'Expand map'}>
      {mapExpanded ? '↙' : '↗'}
    </button>
  </div>
  <div class="viz-stat">{filteredIssueCount()} of {timeFilteredPoints().length} issues shown</div>
{/if}

<style>
  .viz-loading {
    font-size: 11px;
    color: #6b7280;
    padding: 12px 0;
    text-align: center;
  }
  .viz-stat {
    font-size: 10px;
    color: #4b5563;
    text-align: center;
    margin-top: 4px;
  }
  .empty-section {
    font-size: 11px;
    color: #6b7280;
    padding: 8px 0;
  }
  .legend-dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .map-time-bar {
    display: flex;
    align-items: center;
    gap: 4px;
    margin-bottom: 6px;
  }
  .time-chip {
    padding: 2px 10px;
    border-radius: 10px;
    border: 1px solid #374151;
    background: transparent;
    color: #9ca3af;
    font-size: 10px;
    cursor: pointer;
    transition: all 0.15s;
  }
  .time-chip:hover { border-color: #6b7280; }
  .time-chip.active {
    background: #374151;
    color: #f3f4f6;
    border-color: #6b7280;
  }
  .trend-stat {
    margin-left: auto;
    font-size: 10px;
    color: #9ca3af;
  }
  .trend-stat.trend-up { color: #f87171; }
  .trend-stat.trend-down { color: #4ade80; }
  .map-filters {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-bottom: 8px;
  }
  .filter-chip {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 2px 8px;
    border-radius: 12px;
    border: 1px solid #374151;
    background: #1f2937;
    color: #d1d5db;
    font-size: 10px;
    cursor: pointer;
    transition: opacity 0.15s, border-color 0.15s;
  }
  .filter-chip:hover { border-color: #6b7280; }
  .filter-chip.inactive {
    opacity: 0.4;
    border-color: #1f2937;
  }
  .chip-count {
    color: #6b7280;
    font-variant-numeric: tabular-nums;
  }
  .map-container {
    position: relative;
  }
  .map-wrapper {
    height: 220px;
    border-radius: 6px;
    overflow: hidden;
    border: 1px solid #374151;
    transition: height 0.2s ease;
  }
  .map-expanded .map-wrapper {
    height: 70vh;
  }
  .map-expand-btn {
    position: absolute;
    top: 6px;
    left: 6px;
    width: 26px;
    height: 26px;
    border-radius: 4px;
    border: none;
    background: rgba(31, 41, 55, 0.85);
    color: #d1d5db;
    font-size: 14px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }
  .map-expand-btn:hover {
    background: rgba(55, 65, 81, 0.9);
  }
</style>
