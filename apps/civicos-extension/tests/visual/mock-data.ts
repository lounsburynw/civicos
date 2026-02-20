// Fixed timestamp to prevent screenshot drift
const FIXED_TIMESTAMP = '2026-01-15T14:30:00.000Z';

export type PulseData = {
  decisions_this_week: Array<{ title: string; date: string; time: string; location: string; meeting_datetime: string }>;
  upcoming_items?: Array<{ id?: string; title: string; meeting_title?: string; project_type?: string; description?: string; summary?: string; status?: string; official_url?: string }>;
  recent_outcomes: Array<{ id?: string; title: string; date: string; outcome: string; is_upcoming?: boolean; summary?: string; official_url?: string }>;
  generated_at: string;
  comment_periods?: Array<{ document_number: string; title: string; abstract?: string; agency_names: string[]; comments_close_on: string; comment_url?: string; html_url?: string; days_remaining: number; document_type?: string; topics?: string[]; pdf_url?: string; publication_date?: string }>;
  upcoming_hearings?: Array<{ bill_id: string; bill_number?: string; bill_name?: string; event_date: string; committee?: string; location?: string; description?: string; summary?: string; official_url?: string; days_until: number }>;
  governors_desk?: Array<{ bill_id: string; bill_number?: string; bill_name?: string; summary?: string; enrolled_date?: string }>;
};

export const cityPulse: PulseData = {
  generated_at: FIXED_TIMESTAMP,
  decisions_this_week: [
    {
      title: 'City Council Regular Meeting',
      date: 'January 21, 2026',
      time: '7:00 PM',
      location: 'City Hall Council Chambers, 1400 Fifth Ave',
      meeting_datetime: '2026-01-21T19:00:00-08:00',
    },
    {
      title: 'Planning Commission Meeting',
      date: 'January 22, 2026',
      time: '7:00 PM',
      location: 'City Hall Council Chambers',
      meeting_datetime: '2026-01-22T19:00:00-08:00',
    },
  ],
  upcoming_items: [
    {
      id: 'agenda-001',
      title: 'Downtown Precise Plan Amendment — Mixed-Use Zoning Update',
      meeting_title: 'City Council Regular Meeting',
      project_type: 'Zoning',
      description: 'Proposed amendment to allow increased density in the downtown corridor',
    },
    {
      id: 'agenda-002',
      title: 'FY 2026-27 Capital Improvement Program Review',
      meeting_title: 'City Council Regular Meeting',
      project_type: 'Budget',
      description: 'Annual review of capital improvement projects and priorities',
    },
  ],
  recent_outcomes: [
    {
      id: 'decision-001',
      title: 'Short-Term Rental Ordinance Update',
      date: '2026-01-14',
      outcome: 'passed',
      summary: 'Updated regulations for short-term rentals requiring annual permits and 30-day minimum stays in residential zones.',
    },
    {
      id: 'decision-002',
      title: 'Bicycle Safety Infrastructure Bond',
      date: '2026-01-14',
      outcome: 'passed',
      summary: 'Approved $2.3M bond measure for protected bike lanes on major corridors.',
    },
  ],
};

