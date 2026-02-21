/**
 * Personalized Query Tools Tests
 *
 * Tests for tools that query Jurisdiction MCP and apply user context.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import request from 'supertest';
import { PersonalMCPHttpServer } from '../src/http-server.js';
import { MemoryContextStorage } from '../lib/providers/context-storage.js';
import { MockJurisdictionMCPClient } from '../lib/jurisdiction-mcp-client.js';

describe('Personalized Query Tools', () => {
  let server: PersonalMCPHttpServer;
  let contextStorage: MemoryContextStorage;
  let mockClient: MockJurisdictionMCPClient;

  beforeEach(() => {
    contextStorage = new MemoryContextStorage();
    mockClient = new MockJurisdictionMCPClient();
    server = new PersonalMCPHttpServer({
      port: 8085,
      contextStorage,
      jurisdictionMCPClient: mockClient,
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

  describe('get_relevant_now', () => {
    it('returns all items when no context is set', async () => {
      const result = await callTool('get_relevant_now', {
        jurisdiction: 'city-san-rafael',
      });

      expect(result.success).toBe(true);
      expect(result.personalized).toBe(false);
      expect(result.message).toContain('Set interests and neighborhood');
      expect(result.upcoming_meetings).toBeDefined();
      expect(result.recent_decisions).toBeDefined();
      expect(result.trending_issues).toBeDefined();
    });

    it('filters results based on interests', async () => {
      // Set up context with interests
      await callTool('set_interests', {
        jurisdiction: 'city-san-rafael',
        interests: ['housing', 'transportation'],
      });

      // Set up mock with varied data
      mockClient.setMockResponse('city_pulse', {
        upcoming_meetings: [
          {
            title: 'City Council Meeting',
            date: '2026-02-10',
            agenda_items: ['Housing Element Update', 'Budget Review'],
          },
          {
            title: 'Parks Commission',
            date: '2026-02-12',
            agenda_items: ['Tree Planting', 'Playground Renovation'],
          },
        ],
        recent_decisions: [
          {
            title: 'Approve bike lane',
            date: '2026-01-28',
            topics: ['transportation', 'traffic safety'],
          },
          {
            title: 'Library hours extension',
            date: '2026-01-27',
            topics: ['library', 'services'],
          },
        ],
        trending_issues: [
          { type: 'pothole', count: 10, location: 'Downtown' },
          { type: 'housing complaint', count: 5, location: 'Terra Linda' },
        ],
      });

      const result = await callTool('get_relevant_now', {
        jurisdiction: 'city-san-rafael',
      });

      expect(result.success).toBe(true);
      expect(result.personalized).toBe(true);
      expect(result.context_used.interests).toContain('housing');
      expect(result.context_used.interests).toContain('transportation');

      // Should include housing meeting but filter parks meeting
      expect(result.upcoming_meetings.length).toBeGreaterThanOrEqual(1);
      expect(result.upcoming_meetings.some((m: {title: string}) => m.agenda_items?.includes('Housing Element Update'))).toBe(true);

      // Should include transportation decision
      expect(result.recent_decisions.some((d: {title: string}) => d.title.includes('bike lane'))).toBe(true);

      // Should include housing-related issues
      expect(result.trending_issues.some((i: {type: string}) => i.type.includes('housing'))).toBe(true);
    });

    it('filters by neighborhood location', async () => {
      await callTool('set_neighborhood', {
        jurisdiction: 'city-san-rafael',
        neighborhood: 'Downtown',
      });

      mockClient.setMockResponse('city_pulse', {
        upcoming_meetings: [],
        recent_decisions: [],
        trending_issues: [
          { type: 'pothole', count: 10, location: 'Downtown' },
          { type: 'graffiti', count: 3, location: 'Terra Linda' },
        ],
      });

      const result = await callTool('get_relevant_now', {
        jurisdiction: 'city-san-rafael',
      });

      expect(result.success).toBe(true);
      expect(result.context_used.neighborhood).toBe('Downtown');
      expect(result.trending_issues.length).toBe(1);
      expect(result.trending_issues[0].location).toBe('Downtown');
    });
  });

  describe('get_suggestions', () => {
    it('prompts for setup when no context', async () => {
      const result = await callTool('get_suggestions', {
        jurisdiction: 'city-san-rafael',
      });

      expect(result.success).toBe(true);
      expect(result.setup_needed).toBe(true);
      expect(result.message).toContain('Set interests or follow items');
      expect(result.suggestions).toEqual([]);
    });

    it('generates suggestions based on interests', async () => {
      await callTool('set_interests', {
        jurisdiction: 'city-san-rafael',
        interests: ['housing'],
      });

      const result = await callTool('get_suggestions', {
        jurisdiction: 'city-san-rafael',
      });

      expect(result.success).toBe(true);
      expect(result.suggestions.length).toBeGreaterThan(0);
      expect(result.context_used.interests).toContain('housing');

      // Should have suggestions related to housing
      const housingRelated = result.suggestions.filter((s: {reason: string}) =>
        s.reason.toLowerCase().includes('housing')
      );
      expect(housingRelated.length).toBeGreaterThan(0);
    });

    it('generates follow-up suggestions for followed items', async () => {
      await callTool('follow_item', {
        jurisdiction: 'city-san-rafael',
        entity_type: 'decision',
        entity_id: 'decision:2026-01-15:item-6a',
        label: 'Housing Element Update',
      });

      const result = await callTool('get_suggestions', {
        jurisdiction: 'city-san-rafael',
      });

      expect(result.success).toBe(true);
      expect(result.context_used.following_count).toBe(1);

      // Should have a follow-up suggestion
      const followUpSuggestion = result.suggestions.find((s: {type: string}) => s.type === 'follow_up');
      expect(followUpSuggestion).toBeDefined();
      expect(followUpSuggestion.title).toContain('Housing Element Update');
    });

    it('limits suggestions to 5', async () => {
      await callTool('set_interests', {
        jurisdiction: 'city-san-rafael',
        interests: ['housing', 'transportation', 'parks', 'budget', 'safety'],
      });

      // Follow multiple items
      for (let i = 0; i < 5; i++) {
        await callTool('follow_item', {
          jurisdiction: 'city-san-rafael',
          entity_type: 'topic',
          entity_id: `topic:item-${i}`,
          label: `Topic ${i}`,
        });
      }

      const result = await callTool('get_suggestions', {
        jurisdiction: 'city-san-rafael',
      });

      expect(result.success).toBe(true);
      expect(result.suggestions.length).toBeLessThanOrEqual(5);
    });
  });

  describe('explain_relevance', () => {
    it('returns zero relevance when no context', async () => {
      const result = await callTool('explain_relevance', {
        jurisdiction: 'city-san-rafael',
        item_id: 'decision:2026-01-15:item-6a',
      });

      expect(result.success).toBe(true);
      expect(result.relevance_score).toBe(0);
      expect(result.explanations).toEqual([]);
      expect(result.message).toContain('No personalization context');
    });

    it('explains relevance for followed items', async () => {
      await callTool('follow_item', {
        jurisdiction: 'city-san-rafael',
        entity_type: 'decision',
        entity_id: 'decision:2026-01-15:item-6a',
        label: 'Housing Element Update',
      });

      const result = await callTool('explain_relevance', {
        jurisdiction: 'city-san-rafael',
        item_id: 'decision:2026-01-15:item-6a',
        item_type: 'decision',
      });

      expect(result.success).toBe(true);
      expect(result.relevance_score).toBeGreaterThan(0);
      expect(result.explanations).toContain('You are following this item');
    });

    it('explains relevance based on interest matches', async () => {
      await callTool('set_interests', {
        jurisdiction: 'city-san-rafael',
        interests: ['housing', 'transportation'],
      });

      const result = await callTool('explain_relevance', {
        jurisdiction: 'city-san-rafael',
        item_id: 'decision:2026-01-15:item-6a',
        item_type: 'decision',
        item_title: 'Housing Element Update',
        item_topics: ['housing', 'planning', 'zoning'],
      });

      expect(result.success).toBe(true);
      expect(result.relevance_score).toBeGreaterThan(0);
      expect(result.explanations.some((e: string) => e.includes('interest') && e.includes('housing'))).toBe(true);
    });

    it('explains relevance based on neighborhood', async () => {
      await callTool('set_neighborhood', {
        jurisdiction: 'city-san-rafael',
        neighborhood: 'Downtown',
      });

      const result = await callTool('explain_relevance', {
        jurisdiction: 'city-san-rafael',
        item_id: 'issue:12345',
        item_type: 'issue',
        item_title: 'Pothole repair needed in Downtown area',
      });

      expect(result.success).toBe(true);
      expect(result.relevance_score).toBeGreaterThan(0);
      expect(result.explanations.some((e: string) => e.includes('neighborhood'))).toBe(true);
    });

    it('provides verdict based on score', async () => {
      // High relevance case
      await callTool('set_interests', {
        jurisdiction: 'city-san-rafael',
        interests: ['housing'],
      });
      await callTool('follow_item', {
        jurisdiction: 'city-san-rafael',
        entity_type: 'decision',
        entity_id: 'decision:housing',
        label: 'Housing Decision',
      });

      const highResult = await callTool('explain_relevance', {
        jurisdiction: 'city-san-rafael',
        item_id: 'decision:housing',
        item_topics: ['housing'],
      });

      expect(highResult.verdict).toContain('Highly relevant');

      // Low relevance case
      const lowResult = await callTool('explain_relevance', {
        jurisdiction: 'city-san-rafael',
        item_id: 'decision:unrelated',
        item_topics: ['library', 'parks'],
      });

      expect(lowResult.verdict.toLowerCase()).toContain('may not directly match');
    });
  });

  describe('tools/list includes personalized query tools', () => {
    it('lists 20 tools (9 identity + 3 prepare + 5 context + 3 personalized query)', async () => {
      const response = await request(server.getApp())
        .post('/mcp')
        .send({ jsonrpc: '2.0', method: 'tools/list', params: {}, id: 1 });

      const tools = response.body.result.tools;
      expect(tools).toHaveLength(21);

      const toolNames = tools.map((t: { name: string }) => t.name);
      expect(toolNames).toContain('get_relevant_now');
      expect(toolNames).toContain('get_suggestions');
      expect(toolNames).toContain('explain_relevance');
    });
  });

  describe('health check shows updated tool count', () => {
    it('reports 20 tools', async () => {
      const response = await request(server.getApp()).get('/health');
      expect(response.body.tools).toBe(21);
    });
  });
});
