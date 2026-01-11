"""
Legislative router: legislation, elections, voting records.

Endpoints:
- GET /legislation/state/{topic} - State legislation by topic
- GET /legislation/federal/{topic} - Federal legislation by topic
- GET /elections/{jurisdiction_id} - Elections for jurisdiction
- GET /elections/{election_id} - Single election details
- GET /elections/{election_id}/contests - Election contests
- GET /voting-record/{official}/{jurisdiction} - Official voting record
- GET /legistar/{city}/events - Legistar events
"""

from datetime import datetime
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel


router = APIRouter()


# === Pydantic Models ===

class Bill(BaseModel):
    """Legislation bill."""
    id: str
    number: str
    title: str
    status: Optional[str] = None
    sponsor: Optional[str] = None
    chamber: Optional[str] = None
    last_action: Optional[str] = None
    last_action_date: Optional[str] = None
    url: Optional[str] = None


class Election(BaseModel):
    """Election record."""
    id: str
    name: str
    date: str
    type: str  # primary, general, special
    jurisdiction_id: str
    status: Optional[str] = None


class Contest(BaseModel):
    """Election contest (race)."""
    id: str
    election_id: str
    name: str
    type: str  # candidate, measure
    candidates: Optional[List[Dict[str, Any]]] = None
    description: Optional[str] = None


class VoteRecord(BaseModel):
    """Official vote record."""
    bill_id: str
    bill_title: str
    vote: str  # yes, no, abstain, absent
    vote_date: str


# === Auth Dependency ===

from .dependencies import verify_auth


# === Endpoints ===

@router.get("/legislation/state/{topic}")
async def get_state_legislation(
    topic: str,
    jurisdiction: Optional[str] = Query(None, description="Filter by jurisdiction"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, description="Maximum bills to return"),
    token: str = Depends(verify_auth)
):
    """
    Get state legislation by topic.

    Returns relevant bills from state legislature.
    Requires authentication.
    """
    try:
        # Try to get legislation from storage
        try:
            from civic import Civic
            from dotenv import load_dotenv
            load_dotenv()
            c = Civic(jurisdiction or "city-san-rafael")
            storage = c._storage
        except ImportError:
            raise HTTPException(status_code=503, detail="Civic library not available")

        # Query legislation
        bills = storage.get_legislation(
            topic=topic,
            level="state",
            limit=limit,
            status=status
        )

        return {
            "topic": topic,
            "level": "state",
            "bills": bills,
            "count": len(bills)
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/legislation/federal/{topic}")
async def get_federal_legislation(
    topic: str,
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, description="Maximum bills to return"),
    token: str = Depends(verify_auth)
):
    """
    Get federal legislation by topic.

    Returns relevant bills from Congress.
    Requires authentication.
    """
    try:
        # Try to get legislation from storage
        try:
            from civic import Civic
            from dotenv import load_dotenv
            load_dotenv()
            c = Civic("city-san-rafael")
            storage = c._storage
        except ImportError:
            raise HTTPException(status_code=503, detail="Civic library not available")

        # Query legislation
        bills = storage.get_legislation(
            topic=topic,
            level="federal",
            limit=limit,
            status=status
        )

        return {
            "topic": topic,
            "level": "federal",
            "bills": bills,
            "count": len(bills)
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/elections/{jurisdiction_id}")
async def get_elections(
    jurisdiction_id: str,
    upcoming_only: bool = Query(True, description="Only return upcoming elections"),
    token: str = Depends(verify_auth)
):
    """
    Get elections for a jurisdiction.

    Returns list of upcoming or past elections.
    Requires authentication.
    """
    try:
        # Try to get elections from storage
        try:
            from civic import Civic
            from dotenv import load_dotenv
            load_dotenv()
            c = Civic(jurisdiction_id)
            storage = c._storage
        except ImportError:
            raise HTTPException(status_code=503, detail="Civic library not available")

        # Query elections
        elections = storage.get_elections(
            jurisdiction_id=jurisdiction_id,
            upcoming_only=upcoming_only
        )

        return {
            "jurisdiction_id": jurisdiction_id,
            "elections": elections,
            "count": len(elections)
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/elections/detail/{election_id}")
async def get_election_detail(
    election_id: str,
    token: str = Depends(verify_auth)
):
    """
    Get details for a specific election.

    Returns election metadata and contests.
    Requires authentication.
    """
    try:
        # Try to get election from storage
        try:
            from civic import Civic
            from dotenv import load_dotenv
            load_dotenv()
            c = Civic("city-san-rafael")
            storage = c._storage
        except ImportError:
            raise HTTPException(status_code=503, detail="Civic library not available")

        # Get election
        election = storage.get_election(election_id)
        if not election:
            raise HTTPException(status_code=404, detail=f"Election not found: {election_id}")

        return election

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/elections/detail/{election_id}/contests")
async def get_election_contests(
    election_id: str,
    token: str = Depends(verify_auth)
):
    """
    Get contests (races) for a specific election.

    Returns list of candidate races and ballot measures.
    Requires authentication.
    """
    try:
        # Try to get contests from storage
        try:
            from civic import Civic
            from dotenv import load_dotenv
            load_dotenv()
            c = Civic("city-san-rafael")
            storage = c._storage
        except ImportError:
            raise HTTPException(status_code=503, detail="Civic library not available")

        # Get contests
        contests = storage.get_election_contests(election_id)

        return {
            "election_id": election_id,
            "contests": contests,
            "count": len(contests)
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/voting-record/{official}/{jurisdiction}")
async def get_voting_record(
    official: str,
    jurisdiction: str,
    topic: Optional[str] = Query(None, description="Filter by topic"),
    token: str = Depends(verify_auth)
):
    """
    Get voting record for an elected official.

    Returns list of votes on bills/measures.
    Requires authentication.
    """
    try:
        # Try to get voting record from storage
        try:
            from civic import Civic
            from dotenv import load_dotenv
            load_dotenv()
            c = Civic(jurisdiction)
            storage = c._storage
        except ImportError:
            raise HTTPException(status_code=503, detail="Civic library not available")

        # Get voting record
        votes = storage.get_voting_record(
            official=official,
            jurisdiction_id=jurisdiction,
            topic=topic
        )

        return {
            "official": official,
            "jurisdiction": jurisdiction,
            "votes": votes,
            "count": len(votes)
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/legistar/{city}/events")
async def get_legistar_events(
    city: str,
    days: int = Query(30, description="Days of events to fetch"),
    token: str = Depends(verify_auth)
):
    """
    Get events from Legistar for a city.

    Returns city council meetings, planning sessions, etc.
    Requires authentication.
    """
    try:
        # Try to get events from Legistar client
        try:
            from civic_services.clients.legistar_client import create_client
            client = create_client(city)
            events = client.get_events(days=days)
        except ImportError:
            raise HTTPException(status_code=503, detail="Legistar client not available")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to fetch events for {city}: {str(e)}")

        return {
            "city": city,
            "events": events,
            "count": len(events),
            "source": "legistar"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")
