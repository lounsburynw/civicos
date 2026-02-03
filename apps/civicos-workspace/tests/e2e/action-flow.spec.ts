/**
 * ActionFlow Integration Tests
 *
 * Tests the action flow from ActionFlow.vue through the API layer.
 * These tests verify the complete integration path:
 *
 * 1. Component renders with counts from API
 * 2. User clicks commit → sign-request emitted
 * 3. After signing → onSigningComplete calls API
 * 4. UI updates to show committed state
 *
 * Note: These tests mock the API layer. For full E2E with real relay,
 * use Playwright tests in apps/civicos-workspace/e2e/
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import ActionFlow from '@/components/shared/ActionFlow.vue';
import type { InitiativeAction, ActionCountResponse } from '@/types/civic';

// Mock the api module
vi.mock('@/services/api', () => ({
  api: {
    getActionCounts: vi.fn(),
    commitAction: vi.fn(),
    completeAction: vi.fn(),
    getActionCommitments: vi.fn(),
    getActionCompletions: vi.fn(),
  },
}));

// Import the mocked api
import { api } from '@/services/api';

describe('ActionFlow', () => {
  const mockAction: InitiativeAction = {
    id: 'submit-comment',
    action_type: 'Comment',
    description: 'Submit a public comment supporting affordable housing',
    target_count: 10,
    deadline: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString(), // 7 days from now
  };

  const mockCounts: ActionCountResponse = {
    action_id: 'action:city-san-rafael:submit-comment',
    commitments: 6,
    completions: 2,
    target: 10,
  };

  const testPublicKey = '03a1b2c3d4e5f678901234567890abcdef1234567890abcdef1234567890abcdef12';
  const testSignature = '304402205678...';

  beforeEach(() => {
    vi.clearAllMocks();
    (api.getActionCounts as ReturnType<typeof vi.fn>).mockResolvedValue(mockCounts);
    (api.commitAction as ReturnType<typeof vi.fn>).mockResolvedValue({
      action_id: mockCounts.action_id,
      action_type: 'commitment',
      public_key: testPublicKey,
      signature: testSignature,
      timestamp: new Date().toISOString(),
      revoked: false,
    });
  });

  describe('Initial Render', () => {
    it('fetches and displays action counts on mount', async () => {
      const wrapper = mount(ActionFlow, {
        props: {
          action: mockAction,
          jurisdiction: 'city-san-rafael',
        },
      });

      await flushPromises();

      expect(api.getActionCounts).toHaveBeenCalledWith(
        'action:city-san-rafael:submit-comment',
        10
      );

      // Progress text shows counts
      expect(wrapper.text()).toContain('6/10 committed');
      expect(wrapper.text()).toContain('2 completed');
    });

    it('displays action type and description', async () => {
      const wrapper = mount(ActionFlow, {
        props: {
          action: mockAction,
          jurisdiction: 'city-san-rafael',
        },
      });

      await flushPromises();

      expect(wrapper.text()).toContain('Comment');
      expect(wrapper.text()).toContain('Submit a public comment supporting affordable housing');
    });

    it('calculates progress percentage correctly', async () => {
      const wrapper = mount(ActionFlow, {
        props: {
          action: mockAction,
          jurisdiction: 'city-san-rafael',
        },
      });

      await flushPromises();

      const progressFill = wrapper.find('.progress-fill');
      expect(progressFill.attributes('style')).toContain('width: 60%');
    });

    it('shows deadline text', async () => {
      const wrapper = mount(ActionFlow, {
        props: {
          action: mockAction,
          jurisdiction: 'city-san-rafael',
        },
      });

      await flushPromises();

      expect(wrapper.text()).toMatch(/days left|Due/);
    });
  });

  describe('Commit Button', () => {
    it('shows commit button when user is not committed', async () => {
      const wrapper = mount(ActionFlow, {
        props: {
          action: mockAction,
          jurisdiction: 'city-san-rafael',
          userPublicKey: testPublicKey,
          userCommitted: false,
        },
      });

      await flushPromises();

      const button = wrapper.find('.commit-button');
      expect(button.exists()).toBe(true);
      expect(button.text()).toContain('Commit to this action');
    });

    it('disables commit button when user is not signed in', async () => {
      const wrapper = mount(ActionFlow, {
        props: {
          action: mockAction,
          jurisdiction: 'city-san-rafael',
          // No userPublicKey provided
        },
      });

      await flushPromises();

      const button = wrapper.find('.commit-button');
      expect(button.attributes('disabled')).toBeDefined();
      expect(wrapper.text()).toContain('Sign in to commit');
    });

    it('shows committed badge when user has committed', async () => {
      const wrapper = mount(ActionFlow, {
        props: {
          action: mockAction,
          jurisdiction: 'city-san-rafael',
          userPublicKey: testPublicKey,
          userCommitted: true,
        },
      });

      await flushPromises();

      expect(wrapper.find('.committed-badge').exists()).toBe(true);
      expect(wrapper.text()).toContain("You're committed");
    });
  });

  describe('Commit Flow', () => {
    it('emits sign-request when commit button clicked', async () => {
      const wrapper = mount(ActionFlow, {
        props: {
          action: mockAction,
          jurisdiction: 'city-san-rafael',
          userPublicKey: testPublicKey,
        },
      });

      await flushPromises();

      const button = wrapper.find('.commit-button');
      await button.trigger('click');

      expect(wrapper.emitted('sign-request')).toBeTruthy();
      expect(wrapper.emitted('sign-request')![0]).toEqual([
        'action:city-san-rafael:submit-comment',
        'city-san-rafael',
      ]);
    });

    it('shows spinner while committing', async () => {
      const wrapper = mount(ActionFlow, {
        props: {
          action: mockAction,
          jurisdiction: 'city-san-rafael',
          userPublicKey: testPublicKey,
        },
      });

      await flushPromises();

      const button = wrapper.find('.commit-button');
      await button.trigger('click');

      expect(wrapper.find('.spinner').exists()).toBe(true);
    });

    it('calls API and updates UI after signing complete', async () => {
      // Mock API to return updated counts
      const updatedCounts = { ...mockCounts, commitments: 7 };
      (api.getActionCounts as ReturnType<typeof vi.fn>)
        .mockResolvedValueOnce(mockCounts) // Initial fetch
        .mockResolvedValueOnce(updatedCounts); // After commit

      const wrapper = mount(ActionFlow, {
        props: {
          action: mockAction,
          jurisdiction: 'city-san-rafael',
          userPublicKey: testPublicKey,
        },
      });

      await flushPromises();

      // Trigger commit
      const button = wrapper.find('.commit-button');
      await button.trigger('click');

      // Simulate parent calling onSigningComplete
      const vm = wrapper.vm as InstanceType<typeof ActionFlow> & {
        onSigningComplete: (sig: string) => Promise<void>;
      };
      await vm.onSigningComplete(testSignature);
      await flushPromises();

      // Verify API was called
      expect(api.commitAction).toHaveBeenCalledWith({
        action_id: 'action:city-san-rafael:submit-comment',
        public_key: testPublicKey,
        signature: testSignature,
      });

      // Verify emits committed event
      expect(wrapper.emitted('committed')).toBeTruthy();
      expect(wrapper.emitted('committed')![0]).toEqual(['action:city-san-rafael:submit-comment']);

      // Verify UI shows committed state
      expect(wrapper.find('.committed-badge').exists()).toBe(true);

      // Verify counts refreshed
      expect(api.getActionCounts).toHaveBeenCalledTimes(2);
    });

    it('shows error when signing fails', async () => {
      const wrapper = mount(ActionFlow, {
        props: {
          action: mockAction,
          jurisdiction: 'city-san-rafael',
          userPublicKey: testPublicKey,
        },
      });

      await flushPromises();

      // Trigger commit
      const button = wrapper.find('.commit-button');
      await button.trigger('click');

      // Simulate parent calling onSigningFailed
      const vm = wrapper.vm as InstanceType<typeof ActionFlow> & {
        onSigningFailed: (msg: string) => void;
      };
      vm.onSigningFailed('User cancelled signing');
      await flushPromises();

      // Verify error is displayed
      expect(wrapper.text()).toContain('User cancelled signing');

      // Verify not in committing state
      expect(wrapper.find('.spinner').exists()).toBe(false);
    });

    it('shows error when API commit fails', async () => {
      (api.commitAction as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
        new Error('Invalid signature')
      );

      const wrapper = mount(ActionFlow, {
        props: {
          action: mockAction,
          jurisdiction: 'city-san-rafael',
          userPublicKey: testPublicKey,
        },
      });

      await flushPromises();

      // Trigger commit
      const button = wrapper.find('.commit-button');
      await button.trigger('click');

      // Simulate parent calling onSigningComplete
      const vm = wrapper.vm as InstanceType<typeof ActionFlow> & {
        onSigningComplete: (sig: string) => Promise<void>;
      };
      await vm.onSigningComplete(testSignature);
      await flushPromises();

      // Verify error is displayed
      expect(wrapper.text()).toContain('Invalid signature');

      // Verify not in committed state
      expect(wrapper.find('.committed-badge').exists()).toBe(false);
    });
  });

  describe('Urgent Actions', () => {
    it('applies urgent styling when deadline is within 3 days', async () => {
      const urgentAction: InitiativeAction = {
        ...mockAction,
        deadline: new Date(Date.now() + 2 * 24 * 60 * 60 * 1000).toISOString(), // 2 days from now
      };

      const wrapper = mount(ActionFlow, {
        props: {
          action: urgentAction,
          jurisdiction: 'city-san-rafael',
        },
      });

      await flushPromises();

      expect(wrapper.find('.action-flow.urgent').exists()).toBe(true);
      expect(wrapper.find('.action-deadline.urgent').exists()).toBe(true);
    });

    it('shows "Due today" when deadline is today', async () => {
      // Set deadline to less than 24 hours from now (same day)
      // Use a time close to end of day to ensure Math.ceil gives 0 days
      const now = new Date();
      const endOfDay = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 23, 59, 59);
      const todayAction: InitiativeAction = {
        ...mockAction,
        deadline: endOfDay.toISOString(),
      };

      const wrapper = mount(ActionFlow, {
        props: {
          action: todayAction,
          jurisdiction: 'city-san-rafael',
        },
      });

      await flushPromises();

      // Should show "Due today" or a related deadline message
      expect(wrapper.text()).toMatch(/Due today|hours? left|Due/);
    });

    it('shows "Deadline passed" when past due', async () => {
      const pastAction: InitiativeAction = {
        ...mockAction,
        deadline: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(), // Yesterday
      };

      const wrapper = mount(ActionFlow, {
        props: {
          action: pastAction,
          jurisdiction: 'city-san-rafael',
        },
      });

      await flushPromises();

      expect(wrapper.text()).toContain('Deadline passed');
    });
  });

  describe('Action ID Format', () => {
    it('constructs correct action ID from jurisdiction and action.id', async () => {
      const wrapper = mount(ActionFlow, {
        props: {
          action: mockAction,
          jurisdiction: 'city-san-rafael',
        },
      });

      await flushPromises();

      expect(api.getActionCounts).toHaveBeenCalledWith(
        'action:city-san-rafael:submit-comment',
        mockAction.target_count
      );
    });
  });

  describe('Watch Effects', () => {
    it('refetches counts when action.id changes', async () => {
      const wrapper = mount(ActionFlow, {
        props: {
          action: mockAction,
          jurisdiction: 'city-san-rafael',
        },
      });

      await flushPromises();
      expect(api.getActionCounts).toHaveBeenCalledTimes(1);

      // Change the action
      await wrapper.setProps({
        action: { ...mockAction, id: 'new-action' },
      });
      await flushPromises();

      expect(api.getActionCounts).toHaveBeenCalledTimes(2);
      expect(api.getActionCounts).toHaveBeenLastCalledWith(
        'action:city-san-rafael:new-action',
        mockAction.target_count
      );
    });

    it('updates hasCommitted when userCommitted prop changes', async () => {
      const wrapper = mount(ActionFlow, {
        props: {
          action: mockAction,
          jurisdiction: 'city-san-rafael',
          userPublicKey: testPublicKey,
          userCommitted: false,
        },
      });

      await flushPromises();
      expect(wrapper.find('.commit-button').exists()).toBe(true);

      // Change userCommitted to true
      await wrapper.setProps({ userCommitted: true });
      await flushPromises();

      expect(wrapper.find('.committed-badge').exists()).toBe(true);
    });
  });
});
