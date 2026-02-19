<script lang="ts">
  import { formatRelativeDate } from '../utils/civic-helpers.js';

  type CorpusInfo = {
    display_name: string;
    storage_count: number;
    vector_count: number;
    coverage_percent: number | null;
  };

  type DataProvenance = {
    jurisdiction: string;
    storage_backend: string;
    total_storage_docs: number;
    total_vector_docs: number;
    corpora: CorpusInfo[];
    freshness: { last_updated: string | null };
  };

  let {
    data,
    loading = false,
  }: {
    data: DataProvenance | null;
    loading?: boolean;
  } = $props();
</script>

<div class="provenance-panel">
  {#if loading}
    <div class="prov-loading">Loading data sources...</div>
  {:else if data}
    <div class="prov-header">
      <span class="prov-title">Data Sources</span>
      <span class="prov-jurisdiction">{data.jurisdiction}</span>
    </div>
    <div class="prov-stats">
      <span>{data.total_storage_docs.toLocaleString()} records</span>
      <span class="meta-sep">&middot;</span>
      <span>{data.total_vector_docs.toLocaleString()} embeddings</span>
    </div>
    <div class="prov-corpora">
      {#each data.corpora as corpus}
        <div class="corpus-row">
          <span class="corpus-name">{corpus.display_name}</span>
          <span class="corpus-stats">
            <span class="corpus-count">{corpus.storage_count.toLocaleString()}</span>
            {#if corpus.vector_count > 0}
              {#if corpus.vector_count > corpus.storage_count}
                <span class="corpus-indexed">indexed</span>
              {:else if corpus.coverage_percent !== null && corpus.coverage_percent >= 99}
                <span class="corpus-indexed">indexed</span>
              {:else if corpus.coverage_percent !== null}
                <span class="corpus-coverage" class:low={corpus.coverage_percent < 50}>
                  {Math.round(corpus.coverage_percent)}%
                </span>
              {/if}
            {:else if corpus.coverage_percent !== null}
              <span class="corpus-coverage low">0%</span>
            {/if}
          </span>
        </div>
      {/each}
    </div>
    <div class="prov-footer-row">
      {#if data.freshness.last_updated}
        <span class="prov-freshness">
          Updated {formatRelativeDate(data.freshness.last_updated)}
        </span>
      {/if}
      <span class="prov-backend">{data.storage_backend}</span>
    </div>
  {:else}
    <div class="prov-loading">Unable to load data sources</div>
  {/if}
</div>

<style>
  .provenance-panel {
    background: #262626;
    border-radius: 8px;
    padding: 10px 12px;
    margin-bottom: 12px;
    border: 1px solid #374151;
  }
  .prov-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 6px;
  }
  .prov-title { font-size: 12px; font-weight: 600; color: #eee; }
  .prov-jurisdiction { font-size: 10px; color: #6b7280; }
  .prov-stats {
    display: flex;
    gap: 4px;
    font-size: 11px;
    color: #9ca3af;
    margin-bottom: 8px;
  }
  .meta-sep { color: #4b5563; }
  .prov-corpora {
    border-top: 1px solid #374151;
    padding-top: 6px;
  }
  .corpus-row {
    display: flex;
    justify-content: space-between;
    padding: 3px 0;
    font-size: 11px;
  }
  .corpus-name { color: #d1d5db; }
  .corpus-stats { display: flex; gap: 6px; align-items: center; }
  .corpus-count { color: #6b7280; font-variant-numeric: tabular-nums; }
  .corpus-indexed {
    font-size: 9px;
    color: #4ade80;
    text-transform: uppercase;
    letter-spacing: 0.3px;
  }
  .corpus-coverage { font-size: 10px; color: #6b7280; font-variant-numeric: tabular-nums; }
  .corpus-coverage.low { color: #f59e0b; }
  .prov-footer-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-top: 1px solid #374151;
    padding-top: 6px;
    margin-top: 6px;
  }
  .prov-freshness { font-size: 10px; color: #4b5563; }
  .prov-backend {
    font-size: 9px;
    color: #4b5563;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  .prov-loading { font-size: 11px; color: #6b7280; padding: 8px 0; }
</style>
