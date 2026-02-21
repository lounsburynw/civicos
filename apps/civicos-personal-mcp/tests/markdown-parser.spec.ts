/**
 * Tests for markdown-parser.ts
 *
 * Validates round-trip parse/render for profile and jurisdiction files.
 */

import { describe, it, expect } from 'vitest';
import {
  parseMarkdown,
  renderMarkdown,
  parseOrderedList,
  renderOrderedList,
} from '../lib/storage/markdown-parser.js';

describe('parseMarkdown', () => {
  it('parses title and sections with key-value pairs', () => {
    const content = `# My Civic Profile

## Identity
- Name: Alice
- Email: alice@example.com

## Location
- Neighborhood: Terra Linda
- Latitude: 37.9735
`;

    const result = parseMarkdown(content);
    expect(result.title).toBe('My Civic Profile');
    expect(result.sections['Identity']).toEqual({
      Name: 'Alice',
      Email: 'alice@example.com',
    });
    expect(result.sections['Location']).toEqual({
      Neighborhood: 'Terra Linda',
      Latitude: '37.9735',
    });
  });

  it('handles missing title', () => {
    const content = `## Section
- Key: Value
`;
    const result = parseMarkdown(content);
    expect(result.title).toBeUndefined();
    expect(result.sections['Section']).toEqual({ Key: 'Value' });
  });

  it('ignores lines that are not h1, h2, or key-value', () => {
    const content = `# Title

Some comment that should be ignored.

## Section
- Key: Value
Another ignored line.
- Another: Pair
`;
    const result = parseMarkdown(content);
    expect(result.title).toBe('Title');
    expect(result.sections['Section']).toEqual({
      Key: 'Value',
      Another: 'Pair',
    });
  });

  it('handles colons in values', () => {
    const content = `## Config
- URL: https://example.com:8080/path
`;
    const result = parseMarkdown(content);
    expect(result.sections['Config']['URL']).toBe('https://example.com:8080/path');
  });

  it('handles empty content', () => {
    const result = parseMarkdown('');
    expect(result.title).toBeUndefined();
    expect(result.sections).toEqual({});
  });

  it('handles key-value pairs before any section (ignored)', () => {
    const content = `# Title
- Orphan: Value

## Section
- Key: Value
`;
    const result = parseMarkdown(content);
    expect(result.sections['Section']).toEqual({ Key: 'Value' });
    // Orphan key-value not in any section
    expect(Object.keys(result.sections)).toEqual(['Section']);
  });

  it('handles asterisk list markers', () => {
    const content = `## Section
* Key: Value
* Another: Pair
`;
    const result = parseMarkdown(content);
    expect(result.sections['Section']).toEqual({
      Key: 'Value',
      Another: 'Pair',
    });
  });
});

describe('renderMarkdown', () => {
  it('renders title and sections', () => {
    const data = {
      title: 'My Profile',
      sections: {
        Identity: { Name: 'Alice', Email: 'alice@example.com' },
        Location: { Neighborhood: 'Terra Linda' },
      },
    };

    const result = renderMarkdown(data);
    expect(result).toContain('# My Profile');
    expect(result).toContain('## Identity');
    expect(result).toContain('- Name: Alice');
    expect(result).toContain('- Email: alice@example.com');
    expect(result).toContain('## Location');
    expect(result).toContain('- Neighborhood: Terra Linda');
  });

  it('renders without title', () => {
    const data = {
      sections: { Section: { Key: 'Value' } },
    };
    const result = renderMarkdown(data);
    expect(result).not.toMatch(/^# /m); // No h1 title line
    expect(result).toContain('## Section');
    expect(result).toContain('- Key: Value');
  });

  it('ends with newline', () => {
    const data = { title: 'Test', sections: { S: { K: 'V' } } };
    const result = renderMarkdown(data);
    expect(result.endsWith('\n')).toBe(true);
  });
});

describe('parseMarkdown + renderMarkdown round-trip', () => {
  it('round-trips key-value sections', () => {
    const original = {
      title: 'Preferences',
      sections: {
        Notifications: { 'Email Digest': 'weekly', 'Meeting Reminders': 'true' },
        Display: { Theme: 'system', Language: 'en' },
      },
    };

    const rendered = renderMarkdown(original);
    const parsed = parseMarkdown(rendered);

    expect(parsed.title).toBe(original.title);
    expect(parsed.sections).toEqual(original.sections);
  });
});

describe('parseOrderedList', () => {
  it('parses numbered items', () => {
    const content = `# My Jurisdictions

1. city-san-rafael
2. county-marin
3. state-california
`;
    const result = parseOrderedList(content);
    expect(result).toEqual(['city-san-rafael', 'county-marin', 'state-california']);
  });

  it('parses unordered items as fallback', () => {
    const content = `# Jurisdictions
- city-san-rafael
- county-marin
`;
    const result = parseOrderedList(content);
    expect(result).toEqual(['city-san-rafael', 'county-marin']);
  });

  it('ignores key-value pairs in unordered lists', () => {
    const content = `- city-san-rafael
- Key: Value
- county-marin
`;
    const result = parseOrderedList(content);
    expect(result).toEqual(['city-san-rafael', 'county-marin']);
  });

  it('ignores titles and comments', () => {
    const content = `# My Jurisdictions

Ordered by priority.

1. city-san-rafael
2. county-marin
`;
    const result = parseOrderedList(content);
    expect(result).toEqual(['city-san-rafael', 'county-marin']);
  });

  it('handles empty content', () => {
    expect(parseOrderedList('')).toEqual([]);
  });
});

describe('renderOrderedList', () => {
  it('renders title, preamble, and numbered items', () => {
    const result = renderOrderedList(
      'My Jurisdictions',
      'Ordered by priority.',
      ['city-san-rafael', 'county-marin']
    );

    expect(result).toContain('# My Jurisdictions');
    expect(result).toContain('Ordered by priority.');
    expect(result).toContain('1. city-san-rafael');
    expect(result).toContain('2. county-marin');
  });

  it('ends with newline', () => {
    const result = renderOrderedList('Title', '', ['item']);
    expect(result.endsWith('\n')).toBe(true);
  });
});

describe('parseOrderedList + renderOrderedList round-trip', () => {
  it('round-trips jurisdiction list', () => {
    const items = ['city-san-rafael', 'county-marin', 'state-california'];
    const rendered = renderOrderedList('My Jurisdictions', 'Ordered by priority.', items);
    const parsed = parseOrderedList(rendered);
    expect(parsed).toEqual(items);
  });
});
