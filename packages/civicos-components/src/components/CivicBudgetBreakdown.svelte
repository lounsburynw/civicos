<script lang="ts">
  import { untrack } from 'svelte';
  import { Chart, DoughnutController, ArcElement, Tooltip, Legend } from 'chart.js';

  Chart.register(DoughnutController, ArcElement, Tooltip, Legend);

  // Local type (mirrors @civicos/client BudgetCategory)
  interface BudgetCategory {
    category: string;
    budgeted_dollars: number;
    percentage: number;
    item_count: number;
  }

  interface ApiClient {
    getBudgetSummary(groupBy?: string): Promise<{
      categories: BudgetCategory[];
      total_budgeted_dollars: number;
      fiscal_year: string;
    }>;
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
  let categories: BudgetCategory[] = $state([]);
  let total = $state(0);
  let fiscalYear = $state('');
  let loading = $state(false);
  let loaded = $state(false);
  let chartCanvas: HTMLCanvasElement | undefined = $state(undefined);
  let budgetChart: Chart | null = null;

  // === Constants ===
  const BUDGET_COLORS = [
    '#3b82f6', '#ec4899', '#14b8a6', '#f59e0b', '#ef4444',
    '#8b5cf6', '#22c55e', '#3b82f6', '#f97316', '#6b7280',
    '#a855f7', '#06b6d4', '#84cc16', '#e11d48',
  ];

  // === Helpers ===
  function formatDollars(amount: number): string {
    if (amount >= 1_000_000) return `$${(amount / 1_000_000).toFixed(1)}M`;
    if (amount >= 1_000) return `$${(amount / 1_000).toFixed(0)}K`;
    return `$${amount.toFixed(0)}`;
  }

  function renderBudgetChart() {
    if (!chartCanvas || categories.length === 0) return;
    if (budgetChart) { budgetChart.destroy(); budgetChart = null; }

    budgetChart = new Chart(chartCanvas, {
      type: 'doughnut',
      data: {
        labels: categories.map(c => c.category),
        datasets: [{
          data: categories.map(c => c.budgeted_dollars),
          backgroundColor: categories.map((_, i) => BUDGET_COLORS[i % BUDGET_COLORS.length]),
          borderWidth: 0,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const val = ctx.raw as number;
                return ` $${(val / 1_000_000).toFixed(1)}M (${categories[ctx.dataIndex].percentage}%)`;
              },
            },
          },
        },
      },
    });
  }

  // === Data Loading ===
  export async function load() {
    if (loaded || loading) return;
    loading = true;
    try {
      const data = await api.getBudgetSummary('department');
      categories = data.categories;
      total = data.total_budgeted_dollars;
      fiscalYear = data.fiscal_year;
      loaded = true;
    } catch (e) {
      console.error('Failed to load budget:', e);
    } finally {
      loading = false;
    }
  }

  // Render chart when canvas becomes available
  $effect(() => {
    if (chartCanvas && categories.length > 0) {
      requestAnimationFrame(() => renderBudgetChart());
    }
  });

  // Auto-load when prop is set (untrack prevents circular dependency)
  $effect(() => {
    if (autoload) untrack(() => load());
  });
</script>

{#if loading}
  <div class="viz-loading">Loading budget data...</div>
{:else if categories.length === 0 && loaded}
  <div class="empty-section">No budget data available</div>
{:else if categories.length > 0}
  <div class="budget-header">
    <span class="budget-total">{formatDollars(total)}</span>
    <span class="budget-year">{fiscalYear}</span>
  </div>
  <div class="chart-wrapper">
    <canvas bind:this={chartCanvas} width="200" height="200"></canvas>
  </div>
  <div class="budget-legend">
    {#each categories.slice(0, 8) as cat, i}
      <div class="budget-legend-item">
        <span class="legend-dot" style="background:{BUDGET_COLORS[i % BUDGET_COLORS.length]}"></span>
        <span class="budget-cat-name">{cat.category}</span>
        <span class="budget-cat-amount">{formatDollars(cat.budgeted_dollars)} ({cat.percentage}%)</span>
      </div>
    {/each}
    {#if categories.length > 8}
      <div class="budget-legend-more">+{categories.length - 8} more departments</div>
    {/if}
  </div>
{/if}

<style>
  .viz-loading {
    font-size: 11px;
    color: #6b7280;
    padding: 12px 0;
    text-align: center;
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
  .budget-header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 8px;
  }
  .budget-total {
    font-size: 18px;
    font-weight: 700;
    color: #eee;
  }
  .budget-year {
    font-size: 11px;
    color: #6b7280;
  }
  .chart-wrapper {
    display: flex;
    justify-content: center;
    padding: 4px 0;
  }
  .chart-wrapper canvas {
    max-width: 200px;
    max-height: 200px;
  }
  .budget-legend {
    margin-top: 8px;
  }
  .budget-legend-item {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 11px;
    padding: 3px 0;
  }
  .budget-cat-name {
    flex: 1;
    color: #d1d5db;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .budget-cat-amount {
    color: #6b7280;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }
  .budget-legend-more {
    font-size: 10px;
    color: #4b5563;
    margin-top: 4px;
  }
</style>
