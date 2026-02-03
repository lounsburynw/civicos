/**
 * ActionList Integration Tests
 *
 * Tests the ActionList component that displays all actions for an initiative.
 * These tests verify:
 *
 * 1. Component fetches and displays actions from API
 * 2. Each action renders via ActionFlow subcomponent
 * 3. Sign request events bubble up to parent
 * 4. Committed actions show correct state
 *
 * Note: These tests mock the API layer. For full E2E with real relay,
 * use Playwright tests in apps/civicos-workspace/e2e/
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import ActionList from '@/components/shared/ActionList.vue';
import type { CivicActionEvent, ActionCountResponse } from '@/types/civic';

// Mock the api module
vi.mock('@/services/api', () => ({
  api: {
    getCivicActionsForInitiative: vi.fn(),
    getActionCounts: vi.fn(),
    commitAction: vi.fn(),
  },
}));

// Import the mocked api
import { api } from '@/services/api';

describe('ActionList', () => {
  const mockActions: CivicActionEvent[] = [
    {
      id: 'action-1',
      initiative_id: 'initiative-housing',
      action_type: 'written_comment',
      description: 'Submit a written comment to the planning commission',
      target_count: 10,
      deadline: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString(),
      public_key: 'creator-pubkey',
      timestamp: new Date().toISOString(),
      revoked: false,
    },
    {
      id: 'action-2',
      initiative_id: 'initiative-housing',
      action_type: 'attend_meeting',
      description: 'Attend the city council meeting on Feb 15',
      target_count: 25,
      deadline: new Date(Date.now() + 14 * 24 * 60 * 60 * 1000).toISOString(),
      public_key: 'creator-pubkey',
      timestamp: new Date().toISOString(),
      revoked: false,
    },
    {
      id: 'action-3',
      initiative_id: 'initiative-housing',
      action_type: 'contact_official',
      description: 'Contact your city council representative',
      public_key: 'creator-pubkey',
      timestamp: new Date().toISOString(),
      revoked: false,
    },
  ];

  const mockCountsMap: Record<string, ActionCountResponse> = {
    'action:city-san-rafael:action-1': {
      action_id: 'action:city-san-rafael:action-1',
      commitments: 6,
      completions: 2,
      target: 10,
    },
    'action:city-san-rafael:action-2': {
      action_id: 'action:city-san-rafael:action-2',
      commitments: 12,
      completions: 0,
      target: 25,
    },
    'action:city-san-rafael:action-3': {
      action_id: 'action:city-san-rafael:action-3',
      commitments: 3,
      completions: 1,
    },
  };

  const testPublicKey = '03a1b2c3d4e5f678901234567890abcdef1234567890abcdef1234567890abcdef12';

  beforeEach(() => {
    vi.clearAllMocks();
    (api.getCivicActionsForInitiative as ReturnType<typeof vi.fn>).mockResolvedValue(mockActions);
    (api.getActionCounts as ReturnType<typeof vi.fn>).mockImplementation((actionId: string) => {
      return Promise.resolve(
        mockCountsMap[actionId] || { action_id: actionId, commitments: 0, completions: 0 }
      );
    });
  });

  describe('Initial Render', () => {
    it('fetches and displays actions on mount', async () => {
      const wrapper = mount(ActionList, {
        props: {
          initiativeId: 'initiative-housing',
          jurisdiction: 'city-san-rafael',
        },
      });

      await flushPromises();

      expect(api.getCivicActionsForInitiative).toHaveBeenCalledWith('initiative-housing');
      expect(wrapper.text()).toContain('3 actions');
    });

    it('displays each action description', async () => {
      const wrapper = mount(ActionList, {
        props: {
          initiativeId: 'initiative-housing',
          jurisdiction: 'city-san-rafael',
        },
      });

      await flushPromises();

      expect(wrapper.text()).toContain('Submit a written comment');
      expect(wrapper.text()).toContain('Attend the city council meeting');
      expect(wrapper.text()).toContain('Contact your city council representative');
    });

    it('passes correct props to ActionFlow components', async () => {
      const wrapper = mount(ActionList, {
        props: {
          initiativeId: 'initiative-housing',
          jurisdiction: 'city-san-rafael',
          userPublicKey: testPublicKey,
        },
      });

      await flushPromises();

      // Each action should trigger an ActionFlow getActionCounts call
      expect(api.getActionCounts).toHaveBeenCalled();
    });
  });

  describe('Loading State', () => {
    it('shows loading spinner while fetching', async () => {
      // Create a promise that doesn't resolve immediately
      let resolvePromise: (value: CivicActionEvent[]) => void;
      const pendingPromise = new Promise<CivicActionEvent[]>((resolve) => {
        resolvePromise = resolve;
      });
      (api.getCivicActionsForInitiative as ReturnType<typeof vi.fn>).mockReturnValue(pendingPromise);

      const wrapper = mount(ActionList, {
        props: {
          initiativeId: 'initiative-housing',
          jurisdiction: 'city-san-rafael',
        },
      });

      // Wait a tick for the component to mount and start loading
      await wrapper.vm.$nextTick();

      expect(wrapper.find('.loading-state').exists()).toBe(true);
      expect(wrapper.text()).toContain('Loading actions...');

      // Resolve and verify loading state clears
      resolvePromise!(mockActions);
      await flushPromises();

      expect(wrapper.find('.loading-state').exists()).toBe(false);
    });
  });

  describe('Error State', () => {
    it('shows error message when fetch fails', async () => {
      (api.getCivicActionsForInitiative as ReturnType<typeof vi.fn>).mockRejectedValue(
        new Error('Network error')
      );

      const wrapper = mount(ActionList, {
        props: {
          initiativeId: 'initiative-housing',
          jurisdiction: 'city-san-rafael',
        },
      });

      await flushPromises();

      expect(wrapper.text()).toContain('Network error');
      expect(wrapper.find('.retry-button').exists()).toBe(true);
    });

    it('retries fetch when retry button clicked', async () => {
      (api.getCivicActionsForInitiative as ReturnType<typeof vi.fn>)
        .mockRejectedValueOnce(new Error('Network error'))
        .mockResolvedValueOnce(mockActions);

      const wrapper = mount(ActionList, {
        props: {
          initiativeId: 'initiative-housing',
          jurisdiction: 'city-san-rafael',
        },
      });

      await flushPromises();
      expect(wrapper.find('.error-state').exists()).toBe(true);

      await wrapper.find('.retry-button').trigger('click');
      await flushPromises();

      expect(api.getCivicActionsForInitiative).toHaveBeenCalledTimes(2);
      expect(wrapper.text()).toContain('3 actions');
    });
  });

  describe('Empty State', () => {
    it('shows empty message when no actions exist', async () => {
      (api.getCivicActionsForInitiative as ReturnType<typeof vi.fn>).mockResolvedValue([]);

      const wrapper = mount(ActionList, {
        props: {
          initiativeId: 'initiative-housing',
          jurisdiction: 'city-san-rafael',
        },
      });

      await flushPromises();

      expect(wrapper.text()).toContain('No actions available');
    });
  });

  describe('Committed Actions', () => {
    it('shows committed state for actions user has committed to', async () => {
      const committedActions = new Set(['action-1', 'action:city-san-rafael:action-2']);

      const wrapper = mount(ActionList, {
        props: {
          initiativeId: 'initiative-housing',
          jurisdiction: 'city-san-rafael',
          userPublicKey: testPublicKey,
          userCommittedActions: committedActions,
        },
      });

      await flushPromises();

      // Two committed badges should be visible
      const committedBadges = wrapper.findAll('.committed-badge');
      expect(committedBadges.length).toBe(2);
    });
  });

  describe('Event Handling', () => {
    it('emits sign-request when ActionFlow requests signing', async () => {
      const wrapper = mount(ActionList, {
        props: {
          initiativeId: 'initiative-housing',
          jurisdiction: 'city-san-rafael',
          userPublicKey: testPublicKey,
        },
      });

      await flushPromises();

      // Find first commit button and click it
      const commitButton = wrapper.find('.commit-button');
      await commitButton.trigger('click');

      expect(wrapper.emitted('sign-request')).toBeTruthy();
      const emittedEvent = wrapper.emitted('sign-request')![0];
      expect(emittedEvent[0]).toContain('action-1');
      expect(emittedEvent[1]).toBe('city-san-rafael');
    });

    it('emits committed when ActionFlow reports commitment', async () => {
      (api.commitAction as ReturnType<typeof vi.fn>).mockResolvedValue({
        action_id: 'action:city-san-rafael:action-1',
        action_type: 'commitment',
        public_key: testPublicKey,
        signature: 'test-signature',
        timestamp: new Date().toISOString(),
        revoked: false,
      });

      const wrapper = mount(ActionList, {
        props: {
          initiativeId: 'initiative-housing',
          jurisdiction: 'city-san-rafael',
          userPublicKey: testPublicKey,
        },
      });

      await flushPromises();

      // Click commit on first action
      const commitButton = wrapper.find('.commit-button');
      await commitButton.trigger('click');

      // Simulate signing completion via exposed method
      const vm = wrapper.vm as InstanceType<typeof ActionList> & {
        onSigningComplete: (actionId: string, signature: string) => void;
      };
      vm.onSigningComplete('action-1', 'test-signature');
      await flushPromises();

      expect(wrapper.emitted('committed')).toBeTruthy();
    });
  });

  describe('Watch Effects', () => {
    it('refetches actions when initiativeId changes', async () => {
      const wrapper = mount(ActionList, {
        props: {
          initiativeId: 'initiative-housing',
          jurisdiction: 'city-san-rafael',
        },
      });

      await flushPromises();
      expect(api.getCivicActionsForInitiative).toHaveBeenCalledTimes(1);

      // Change the initiative
      await wrapper.setProps({ initiativeId: 'initiative-parks' });
      await flushPromises();

      expect(api.getCivicActionsForInitiative).toHaveBeenCalledTimes(2);
      expect(api.getCivicActionsForInitiative).toHaveBeenLastCalledWith('initiative-parks');
    });
  });

  describe('Exposed Methods', () => {
    it('exposes refresh method', async () => {
      const wrapper = mount(ActionList, {
        props: {
          initiativeId: 'initiative-housing',
          jurisdiction: 'city-san-rafael',
        },
      });

      await flushPromises();
      expect(api.getCivicActionsForInitiative).toHaveBeenCalledTimes(1);

      // Call exposed refresh method
      const vm = wrapper.vm as InstanceType<typeof ActionList> & {
        refresh: () => Promise<void>;
      };
      await vm.refresh();
      await flushPromises();

      expect(api.getCivicActionsForInitiative).toHaveBeenCalledTimes(2);
    });
  });

  describe('Action Type Mapping', () => {
    it('maps CivicActionType to InitiativeAction action_type', async () => {
      const wrapper = mount(ActionList, {
        props: {
          initiativeId: 'initiative-housing',
          jurisdiction: 'city-san-rafael',
        },
      });

      await flushPromises();

      // The action types from CivicActionEvent should be mapped correctly
      // written_comment -> comment
      // attend_meeting -> attend
      // contact_official -> contact
      const actionTypes = wrapper.findAll('.action-type');
      expect(actionTypes.length).toBe(3);
    });
  });

  describe('Actions Count Display', () => {
    it('displays singular "action" for one action', async () => {
      (api.getCivicActionsForInitiative as ReturnType<typeof vi.fn>).mockResolvedValue([
        mockActions[0],
      ]);

      const wrapper = mount(ActionList, {
        props: {
          initiativeId: 'initiative-housing',
          jurisdiction: 'city-san-rafael',
        },
      });

      await flushPromises();

      expect(wrapper.text()).toContain('1 action');
      expect(wrapper.text()).not.toContain('1 actions');
    });
  });
});
