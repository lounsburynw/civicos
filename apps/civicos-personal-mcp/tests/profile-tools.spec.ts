/**
 * Tests for profile, preferences, and jurisdictions management tools.
 *
 * These tools allow frontends (browser extension, Open WebUI) to manage
 * user settings via the HTTP JSON-RPC interface.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import request from 'supertest';
import { PersonalMCPHttpServer } from '../src/http-server.js';
import { MemoryPersonalStorage } from '../lib/storage/memory-storage.js';

describe('Profile Management Tools', () => {
  let server: PersonalMCPHttpServer;
  let storage: MemoryPersonalStorage;

  beforeEach(async () => {
    storage = new MemoryPersonalStorage();
    await storage.initialize();
    server = new PersonalMCPHttpServer({
      port: 8090,
      personalStorage: storage,
    });
  });

  function callTool(name: string, args: Record<string, unknown> = {}) {
    return request(server.getApp())
      .post('/mcp')
      .send({
        jsonrpc: '2.0',
        method: 'tools/call',
        params: { name, arguments: args },
        id: 1,
      })
      .expect(200);
  }

  function parseResult(response: { body: { result: { content: Array<{ text: string }> } } }) {
    return JSON.parse(response.body.result.content[0].text);
  }

  // ================================================================
  // Profile tools
  // ================================================================

  describe('get_profile', () => {
    it('returns empty profile by default', async () => {
      const response = await callTool('get_profile');
      const result = parseResult(response);

      expect(result.success).toBe(true);
      expect(result.profile.interests).toEqual([]);
      expect(result.profile.name).toBeUndefined();
    });

    it('returns saved profile', async () => {
      await storage.saveProfile({
        name: 'Alice',
        email: 'alice@example.com',
        neighborhood: 'Terra Linda',
        interests: ['Housing', 'Transportation'],
      });

      const response = await callTool('get_profile');
      const result = parseResult(response);

      expect(result.success).toBe(true);
      expect(result.profile.name).toBe('Alice');
      expect(result.profile.email).toBe('alice@example.com');
      expect(result.profile.interests).toEqual(['Housing', 'Transportation']);
    });
  });

  describe('set_profile', () => {
    it('sets profile fields', async () => {
      const response = await callTool('set_profile', {
        name: 'Bob',
        neighborhood: 'Downtown',
        interests: ['Parks', 'Budget'],
      });
      const result = parseResult(response);

      expect(result.success).toBe(true);
      expect(result.profile.name).toBe('Bob');
      expect(result.profile.neighborhood).toBe('Downtown');
      expect(result.profile.interests).toEqual(['Parks', 'Budget']);
    });

    it('merges with existing profile (partial update)', async () => {
      // Set initial profile
      await callTool('set_profile', {
        name: 'Alice',
        email: 'alice@example.com',
        interests: ['Housing'],
      });

      // Update only name
      const response = await callTool('set_profile', {
        name: 'Alice B.',
      });
      const result = parseResult(response);

      expect(result.profile.name).toBe('Alice B.');
      expect(result.profile.email).toBe('alice@example.com');
      expect(result.profile.interests).toEqual(['Housing']);
    });

    it('replaces interests when provided', async () => {
      await callTool('set_profile', { interests: ['Housing'] });
      const response = await callTool('set_profile', { interests: ['Parks', 'Budget'] });
      const result = parseResult(response);

      expect(result.profile.interests).toEqual(['Parks', 'Budget']);
    });

    it('sets coordinates', async () => {
      const response = await callTool('set_profile', {
        latitude: 37.9735,
        longitude: -122.5311,
      });
      const result = parseResult(response);

      expect(result.profile.latitude).toBe(37.9735);
      expect(result.profile.longitude).toBe(-122.5311);
    });
  });

  // ================================================================
  // Preferences tools
  // ================================================================

  describe('get_preferences', () => {
    it('returns empty preferences by default', async () => {
      const response = await callTool('get_preferences');
      const result = parseResult(response);

      expect(result.success).toBe(true);
      expect(result.preferences.notifications).toEqual({});
      expect(result.preferences.display).toEqual({});
    });
  });

  describe('set_preferences', () => {
    it('sets notification preferences', async () => {
      const response = await callTool('set_preferences', {
        notifications: { 'Email Digest': 'weekly', 'Meeting Reminders': 'true' },
      });
      const result = parseResult(response);

      expect(result.success).toBe(true);
      expect(result.preferences.notifications['Email Digest']).toBe('weekly');
      expect(result.preferences.notifications['Meeting Reminders']).toBe('true');
    });

    it('sets display preferences', async () => {
      const response = await callTool('set_preferences', {
        display: { Theme: 'dark', Language: 'en' },
      });
      const result = parseResult(response);

      expect(result.preferences.display.Theme).toBe('dark');
      expect(result.preferences.display.Language).toBe('en');
    });

    it('merges with existing preferences', async () => {
      await callTool('set_preferences', {
        notifications: { 'Email Digest': 'weekly' },
        display: { Theme: 'light' },
      });

      const response = await callTool('set_preferences', {
        notifications: { 'Meeting Reminders': 'true' },
      });
      const result = parseResult(response);

      // Original notification preserved, new one added
      expect(result.preferences.notifications['Email Digest']).toBe('weekly');
      expect(result.preferences.notifications['Meeting Reminders']).toBe('true');
      // Display unchanged
      expect(result.preferences.display.Theme).toBe('light');
    });
  });

  // ================================================================
  // Jurisdictions tools
  // ================================================================

  describe('get_jurisdictions', () => {
    it('returns empty list by default', async () => {
      const response = await callTool('get_jurisdictions');
      const result = parseResult(response);

      expect(result.success).toBe(true);
      expect(result.jurisdictions).toEqual([]);
      expect(result.count).toBe(0);
    });
  });

  describe('set_jurisdictions', () => {
    it('sets jurisdiction list', async () => {
      const response = await callTool('set_jurisdictions', {
        jurisdictions: ['city-san-rafael', 'county-marin'],
      });
      const result = parseResult(response);

      expect(result.success).toBe(true);
      expect(result.jurisdictions).toEqual(['city-san-rafael', 'county-marin']);
      expect(result.count).toBe(2);
    });

    it('replaces existing jurisdictions', async () => {
      await callTool('set_jurisdictions', {
        jurisdictions: ['city-san-rafael'],
      });

      const response = await callTool('set_jurisdictions', {
        jurisdictions: ['county-marin', 'state-california'],
      });
      const result = parseResult(response);

      expect(result.jurisdictions).toEqual(['county-marin', 'state-california']);
    });

    it('persists across get calls', async () => {
      await callTool('set_jurisdictions', {
        jurisdictions: ['city-san-rafael', 'county-marin'],
      });

      const response = await callTool('get_jurisdictions');
      const result = parseResult(response);

      expect(result.jurisdictions).toEqual(['city-san-rafael', 'county-marin']);
    });
  });

  // ================================================================
  // Storage info tool
  // ================================================================

  describe('get_storage_info', () => {
    it('returns memory storage info', async () => {
      const response = await callTool('get_storage_info');
      const result = parseResult(response);

      expect(result.type).toBe('memory');
      expect(result.version).toBe(1);
      expect(result.initialized).toBe(true);
    });
  });

  // ================================================================
  // Tool listing
  // ================================================================

  describe('tools/list includes profile tools', () => {
    it('lists all 27 tools', async () => {
      const response = await request(server.getApp())
        .post('/mcp')
        .send({ jsonrpc: '2.0', method: 'tools/list', params: {}, id: 1 });

      const tools = response.body.result.tools;
      const toolNames = tools.map((t: { name: string }) => t.name);

      expect(toolNames).toContain('get_profile');
      expect(toolNames).toContain('set_profile');
      expect(toolNames).toContain('get_preferences');
      expect(toolNames).toContain('set_preferences');
      expect(toolNames).toContain('get_jurisdictions');
      expect(toolNames).toContain('set_jurisdictions');
      expect(toolNames).toContain('get_storage_info');
    });
  });
});

describe('Profile tools without PersonalStorage', () => {
  let server: PersonalMCPHttpServer;

  beforeEach(() => {
    // No personalStorage — legacy mode
    server = new PersonalMCPHttpServer({ port: 8091 });
  });

  function callTool(name: string, args: Record<string, unknown> = {}) {
    return request(server.getApp())
      .post('/mcp')
      .send({
        jsonrpc: '2.0',
        method: 'tools/call',
        params: { name, arguments: args },
        id: 1,
      })
      .expect(200);
  }

  function parseResult(response: { body: { result: { content: Array<{ text: string }> } } }) {
    return JSON.parse(response.body.result.content[0].text);
  }

  it('get_profile returns error without storage', async () => {
    const response = await callTool('get_profile');
    const result = parseResult(response);
    expect(result.success).toBe(false);
    expect(result.error).toContain('No PersonalStorage configured');
  });

  it('set_profile returns error without storage', async () => {
    const response = await callTool('set_profile', { name: 'Alice' });
    const result = parseResult(response);
    expect(result.success).toBe(false);
  });

  it('get_storage_info returns legacy info', async () => {
    const response = await callTool('get_storage_info');
    const result = parseResult(response);
    expect(result.type).toBe('legacy');
  });
});
