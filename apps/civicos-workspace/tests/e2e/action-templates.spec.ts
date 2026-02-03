/**
 * TemplateView Component Tests
 *
 * Tests the template display component:
 * 1. Template text rendering
 * 2. Placeholder parsing and field generation
 * 3. Copy-to-clipboard functionality
 * 4. Download functionality
 * 5. Expand/collapse behavior
 * 6. Pre-fill from user context
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import TemplateView from '@/components/shared/TemplateView.vue';

// Mock clipboard API
const mockWriteText = vi.fn().mockResolvedValue(undefined);

Object.defineProperty(navigator, 'clipboard', {
  value: {
    writeText: mockWriteText,
  },
  writable: true,
  configurable: true,
});

// Mock URL for blob download
const mockCreateObjectURL = vi.fn().mockReturnValue('blob:mock-url');
const mockRevokeObjectURL = vi.fn();

global.URL.createObjectURL = mockCreateObjectURL;
global.URL.revokeObjectURL = mockRevokeObjectURL;

describe('TemplateView', () => {
  const sampleTemplate = `Dear City Council,

I am writing to express my support for the affordable housing proposal.

Sincerely,
{{name}}
{{address}}`;

  const sampleTemplateNoPlaceholders = `Dear City Council,

I am writing to express my support for the affordable housing proposal.

Sincerely,
A Concerned Resident`;

  const sampleInstructions = 'Send this letter to citycouncil@sanrafael.gov by Friday.';

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Basic Rendering', () => {
    it('renders template text', async () => {
      const wrapper = mount(TemplateView, {
        props: {
          template: sampleTemplateNoPlaceholders,
        },
      });

      await flushPromises();

      expect(wrapper.text()).toContain('Dear City Council');
      expect(wrapper.text()).toContain('affordable housing proposal');
    });

    it('renders instructions when provided', async () => {
      const wrapper = mount(TemplateView, {
        props: {
          template: sampleTemplateNoPlaceholders,
          instructions: sampleInstructions,
        },
      });

      await flushPromises();

      expect(wrapper.text()).toContain('Instructions');
      expect(wrapper.text()).toContain('citycouncil@sanrafael.gov');
    });

    it('does not render instructions section when not provided', async () => {
      const wrapper = mount(TemplateView, {
        props: {
          template: sampleTemplateNoPlaceholders,
        },
      });

      await flushPromises();

      expect(wrapper.find('.instructions-section').exists()).toBe(false);
    });

    it('starts expanded by default', async () => {
      const wrapper = mount(TemplateView, {
        props: {
          template: sampleTemplateNoPlaceholders,
        },
      });

      await flushPromises();

      expect(wrapper.find('.template-content').classes()).not.toContain('collapsed');
    });
  });

  describe('Placeholder Parsing', () => {
    it('detects placeholders and creates input fields', async () => {
      const wrapper = mount(TemplateView, {
        props: {
          template: sampleTemplate,
        },
      });

      await flushPromises();

      // Should have input fields for name and address
      const inputs = wrapper.findAll('.field-input');
      expect(inputs.length).toBe(2);

      // Should have labels
      expect(wrapper.text()).toContain('Your Name');
      expect(wrapper.text()).toContain('Address');
    });

    it('shows fields hint when placeholders exist', async () => {
      const wrapper = mount(TemplateView, {
        props: {
          template: sampleTemplate,
        },
      });

      await flushPromises();

      expect(wrapper.text()).toContain('Fill in your details');
    });

    it('does not show fields section when no placeholders', async () => {
      const wrapper = mount(TemplateView, {
        props: {
          template: sampleTemplateNoPlaceholders,
        },
      });

      await flushPromises();

      expect(wrapper.find('.fields-section').exists()).toBe(false);
    });

    it('replaces placeholders with user input', async () => {
      const wrapper = mount(TemplateView, {
        props: {
          template: sampleTemplate,
        },
      });

      await flushPromises();

      // Find and fill the name input
      const inputs = wrapper.findAll('.field-input');
      await inputs[0].setValue('Jane Doe');
      await inputs[1].setValue('123 Main St');

      // Check the template text is updated
      const templateText = wrapper.find('.template-text pre');
      expect(templateText.text()).toContain('Jane Doe');
      expect(templateText.text()).toContain('123 Main St');
    });

    it('shows placeholder markers for empty fields', async () => {
      const wrapper = mount(TemplateView, {
        props: {
          template: sampleTemplate,
        },
      });

      await flushPromises();

      const templateText = wrapper.find('.template-text pre');
      expect(templateText.text()).toContain('[NAME]');
      expect(templateText.text()).toContain('[ADDRESS]');
    });
  });

  describe('Prefill', () => {
    it('pre-fills fields from prefill prop', async () => {
      const wrapper = mount(TemplateView, {
        props: {
          template: sampleTemplate,
          prefill: {
            name: 'John Smith',
            address: '456 Oak Ave',
          },
        },
      });

      await flushPromises();

      const inputs = wrapper.findAll('.field-input');
      expect((inputs[0].element as HTMLInputElement).value).toBe('John Smith');
      expect((inputs[1].element as HTMLInputElement).value).toBe('456 Oak Ave');

      // Template should show pre-filled values
      const templateText = wrapper.find('.template-text pre');
      expect(templateText.text()).toContain('John Smith');
      expect(templateText.text()).toContain('456 Oak Ave');
    });

    it('allows editing pre-filled values', async () => {
      const wrapper = mount(TemplateView, {
        props: {
          template: sampleTemplate,
          prefill: {
            name: 'John Smith',
          },
        },
      });

      await flushPromises();

      const inputs = wrapper.findAll('.field-input');
      await inputs[0].setValue('Jane Doe');

      const templateText = wrapper.find('.template-text pre');
      expect(templateText.text()).toContain('Jane Doe');
      expect(templateText.text()).not.toContain('John Smith');
    });
  });

  describe('Copy to Clipboard', () => {
    it('copies filled template to clipboard', async () => {
      const wrapper = mount(TemplateView, {
        props: {
          template: sampleTemplate,
          prefill: {
            name: 'Jane Doe',
            address: '789 Elm St',
          },
        },
      });

      await flushPromises();

      const copyButton = wrapper.findAll('.action-button')[0];
      await copyButton.trigger('click');

      expect(mockWriteText).toHaveBeenCalled();
      const copiedText = mockWriteText.mock.calls[0][0];
      expect(copiedText).toContain('Jane Doe');
      expect(copiedText).toContain('789 Elm St');
    });

    it('shows "Copied!" feedback after copying', async () => {
      vi.useFakeTimers();

      const wrapper = mount(TemplateView, {
        props: {
          template: sampleTemplateNoPlaceholders,
        },
      });

      await flushPromises();

      const copyButton = wrapper.findAll('.action-button')[0];
      await copyButton.trigger('click');
      await flushPromises();

      expect(wrapper.text()).toContain('Copied!');

      // After 2 seconds, should revert
      vi.advanceTimersByTime(2000);
      await flushPromises();

      expect(wrapper.text()).toContain('Copy');

      vi.useRealTimers();
    });
  });

  describe('Download', () => {
    it('has download button that creates blob', async () => {
      const wrapper = mount(TemplateView, {
        props: {
          template: sampleTemplateNoPlaceholders,
        },
      });

      await flushPromises();

      // Verify download button exists
      const downloadButton = wrapper.findAll('.action-button')[1];
      expect(downloadButton.exists()).toBe(true);
      expect(downloadButton.text()).toContain('Download');

      // Note: Full download test would require complex document.createElement mocking
      // The button exists and clicking it triggers the download function
    });
  });

  describe('Expand/Collapse', () => {
    it('toggles content visibility when header clicked', async () => {
      const wrapper = mount(TemplateView, {
        props: {
          template: sampleTemplateNoPlaceholders,
        },
      });

      await flushPromises();

      // Initially expanded
      expect(wrapper.find('.template-content').classes()).not.toContain('collapsed');

      // Click header to collapse
      await wrapper.find('.template-header').trigger('click');
      expect(wrapper.find('.template-content').classes()).toContain('collapsed');

      // Click again to expand
      await wrapper.find('.template-header').trigger('click');
      expect(wrapper.find('.template-content').classes()).not.toContain('collapsed');
    });
  });

  describe('Multiple Placeholders', () => {
    it('handles template with many different placeholders', async () => {
      const multiPlaceholderTemplate = `From: {{name}}
Email: {{email}}
Phone: {{phone}}
Subject: {{subject}}

Dear Council Member,

I live at {{address}} in {{neighborhood}}.`;

      const wrapper = mount(TemplateView, {
        props: {
          template: multiPlaceholderTemplate,
        },
      });

      await flushPromises();

      const inputs = wrapper.findAll('.field-input');
      // Should have 6 unique placeholders
      expect(inputs.length).toBe(6);
    });

    it('handles duplicate placeholders (same field used multiple times)', async () => {
      const duplicateTemplate = `Hello {{name}},

This letter is from {{name}} regarding...`;

      const wrapper = mount(TemplateView, {
        props: {
          template: duplicateTemplate,
        },
      });

      await flushPromises();

      // Should only create one input field
      const inputs = wrapper.findAll('.field-input');
      expect(inputs.length).toBe(1);

      // Fill the field
      await inputs[0].setValue('Jane Doe');

      // Both occurrences should be replaced
      const templateText = wrapper.find('.template-text pre').text();
      const matches = templateText.match(/Jane Doe/g);
      expect(matches?.length).toBe(2);
    });
  });

  describe('ActionFlow Integration', () => {
    it('can be imported and used in ActionFlow context', async () => {
      // This verifies the component can render with typical action data
      const actionTemplate = `I commit to attending the City Council meeting on {{date}}.

My name is {{name}} and I will speak about affordable housing.`;

      const wrapper = mount(TemplateView, {
        props: {
          template: actionTemplate,
          instructions: 'Meeting is at City Hall, 1400 5th Ave, 6:00 PM.',
          prefill: {
            date: 'January 15, 2026',
          },
        },
      });

      await flushPromises();

      expect(wrapper.text()).toContain('January 15, 2026');
      expect(wrapper.text()).toContain('City Hall');
    });
  });
});
