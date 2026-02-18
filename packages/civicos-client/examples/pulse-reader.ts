/**
 * Second Surface Proof — CivicOS Client SDK
 *
 * Demonstrates that @civicos/client works outside the Chrome extension.
 * Run: npx tsx examples/pulse-reader.ts
 */

import {
  RegistryClient,
  ApiClient,
  CivicSession,
  MemoryStorageAdapter,
} from '../src/index.js';

async function main() {
  console.log('=== CivicOS Client SDK — Second Surface Proof ===\n');

  // 1. Create storage + clients (no Chrome APIs needed)
  const storage = new MemoryStorageAdapter();
  const registry = new RegistryClient(storage);
  const api = new ApiClient(registry);
  const session = new CivicSession(api, registry);

  console.log(`Jurisdiction: ${await registry.getActiveJurisdiction()}`);
  console.log(`MCP endpoint: ${await registry.getMcpUrl()}`);
  console.log(`Relay endpoint: ${await registry.getRelayUrl()}\n`);

  // 2. Load pulse data (the core read operation)
  console.log('Loading city pulse...');
  const pulse = await session.loadPulse();

  console.log(`\n--- City Pulse: ${pulse.jurisdiction} ---`);
  console.log(`Meetings: ${pulse.decisions_this_week?.length ?? 0} upcoming`);
  console.log(`Agenda items: ${pulse.upcoming_items?.length ?? 0} upcoming`);
  console.log(`Recent outcomes: ${pulse.recent_outcomes?.length ?? 0}`);

  if (pulse.decisions_this_week?.length) {
    const next = pulse.decisions_this_week[0];
    console.log(`\nNext meeting: ${next.title}`);
    console.log(`  Date: ${next.date}`);
  }

  if (pulse.upcoming_items?.length) {
    console.log(`\nUpcoming agenda items:`);
    for (const item of pulse.upcoming_items.slice(0, 3)) {
      const flags = [
        item.stance_eligible ? 'stance' : null,
        item.comment_eligible ? 'comment' : null,
      ].filter(Boolean).join(', ');
      console.log(`  - ${item.title}${flags ? ` [${flags}]` : ''}`);
    }
    if (pulse.upcoming_items.length > 3) {
      console.log(`  ... and ${pulse.upcoming_items.length - 3} more`);
    }
  }

  // 3. Load voice counts for stance-eligible items
  const voiceIds = CivicSession.extractVoiceEntityIds(pulse);
  if (voiceIds.length > 0) {
    console.log(`\nLoading voice counts for ${voiceIds.length} entities...`);
    const voiceCounts = await session.loadVoiceCounts(pulse);
    for (const [entityId, counts] of voiceCounts) {
      if (counts.support || counts.oppose || counts.watching) {
        console.log(`  ${entityId}: +${counts.support} -${counts.oppose} ~${counts.watching}`);
      }
    }
  }

  // 4. Load data provenance
  console.log('\nLoading data provenance...');
  const provenance = await session.loadProvenance();
  if (provenance.corpora) {
    console.log('Data sources:');
    for (const corpus of provenance.corpora) {
      const coverage = corpus.coverage_percent != null ? `${corpus.coverage_percent}%` : 'n/a';
      console.log(`  ${corpus.display_name}: ${corpus.storage_count} stored, ${corpus.vector_count} indexed (${coverage})`);
    }
  }

  console.log('\n=== Second surface proof complete ===');
  console.log('SDK works outside Chrome extension: YES');
}

main().catch(console.error);
