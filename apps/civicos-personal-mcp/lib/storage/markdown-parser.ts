/**
 * Simple markdown parser for human-editable profile/preference files.
 *
 * Supports:
 * - `# Title` → document title
 * - `## Section` → section key
 * - `- Key: Value` → key-value pair in current section
 * - `1. item` → ordered list items (for jurisdictions.md)
 * - Everything else ignored (users can add comments freely)
 *
 * No dependencies — uses only string operations.
 */

export interface ParsedMarkdown {
  title?: string;
  sections: Record<string, Record<string, string>>;
}

/**
 * Parse a markdown file with ## sections and - Key: Value pairs.
 */
export function parseMarkdown(content: string): ParsedMarkdown {
  const result: ParsedMarkdown = { sections: {} };
  let currentSection: string | null = null;

  for (const rawLine of content.split('\n')) {
    const line = rawLine.trimEnd();

    // # Title (h1)
    const h1Match = line.match(/^#\s+(.+)$/);
    if (h1Match && !line.startsWith('##')) {
      result.title = h1Match[1].trim();
      continue;
    }

    // ## Section (h2)
    const h2Match = line.match(/^##\s+(.+)$/);
    if (h2Match) {
      currentSection = h2Match[1].trim();
      if (!result.sections[currentSection]) {
        result.sections[currentSection] = {};
      }
      continue;
    }

    // - Key: Value (within a section)
    if (currentSection) {
      const kvMatch = line.match(/^[-*]\s+([^:]+):\s*(.*)$/);
      if (kvMatch) {
        const key = kvMatch[1].trim();
        const value = kvMatch[2].trim();
        result.sections[currentSection][key] = value;
      }
    }
  }

  return result;
}

/**
 * Render a ParsedMarkdown back to a markdown string.
 */
export function renderMarkdown(data: ParsedMarkdown): string {
  const lines: string[] = [];

  if (data.title) {
    lines.push(`# ${data.title}`, '');
  }

  const sectionNames = Object.keys(data.sections);
  for (let i = 0; i < sectionNames.length; i++) {
    const section = sectionNames[i];
    const entries = data.sections[section];

    lines.push(`## ${section}`);
    for (const [key, value] of Object.entries(entries)) {
      lines.push(`- ${key}: ${value}`);
    }

    // Blank line between sections
    if (i < sectionNames.length - 1) {
      lines.push('');
    }
  }

  // Ensure trailing newline
  lines.push('');
  return lines.join('\n');
}

/**
 * Parse an ordered list file (e.g., jurisdictions.md).
 * Matches lines like `1. city-san-rafael` or `2. county-marin`.
 * Also matches unordered `- item` lines as fallback.
 */
export function parseOrderedList(content: string): string[] {
  const items: string[] = [];

  for (const rawLine of content.split('\n')) {
    const line = rawLine.trim();

    // Ordered list: 1. item
    const orderedMatch = line.match(/^\d+\.\s+(.+)$/);
    if (orderedMatch) {
      items.push(orderedMatch[1].trim());
      continue;
    }

    // Fallback: unordered list - item (but not key: value)
    const unorderedMatch = line.match(/^[-*]\s+(.+)$/);
    if (unorderedMatch && !unorderedMatch[1].includes(':')) {
      items.push(unorderedMatch[1].trim());
    }
  }

  return items;
}

/**
 * Render an ordered list file with title and preamble.
 */
export function renderOrderedList(title: string, preamble: string, items: string[]): string {
  const lines: string[] = [];

  lines.push(`# ${title}`, '');

  if (preamble) {
    lines.push(preamble, '');
  }

  for (let i = 0; i < items.length; i++) {
    lines.push(`${i + 1}. ${items[i]}`);
  }

  lines.push('');
  return lines.join('\n');
}
