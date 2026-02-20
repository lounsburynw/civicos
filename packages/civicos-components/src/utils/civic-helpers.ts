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

// --- Urgency & Focal Point Utilities ---

export type FocalMeeting = {
  title: string;
  date: string;
  time: string;
  location: string;
  meeting_datetime: string;
  days_until: number;
  agendaItems: Array<{ id?: string; title: string; project_type?: string }>;
};

/**
 * Compute city meetings happening within `withinDays` days of `referenceTime`.
 * Returns enriched meeting objects with `days_until` and linked agenda items.
 */
export function computeCityFocalMeetings(
  meetings: Array<{ title: string; date: string; time: string; location: string; meeting_datetime: string }>,
  upcomingItems: Array<{ id?: string; title: string; meeting_title?: string; project_type?: string }>,
  referenceTime: Date,
  withinDays = 7,
): FocalMeeting[] {
  return meetings
    .filter(m => {
      if (!m.meeting_datetime) return false;
      const diffMs = new Date(m.meeting_datetime).getTime() - referenceTime.getTime();
      const diffDays = Math.ceil(diffMs / (1000 * 60 * 60 * 24));
      return diffDays >= 0 && diffDays <= withinDays;
    })
    .map(m => {
      const diffMs = new Date(m.meeting_datetime).getTime() - referenceTime.getTime();
      const daysUntil = Math.ceil(diffMs / (1000 * 60 * 60 * 24));
      const agendaItems = upcomingItems.filter(i => i.meeting_title === m.title);
      return { ...m, days_until: daysUntil, agendaItems };
    });
}

/**
 * Returns a CSS class name for urgency-based coloring.
 */
export function urgencyClass(days: number): string {
  if (days <= 0) return 'urgent-closed';
  if (days <= 3) return 'urgent-critical';
  if (days <= 7) return 'urgent-soon';
  return 'urgent-normal';
}

/**
 * Look up how many days until a city meeting (by title).
 * Returns null if meeting not found or already past.
 */
export function meetingDaysUntil(
  meetingTitle: string,
  meetings: Array<{ title: string; meeting_datetime: string }>,
  referenceTime: Date,
): number | null {
  const meeting = meetings.find(m => m.title === meetingTitle);
  if (!meeting?.meeting_datetime) return null;
  const diffMs = new Date(meeting.meeting_datetime).getTime() - referenceTime.getTime();
  const days = Math.ceil(diffMs / (1000 * 60 * 60 * 24));
  return days >= 0 ? days : null;
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
