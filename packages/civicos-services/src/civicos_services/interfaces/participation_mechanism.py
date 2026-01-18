"""
ParticipationMechanism Interface

Unified interface for any civic focal point that enables civic action.
Implements abstraction layer for CivicEvent, Complaint, ProposedAgendaItem.

Layer 1: Schema & Data Model (Complaint-to-Civic Implementation)
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from datetime import datetime


class ParticipationMechanism(ABC):
    """
    Abstract interface for any civic focal point.

    Enables unified handling of CivicEvent, Complaint, ProposedAgendaItem
    without tight coupling.
    """

    @abstractmethod
    def get_id(self) -> str:
        """Unique identifier for this focal point"""
        pass

    @abstractmethod
    def get_type(self) -> str:
        """Focal point type: 'CivicEvent' | 'Complaint' | 'ProposedAgendaItem'"""
        pass

    @abstractmethod
    def get_actions(self) -> List[Dict]:
        """
        Available actions for this focal point.

        Returns:
            List of action dictionaries matching MessageAction schema:
            {
                "action_type": "email" | "calendar" | "link" | "complaint_submit",
                "action_label": "Email Council",
                "action_target": "mailto:council@city.gov",
                ...
            }
        """
        pass

    @abstractmethod
    def get_context(self) -> Dict:
        """
        Multi-dimensional context for engagement decision.

        Returns:
            {
                "legislative_context": {...},     # State bills, federal programs
                "financial_context": {...},       # CDBG allocations, budgets
                "community_context": {            # NEW for complaints
                    "neighbor_count": 15,
                    "organizing_status": "active"
                },
                "temporal_context": {
                    "urgency": "high" | "medium" | "low",
                    "time_until_event": 604800  # seconds
                }
            }
        """
        pass

    @abstractmethod
    def get_lifecycle_status(self) -> str:
        """
        Lifecycle stage for this focal point.

        CivicEvent: 'scheduled' | 'in_progress' | 'completed'
        Complaint: 'open' | 'matched' | 'community_formed' | 'escalated' | 'resolved'
        ProposedAgendaItem: 'draft' | 'submitted' | 'accepted' | 'rejected'
        """
        pass

    def is_government_generated(self) -> bool:
        """True if immutable government data (disk), False if user-generated (RAM)"""
        return self.get_type() in ['CivicEvent', 'ElectedOfficial', 'BallotMeasure']

    def get_participation_threshold(self) -> str:
        """Required civic literacy level: 'low' | 'medium' | 'high'"""
        # Default: government focal points require higher literacy
        return 'high' if self.is_government_generated() else 'low'