export const statePulse: PulseData = {
  generated_at: FIXED_TIMESTAMP,
  decisions_this_week: [
    { title: 'Housing', date: '12 bills', time: '3 in committee', location: '', meeting_datetime: '' },
    { title: 'Transportation', date: '8 bills', time: '2 hearings', location: '', meeting_datetime: '' },
    { title: 'Environment', date: '6 bills', time: '1 hearing', location: '', meeting_datetime: '' },
    { title: 'Education', date: '5 bills', time: '', location: '', meeting_datetime: '' },
  ],
  upcoming_items: [
    {
      id: 'ca-ab-1234',
      title: 'AB 1234 — California Housing Accountability Act',
      meeting_title: 'Assembly Housing Committee',
      status: 'In Committee',
      summary: 'Strengthens the Housing Accountability Act by limiting local governments\' ability to deny housing projects that comply with existing zoning and land use regulations.',
      description: 'Key housing production bill — affects local zoning authority',
      official_url: 'https://leginfo.legislature.ca.gov/faces/billNavClient.xhtml?bill_id=202520260AB1234',
    },
    {
      id: 'ca-sb-567',
      title: 'SB 567 — Renewable Energy Grid Modernization',
      meeting_title: 'Senate Energy, Utilities and Communications',
      status: 'Second Reading',
      summary: 'Requires investor-owned utilities to achieve 90% renewable energy by 2035 and establishes community solar programs for low-income residents.',
      official_url: 'https://leginfo.legislature.ca.gov/faces/billNavClient.xhtml?bill_id=202520260SB567',
    },
  ],
  recent_outcomes: [
    {
      id: 'ca-ab-890',
      title: 'AB 890 — Wildfire Prevention and Forest Management',
      date: '2026-01-10',
      outcome: 'passed',
      summary: 'Allocates $500M for wildfire prevention including defensible space requirements and prescribed burn programs.',
      official_url: 'https://leginfo.legislature.ca.gov/faces/billNavClient.xhtml?bill_id=202520260AB890',
    },
    {
      id: 'ca-sb-321',
      title: 'SB 321 — Community College Funding Formula Reform',
      date: '2026-01-08',
      outcome: 'failed',
      summary: 'Proposed changes to the Student Centered Funding Formula were rejected by the Senate Education Committee.',
    },
  ],
  upcoming_hearings: [
    {
      bill_id: 'ca-ab-1234',
      bill_number: 'AB 1234',
      bill_name: 'California Housing Accountability Act',
      event_date: '2026-01-23',
      committee: 'Assembly Housing Committee',
      location: 'State Capitol, Room 437',
      summary: 'Public hearing on amendments to the Housing Accountability Act.',
      days_until: 8,
    },
  ],
  governors_desk: [
    {
      bill_id: 'ca-ab-555',
      bill_number: 'AB 555',
      bill_name: 'Paid Family Leave Expansion',
      summary: 'Expands California\'s Paid Family Leave program from 8 to 12 weeks and increases wage replacement to 90% for low-income workers.',
      enrolled_date: '2026-01-12',
    },
  ],
};

export const federalPulse: PulseData = {
  generated_at: FIXED_TIMESTAMP,
  decisions_this_week: [
    { title: 'Rulemaking', date: '3 open', time: '2 closing soon', location: '', meeting_datetime: '' },
    { title: 'Appropriations', date: '1 bill', time: '', location: '', meeting_datetime: '' },
  ],
  upcoming_items: [],
  recent_outcomes: [
    {
      id: 'fed-hr-4567',
      title: 'HR 4567 — Infrastructure Investment and Jobs Act Extension',
      date: '2026-01-12',
      outcome: 'passed',
      summary: 'Extended infrastructure funding authorization through 2030 with $50B in additional broadband deployment funding.',
    },
  ],
  comment_periods: [
    {
      document_number: 'EPA-2026-0042',
      title: 'National Ambient Air Quality Standards for Particulate Matter',
      abstract: 'The Environmental Protection Agency proposes to revise the primary annual PM2.5 standard from 12.0 to 9.0 micrograms per cubic meter to provide increased protection against health effects associated with long-term PM2.5 exposure, including premature death and cardiovascular effects.',
      agency_names: ['Environmental Protection Agency'],
      comments_close_on: '2026-01-18',
      comment_url: 'https://www.regulations.gov/comment/EPA-2026-0042-0001',
      html_url: 'https://www.federalregister.gov/d/2026-00042',
      days_remaining: 3,
      document_type: 'proposed_rule',
      topics: ['Air Quality', 'Public Health', 'Environmental Standards'],
    },
    {
      document_number: 'DOT-2026-0108',
      title: 'Automated Vehicle Safety Framework',
      abstract: 'The Department of Transportation proposes a comprehensive safety framework for automated driving systems operating on public roads, establishing performance standards and reporting requirements for manufacturers.',
      agency_names: ['Department of Transportation', 'National Highway Traffic Safety Administration'],
      comments_close_on: '2026-02-15',
      comment_url: 'https://www.regulations.gov/comment/DOT-2026-0108-0001',
      html_url: 'https://www.federalregister.gov/d/2026-00108',
      days_remaining: 31,
      document_type: 'proposed_rule',
      topics: ['Transportation Safety', 'Autonomous Vehicles'],
    },
  ],
};

export const pulseByLevel: Record<string, PulseData> = {
  city: cityPulse,
  state: statePulse,
  federal: federalPulse,
};
