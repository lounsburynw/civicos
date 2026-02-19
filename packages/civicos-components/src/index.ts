// Shared utilities
export {
  isPastMeeting,
  formatMeetingTime,
  formatRelativeDate,
  truncateNpub,
  outcomeIcon,
  outcomeClass,
  googleCalendarUrl,
  downloadIcs,
} from './utils/civic-helpers.js';

// Import components to register custom elements
import './components/CivicVoiceButtons.svelte';
import './components/CivicSynthesisBar.svelte';
import './components/CivicAgendaItemCard.svelte';
import './components/CivicDecisionCard.svelte';
import './components/CivicInitiativeCard.svelte';
import './components/CivicCommentThread.svelte';
// Smart view components (own internal state, compose leaf components)
import './components/CivicAgendaView.svelte';
import './components/CivicDecisionView.svelte';
import './components/CivicInitiativeView.svelte';
// Presentation components (self-contained, composable)
import './components/CivicMeetingCard.svelte';
import './components/CivicProvenancePanel.svelte';
import './components/CivicIdentityChip.svelte';
import './components/CivicReadOnlyPulse.svelte';
// Visualization components (own data loading, self-contained rendering)
import './components/CivicIssueMap.svelte';
import './components/CivicBudgetBreakdown.svelte';
