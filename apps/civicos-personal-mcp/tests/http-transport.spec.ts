/**
 * HTTP Transport Tests
 *
 * Tests the HTTP server transport for Personal MCP.
 */

import { describe, it, expect, beforeAll } from 'vitest';
import request from 'supertest';
import { PersonalMCPHttpServer } from '../src/http-server.js';

describe('PersonalMCPHttpServer', () => {
  let server: PersonalMCPHttpServer;

  beforeAll(() => {
    server = new PersonalMCPHttpServer({ port: 8082 });
  });

  describe('GET /health', () => {
    it('returns healthy status', async () => {
      const response = await request(server.getApp())
        .get('/health')
        .expect(200);

      expect(response.body.status).toBe('healthy');
      expect(response.body.server).toBe('civicos-personal-mcp');
      expect(response.body.transport).toBe('http');
      expect(response.body.tools).toBe(21);
    });
  });

  describe('POST /mcp - initialize', () => {
    it('returns server info', async () => {
      const response = await request(server.getApp())
        .post('/mcp')
        .send({ jsonrpc: '2.0', method: 'initialize', params: {}, id: 1 })
        .expect(200);

      expect(response.body.result.serverInfo.name).toBe('civicos-personal-mcp');
      expect(response.body.result.capabilities.tools).toBeDefined();
    });
  });

  describe('POST /mcp - tools/list', () => {
    it('returns all tools', async () => {
      const response = await request(server.getApp())
        .post('/mcp')
        .send({ jsonrpc: '2.0', method: 'tools/list', params: {}, id: 1 })
        .expect(200);

      expect(response.body.result.tools).toHaveLength(21);

      const toolNames = response.body.result.tools.map((t: { name: string }) => t.name);
      // Identity tools
      expect(toolNames).toContain('identity_status');
      expect(toolNames).toContain('identity_create');
      expect(toolNames).toContain('sign_voice');
      expect(toolNames).toContain('sign_commitment');
      expect(toolNames).toContain('sign_completion');
      // Context tools
      expect(toolNames).toContain('set_neighborhood');
      expect(toolNames).toContain('set_interests');
      expect(toolNames).toContain('follow_item');
      expect(toolNames).toContain('unfollow_item');
      expect(toolNames).toContain('get_context');
    });
  });

  describe('POST /mcp - tools/call identity_status', () => {
    it('returns no identity when none configured', async () => {
      const response = await request(server.getApp())
        .post('/mcp')
        .send({
          jsonrpc: '2.0',
          method: 'tools/call',
          params: { name: 'identity_status' },
          id: 1,
        })
        .expect(200);

      const content = JSON.parse(response.body.result.content[0].text);
      expect(content.hasIdentity).toBe(false);
    });
  });

  describe('POST /mcp - identity workflow', () => {
    let testServer: PersonalMCPHttpServer;

    beforeAll(() => {
      // Fresh server for identity tests
      testServer = new PersonalMCPHttpServer({ port: 8083 });
    });

    it('creates identity and signs voice', async () => {
      // Create identity
      const createResponse = await request(testServer.getApp())
        .post('/mcp')
        .send({
          jsonrpc: '2.0',
          method: 'tools/call',
          params: {
            name: 'identity_create',
            arguments: { tier: 'private', password: 'test123' },
          },
          id: 1,
        })
        .expect(200);

      const createResult = JSON.parse(createResponse.body.result.content[0].text);
      expect(createResult.success).toBe(true);
      expect(createResult.identity.tier).toBe('private');
      expect(createResult.identity.publicKey).toBeDefined();
      expect(createResult.mnemonic).toBeDefined();

      // Check status
      const statusResponse = await request(testServer.getApp())
        .post('/mcp')
        .send({
          jsonrpc: '2.0',
          method: 'tools/call',
          params: { name: 'identity_status' },
          id: 2,
        })
        .expect(200);

      const statusResult = JSON.parse(statusResponse.body.result.content[0].text);
      expect(statusResult.hasIdentity).toBe(true);
      expect(statusResult.isUnlocked).toBe(true);

      // Sign voice
      const signResponse = await request(testServer.getApp())
        .post('/mcp')
        .send({
          jsonrpc: '2.0',
          method: 'tools/call',
          params: {
            name: 'sign_voice',
            arguments: {
              entity: 'decision:city-san-rafael:2026-01-15:item-6a',
              jurisdiction: 'city-san-rafael',
              stance: 'support',
            },
          },
          id: 3,
        })
        .expect(200);

      const signResult = JSON.parse(signResponse.body.result.content[0].text);
      expect(signResult.success).toBe(true);
      expect(signResult.event.kind).toBe(30800);
      expect(signResult.event.pubkey).toBe(createResult.identity.publicKey);
      expect(signResult.event.sig).toBeDefined();
    });

    it('signs commitment and completion', async () => {
      // Sign commitment
      const commitResponse = await request(testServer.getApp())
        .post('/mcp')
        .send({
          jsonrpc: '2.0',
          method: 'tools/call',
          params: {
            name: 'sign_commitment',
            arguments: {
              action_id: 'action:city-san-rafael:initiative-123:comment',
              jurisdiction: 'city-san-rafael',
            },
          },
          id: 4,
        })
        .expect(200);

      const commitResult = JSON.parse(commitResponse.body.result.content[0].text);
      expect(commitResult.success).toBe(true);
      expect(commitResult.event.kind).toBe(30801);

      // Sign completion
      const completeResponse = await request(testServer.getApp())
        .post('/mcp')
        .send({
          jsonrpc: '2.0',
          method: 'tools/call',
          params: {
            name: 'sign_completion',
            arguments: {
              action_id: 'action:city-san-rafael:initiative-123:comment',
              jurisdiction: 'city-san-rafael',
              evidence_url: 'https://example.com/comment-123',
            },
          },
          id: 5,
        })
        .expect(200);

      const completeResult = JSON.parse(completeResponse.body.result.content[0].text);
      expect(completeResult.success).toBe(true);
      expect(completeResult.event.kind).toBe(30802);
    });
  });

  describe('POST /mcp - error handling', () => {
    it('returns error for unknown method', async () => {
      const response = await request(server.getApp())
        .post('/mcp')
        .send({ jsonrpc: '2.0', method: 'unknown/method', params: {}, id: 1 })
        .expect(200);

      expect(response.body.error.code).toBe(-32601);
      expect(response.body.error.message).toContain('Method not found');
    });

    it('returns error for missing tool name', async () => {
      const response = await request(server.getApp())
        .post('/mcp')
        .send({ jsonrpc: '2.0', method: 'tools/call', params: {}, id: 1 })
        .expect(200);

      expect(response.body.error.code).toBe(-32602);
      expect(response.body.error.message).toContain('Missing tool name');
    });
  });
});
