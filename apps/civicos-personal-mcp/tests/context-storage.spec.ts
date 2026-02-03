/**
 * Context Storage Tests
 *
 * Tests for user context personalization storage.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import request from 'supertest';
import { PersonalMCPHttpServer } from '../src/http-server.js';
import {
  MemoryContextStorage,
  createDefaultContext,
  type StoredUserContext,
} from '../lib/providers/context-storage.js';

describe('MemoryContextStorage', () => {
  let storage: MemoryContextStorage;

  beforeEach(() => {
    storage = new MemoryContextStorage();
  });

  it('starts empty', async () => {
    const result = await storage.load('city-san-rafael');
    expect(result).toBeNull();
  });

  it('saves and loads context', async () => {
    const context = createDefaultContext('city-san-rafael');
    context.interests = ['housing', 'transportation'];
    context.neighborhood = { neighborhood: 'Terra Linda' };

    await storage.save('city-san-rafael', context);

    const loaded = await storage.load('city-san-rafael');
    expect(loaded).not.toBeNull();
    expect(loaded?.interests).toEqual(['housing', 'transportation']);
    expect(loaded?.neighborhood?.neighborhood).toBe('Terra Linda');
  });

  it('deletes context', async () => {
    const context = createDefaultContext('city-san-rafael');
    await storage.save('city-san-rafael', context);

    await storage.delete('city-san-rafael');

    const loaded = await storage.load('city-san-rafael');
    expect(loaded).toBeNull();
  });

  it('lists jurisdictions', async () => {
    await storage.save('city-san-rafael', createDefaultContext('city-san-rafael'));
    await storage.save('city-los-angeles', createDefaultContext('city-los-angeles'));

    const jurisdictions = await storage.list();
    expect(jurisdictions).toContain('city-san-rafael');
    expect(jurisdictions).toContain('city-los-angeles');
    expect(jurisdictions).toHaveLength(2);
  });

  it('isolates contexts by jurisdiction', async () => {
    const srContext = createDefaultContext('city-san-rafael');
    srContext.interests = ['housing'];

    const laContext = createDefaultContext('city-los-angeles');
    laContext.interests = ['traffic'];

    await storage.save('city-san-rafael', srContext);
    await storage.save('city-los-angeles', laContext);

    const sr = await storage.load('city-san-rafael');
    const la = await storage.load('city-los-angeles');

    expect(sr?.interests).toEqual(['housing']);
    expect(la?.interests).toEqual(['traffic']);
  });
});

describe('createDefaultContext', () => {
  it('creates valid default context', () => {
    const context = createDefaultContext('city-san-rafael');

    expect(context.version).toBe(1);
    expect(context.jurisdiction).toBe('city-san-rafael');
    expect(context.interests).toEqual([]);
    expect(context.following_items).toEqual([]);
    expect(context.created_at).toBeGreaterThan(0);
    expect(context.updated_at).toBeGreaterThan(0);
    expect(context.neighborhood).toBeUndefined();
  });
});

describe('Context Personalization Tools', () => {
  let server: PersonalMCPHttpServer;
  let contextStorage: MemoryContextStorage;

  beforeEach(() => {
    contextStorage = new MemoryContextStorage();
    server = new PersonalMCPHttpServer({
      port: 8084,
      contextStorage,
    });
  });

  async function callTool(name: string, args: Record<string, unknown>) {
    const response = await request(server.getApp())
      .post('/mcp')
      .send({
        jsonrpc: '2.0',
        method: 'tools/call',
        params: { name, arguments: args },
        id: 1,
      });
    return JSON.parse(response.body.result.content[0].text);
  }

  describe('set_neighborhood', () => {
    it('sets neighborhood without coordinates', async () => {
      const result = await callTool('set_neighborhood', {
        jurisdiction: 'city-san-rafael',
        neighborhood: 'Terra Linda',
      });

      expect(result.success).toBe(true);
      expect(result.neighborhood.neighborhood).toBe('Terra Linda');
      expect(result.neighborhood.lat).toBeUndefined();
      expect(result.neighborhood.lng).toBeUndefined();
    });

    it('sets neighborhood with coordinates', async () => {
      const result = await callTool('set_neighborhood', {
        jurisdiction: 'city-san-rafael',
        neighborhood: 'Downtown',
        lat: 37.9735,
        lng: -122.5311,
      });

      expect(result.success).toBe(true);
      expect(result.neighborhood.neighborhood).toBe('Downtown');
      expect(result.neighborhood.lat).toBe(37.9735);
      expect(result.neighborhood.lng).toBe(-122.5311);
    });

    it('updates existing neighborhood', async () => {
      await callTool('set_neighborhood', {
        jurisdiction: 'city-san-rafael',
        neighborhood: 'Terra Linda',
      });

      const result = await callTool('set_neighborhood', {
        jurisdiction: 'city-san-rafael',
        neighborhood: 'Downtown',
      });

      expect(result.success).toBe(true);
      expect(result.neighborhood.neighborhood).toBe('Downtown');

      // Verify stored
      const context = await contextStorage.load('city-san-rafael');
      expect(context?.neighborhood?.neighborhood).toBe('Downtown');
    });
  });

  describe('set_interests', () => {
    it('sets interests', async () => {
      const result = await callTool('set_interests', {
        jurisdiction: 'city-san-rafael',
        interests: ['housing', 'transportation', 'parks'],
      });

      expect(result.success).toBe(true);
      expect(result.interests).toEqual(['housing', 'transportation', 'parks']);
    });

    it('normalizes interests (lowercase, dedupe)', async () => {
      const result = await callTool('set_interests', {
        jurisdiction: 'city-san-rafael',
        interests: ['Housing', 'HOUSING', '  transportation  ', 'parks'],
      });

      expect(result.success).toBe(true);
      expect(result.interests).toEqual(['housing', 'transportation', 'parks']);
    });

    it('replaces existing interests', async () => {
      await callTool('set_interests', {
        jurisdiction: 'city-san-rafael',
        interests: ['housing'],
      });

      const result = await callTool('set_interests', {
        jurisdiction: 'city-san-rafael',
        interests: ['traffic', 'budget'],
      });

      expect(result.interests).toEqual(['traffic', 'budget']);
    });
  });

  describe('follow_item', () => {
    it('follows a decision', async () => {
      const result = await callTool('follow_item', {
        jurisdiction: 'city-san-rafael',
        entity_type: 'decision',
        entity_id: 'decision:2026-01-15:item-6a',
        label: 'Housing Element Update',
      });

      expect(result.success).toBe(true);
      expect(result.item.entity_type).toBe('decision');
      expect(result.item.entity_id).toBe('decision:2026-01-15:item-6a');
      expect(result.item.label).toBe('Housing Element Update');
      expect(result.total_following).toBe(1);
    });

    it('follows multiple items', async () => {
      await callTool('follow_item', {
        jurisdiction: 'city-san-rafael',
        entity_type: 'decision',
        entity_id: 'decision:2026-01-15:item-6a',
      });

      await callTool('follow_item', {
        jurisdiction: 'city-san-rafael',
        entity_type: 'meeting',
        entity_id: 'meeting:2026-02-01',
      });

      const result = await callTool('follow_item', {
        jurisdiction: 'city-san-rafael',
        entity_type: 'topic',
        entity_id: 'topic:housing',
      });

      expect(result.total_following).toBe(3);
    });

    it('updates label when re-following same item', async () => {
      await callTool('follow_item', {
        jurisdiction: 'city-san-rafael',
        entity_type: 'decision',
        entity_id: 'decision:2026-01-15:item-6a',
        label: 'Old Label',
      });

      const result = await callTool('follow_item', {
        jurisdiction: 'city-san-rafael',
        entity_type: 'decision',
        entity_id: 'decision:2026-01-15:item-6a',
        label: 'New Label',
      });

      expect(result.total_following).toBe(1); // Still 1, not duplicated
      expect(result.item.label).toBe('New Label');
    });
  });

  describe('unfollow_item', () => {
    it('unfollows an item', async () => {
      await callTool('follow_item', {
        jurisdiction: 'city-san-rafael',
        entity_type: 'decision',
        entity_id: 'decision:2026-01-15:item-6a',
      });

      const result = await callTool('unfollow_item', {
        jurisdiction: 'city-san-rafael',
        entity_id: 'decision:2026-01-15:item-6a',
      });

      expect(result.success).toBe(true);
      expect(result.total_following).toBe(0);
    });

    it('returns error for non-existent item', async () => {
      const result = await callTool('unfollow_item', {
        jurisdiction: 'city-san-rafael',
        entity_id: 'nonexistent',
      });

      expect(result.success).toBe(false);
      expect(result.error).toContain('No context found');
    });

    it('returns error for wrong item id', async () => {
      await callTool('follow_item', {
        jurisdiction: 'city-san-rafael',
        entity_type: 'decision',
        entity_id: 'decision:2026-01-15:item-6a',
      });

      const result = await callTool('unfollow_item', {
        jurisdiction: 'city-san-rafael',
        entity_id: 'wrong-id',
      });

      expect(result.success).toBe(false);
      expect(result.error).toContain('Item not found');
    });
  });

  describe('get_context', () => {
    it('returns empty state when no context saved', async () => {
      const result = await callTool('get_context', {
        jurisdiction: 'city-san-rafael',
      });

      expect(result.hasContext).toBe(false);
      expect(result.jurisdiction).toBe('city-san-rafael');
    });

    it('returns full context after personalization', async () => {
      await callTool('set_neighborhood', {
        jurisdiction: 'city-san-rafael',
        neighborhood: 'Downtown',
        lat: 37.9735,
        lng: -122.5311,
      });

      await callTool('set_interests', {
        jurisdiction: 'city-san-rafael',
        interests: ['housing', 'transportation'],
      });

      await callTool('follow_item', {
        jurisdiction: 'city-san-rafael',
        entity_type: 'decision',
        entity_id: 'decision:2026-01-15:item-6a',
        label: 'Housing Element',
      });

      const result = await callTool('get_context', {
        jurisdiction: 'city-san-rafael',
      });

      expect(result.hasContext).toBe(true);
      expect(result.neighborhood.neighborhood).toBe('Downtown');
      expect(result.interests).toEqual(['housing', 'transportation']);
      expect(result.following_items).toHaveLength(1);
      expect(result.following_items[0].entity_id).toBe('decision:2026-01-15:item-6a');
      expect(result.created_at).toBeDefined();
      expect(result.updated_at).toBeDefined();
    });
  });

  describe('tools/list includes context tools', () => {
    it('lists 17 tools (9 identity + 5 context + 3 personalized query)', async () => {
      const response = await request(server.getApp())
        .post('/mcp')
        .send({ jsonrpc: '2.0', method: 'tools/list', params: {}, id: 1 });

      const tools = response.body.result.tools;
      expect(tools).toHaveLength(17);

      const toolNames = tools.map((t: { name: string }) => t.name);
      expect(toolNames).toContain('set_neighborhood');
      expect(toolNames).toContain('set_interests');
      expect(toolNames).toContain('follow_item');
      expect(toolNames).toContain('unfollow_item');
      expect(toolNames).toContain('get_context');
    });
  });

  describe('health check shows updated tool count', () => {
    it('reports 17 tools', async () => {
      const response = await request(server.getApp()).get('/health');
      expect(response.body.tools).toBe(17);
    });
  });
});
