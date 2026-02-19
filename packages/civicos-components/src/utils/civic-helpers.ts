// Shared utility functions for civic components and surfaces.
// Pure functions with no framework or platform dependencies.

export function isPastMeeting(meeting: { meeting_datetime: string }): boolean {
  return new Date(meeting.meeting_datetime) < new Date();
}

export function formatMeetingTime(meeting: { date: string; time: string }): string {
  return meeting.time ? `${meeting.date} @ ${meeting.time}` : meeting.date;
}

export function formatRelativeDate(dateStr: string | null): string {
  if (!dateStr) return 'unknown';
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return dateStr;
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  if (diffDays === 0) return 'today';
  if (diffDays === 1) return 'yesterday';
  if (diffDays < 30) return `${diffDays}d ago`;
  return d.toLocaleDateString();
}

export function truncateNpub(npub: string): string {
  if (npub.length <= 16) return npub;
  return npub.slice(0, 10) + '...' + npub.slice(-6);
}

export function outcomeIcon(outcome: string): string {
  const lower = outcome.toLowerCase();
  if (lower === 'on_agenda') return '\u25B6';
  if (lower.includes('approved') || lower.includes('passed') || lower.includes('adopted') || lower.includes('enrolled') || lower.includes('signed') || lower.includes('enacted')) return '\u2713';
  if (lower.includes('denied') || lower.includes('failed') || lower.includes('rejected') || lower.includes('vetoed')) return '\u2717';
  if (lower.includes('continued') || lower.includes('tabled')) return '\u21BB';
  if (lower.includes('introduced') || lower.includes('engrossed') || lower.includes('active') || lower.includes('pending')) return '\u25B6';
  return '\u2022';
}

export function outcomeClass(outcome: string): string {
  const lower = outcome.toLowerCase();
  if (lower === 'on_agenda') return 'upcoming';
  if (lower.includes('approved') || lower.includes('passed') || lower.includes('adopted') || lower.includes('enrolled') || lower.includes('signed') || lower.includes('enacted')) return 'passed';
  if (lower.includes('denied') || lower.includes('failed') || lower.includes('rejected') || lower.includes('vetoed')) return 'failed';
  if (lower.includes('introduced') || lower.includes('engrossed') || lower.includes('active') || lower.includes('pending')) return 'upcoming';
  return 'other';
}

export function googleCalendarUrl(meeting: { title: string; date: string; time: string; location: string; meeting_datetime: string }): string {
  const start = new Date(meeting.meeting_datetime);
  const end = new Date(start.getTime() + 2 * 60 * 60 * 1000);
  const fmt = (d: Date) => d.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '');
  return `https://www.google.com/calendar/render?action=TEMPLATE&text=${encodeURIComponent(meeting.title)}&dates=${fmt(start)}/${fmt(end)}&location=${encodeURIComponent(meeting.location || '')}`;
}

export function downloadIcs(meeting: { title: string; location: string; meeting_datetime: string }): void {
  const start = new Date(meeting.meeting_datetime);
  const end = new Date(start.getTime() + 2 * 60 * 60 * 1000);
  const fmt = (d: Date) => d.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '');
  const ics = `BEGIN:VCALENDAR\nVERSION:2.0\nBEGIN:VEVENT\nDTSTART:${fmt(start)}\nDTEND:${fmt(end)}\nSUMMARY:${meeting.title}\nLOCATION:${meeting.location || ''}\nEND:VEVENT\nEND:VCALENDAR`;
  const blob = new Blob([ics], { type: 'text/calendar' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${meeting.title.replace(/[^a-zA-Z0-9]/g, '_')}.ics`;
  a.click();
  URL.revokeObjectURL(url);
}
