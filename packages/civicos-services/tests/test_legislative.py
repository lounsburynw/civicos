"""
Tests for legislative router: legislation search, elections, voting records,
and Legistar events.

Mocks external dependencies (CivicOS storage, Legistar client, auth) while
exercising filtering, error handling, and response shaping in the router.

To run:
    pytest packages/civicos-services/tests/test_legislative.py -q --override-ini="addopts="
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from civicos_services.servers.routers.legislative import router


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    """Create a FastAPI app with the legislative router and auth bypassed."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """TestClient with auth dependency overridden."""
    from civicos_services.servers.routers.dependencies import verify_auth, AuthContext

    async def mock_auth():
        return AuthContext(key_id="test-key", source="env", tier="admin")

    app.dependency_overrides[verify_auth] = mock_auth
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _mock_civicos(storage):
    """Create a mock CivicOS instance wired to the given storage mock."""
    mock_civic = MagicMock()
    mock_civic.storage = storage
    return mock_civic


SAMPLE_STATE_BILLS = [
    {"id": "CA-AB-1234", "number": "AB 1234", "title": "Housing Density Act",
     "status": "active", "level": "state"},
    {"id": "CA-SB-567", "number": "SB 567", "title": "Zoning Reform",
     "status": "active", "level": "state"},
]

SAMPLE_FEDERAL_BILLS = [
    {"id": "US-HR-100", "number": "HR 100", "title": "Infrastructure Bill",
     "status": "introduced", "level": "federal"},
]

SAMPLE_ELECTIONS = [
    {"id": "elec-2026-nov", "name": "November 2026 General",
     "date": "2026-11-03", "type": "general", "jurisdiction_id": "city-san-rafael"},
]

SAMPLE_ELECTION_DETAIL = {
    "id": "elec-2026-nov", "name": "November 2026 General",
    "date": "2026-11-03", "type": "general",
    "jurisdiction_id": "city-san-rafael",
    "contests": [{"id": "c1", "name": "City Council District 1"}],
}

SAMPLE_CONTESTS = [
    {"id": "c1", "election_id": "elec-2026-nov", "name": "City Council District 1",
     "type": "candidate"},
    {"id": "c2", "election_id": "elec-2026-nov", "name": "Measure A",
     "type": "measure"},
]

SAMPLE_VOTES = [
    {"bill_id": "CA-AB-1234", "bill_title": "Housing Density Act",
     "vote": "yes", "vote_date": "2026-03-15"},
    {"bill_id": "CA-SB-567", "bill_title": "Zoning Reform",
     "vote": "no", "vote_date": "2026-04-01"},
]

SAMPLE_EVENTS = [
    {"id": "evt-1", "name": "City Council Meeting", "date": "2026-04-15"},
    {"id": "evt-2", "name": "Planning Commission", "date": "2026-04-17"},
]


# ---------------------------------------------------------------------------
# State legislation
# ---------------------------------------------------------------------------

class TestStateLegislation:
    def test_returns_bills_for_topic(self, client):
        storage = MagicMock()
        storage.get_legislation.return_value = SAMPLE_STATE_BILLS

        with patch(
            "civicos.CivicOS",
            return_value=_mock_civicos(storage),
        ) as mock_cls, patch("dotenv.load_dotenv"):
            resp = client.get("/legislation/state/housing")

        assert resp.status_code == 200
        body = resp.json()
        assert body["topic"] == "housing"
        assert body["level"] == "state"
        assert body["count"] == 2
        assert body["bills"][0]["id"] == "CA-AB-1234"
        assert body["bills"][1]["title"] == "Zoning Reform"
        storage.get_legislation.assert_called_once_with(
            topic="housing", level="state", limit=50, status=None,
        )

    def test_passes_jurisdiction_to_civicos(self, client):
        storage = MagicMock()
        storage.get_legislation.return_value = []

        with patch(
            "civicos.CivicOS",
            return_value=_mock_civicos(storage),
        ) as mock_cls, patch("dotenv.load_dotenv"):
            resp = client.get("/legislation/state/transit?jurisdiction=city-larkspur")

        assert resp.status_code == 200
        mock_cls.assert_called_once_with("city-larkspur")
        assert resp.json()["count"] == 0
        assert resp.json()["bills"] == []

    def test_defaults_jurisdiction_to_san_rafael(self, client):
        storage = MagicMock()
        storage.get_legislation.return_value = []

        with patch(
            "civicos.CivicOS",
            return_value=_mock_civicos(storage),
        ) as mock_cls, patch("dotenv.load_dotenv"):
            resp = client.get("/legislation/state/parks")

        assert resp.status_code == 200
        assert resp.json()["topic"] == "parks"
        mock_cls.assert_called_once_with("city-san-rafael")

    def test_passes_status_filter(self, client):
        storage = MagicMock()
        storage.get_legislation.return_value = SAMPLE_STATE_BILLS[:1]

        with patch(
            "civicos.CivicOS",
            return_value=_mock_civicos(storage),
        ), patch("dotenv.load_dotenv"):
            resp = client.get("/legislation/state/housing?status=active")

        assert resp.status_code == 200
        storage.get_legislation.assert_called_once_with(
            topic="housing", level="state", limit=50, status="active",
        )
        assert resp.json()["count"] == 1

    def test_respects_limit_parameter(self, client):
        storage = MagicMock()
        storage.get_legislation.return_value = SAMPLE_STATE_BILLS[:1]

        with patch(
            "civicos.CivicOS",
            return_value=_mock_civicos(storage),
        ), patch("dotenv.load_dotenv"):
            resp = client.get("/legislation/state/housing?limit=10")

        assert resp.status_code == 200
        storage.get_legislation.assert_called_once_with(
            topic="housing", level="state", limit=10, status=None,
        )

    def test_import_error_returns_503(self, client):
        with patch(
            "civicos.CivicOS",
            side_effect=ImportError("no module"),
        ), patch("dotenv.load_dotenv", side_effect=ImportError("no module")):
            resp = client.get("/legislation/state/housing")

        assert resp.status_code == 503
        assert "not available" in resp.json()["detail"]

    def test_storage_error_returns_500(self, client):
        storage = MagicMock()
        storage.get_legislation.side_effect = RuntimeError("DB connection lost")

        with patch(
            "civicos.CivicOS",
            return_value=_mock_civicos(storage),
        ), patch("dotenv.load_dotenv"):
            resp = client.get("/legislation/state/housing")

        assert resp.status_code == 500
        assert "DB connection lost" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Federal legislation
# ---------------------------------------------------------------------------

class TestFederalLegislation:
    def test_returns_bills_for_topic(self, client):
        storage = MagicMock()
        storage.get_legislation.return_value = SAMPLE_FEDERAL_BILLS

        with patch(
            "civicos.CivicOS",
            return_value=_mock_civicos(storage),
        ), patch("dotenv.load_dotenv"):
            resp = client.get("/legislation/federal/infrastructure")

        assert resp.status_code == 200
        body = resp.json()
        assert body["topic"] == "infrastructure"
        assert body["level"] == "federal"
        assert body["count"] == 1
        assert body["bills"][0]["number"] == "HR 100"
        assert body["bills"][0]["title"] == "Infrastructure Bill"
        storage.get_legislation.assert_called_once_with(
            topic="infrastructure", level="federal", limit=50, status=None,
        )

    def test_always_uses_san_rafael_for_civicos(self, client):
        """Federal endpoint hardcodes city-san-rafael as CivicOS jurisdiction."""
        storage = MagicMock()
        storage.get_legislation.return_value = []

        with patch(
            "civicos.CivicOS",
            return_value=_mock_civicos(storage),
        ) as mock_cls, patch("dotenv.load_dotenv"):
            resp = client.get("/legislation/federal/defense")

        mock_cls.assert_called_once_with("city-san-rafael")
        assert resp.json()["count"] == 0

    def test_passes_status_and_limit(self, client):
        storage = MagicMock()
        storage.get_legislation.return_value = []

        with patch(
            "civicos.CivicOS",
            return_value=_mock_civicos(storage),
        ), patch("dotenv.load_dotenv"):
            resp = client.get("/legislation/federal/housing?status=introduced&limit=5")

        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 0
        assert body["bills"] == []
        assert body["topic"] == "housing"
        assert body["level"] == "federal"
        storage.get_legislation.assert_called_once_with(
            topic="housing", level="federal", limit=5, status="introduced",
        )

    def test_import_error_returns_503(self, client):
        with patch(
            "civicos.CivicOS",
            side_effect=ImportError("missing"),
        ), patch(
            "dotenv.load_dotenv",
            side_effect=ImportError("missing"),
        ):
            resp = client.get("/legislation/federal/housing")

        assert resp.status_code == 503
        assert "not available" in resp.json()["detail"]

    def test_storage_error_returns_500(self, client):
        storage = MagicMock()
        storage.get_legislation.side_effect = ValueError("bad query")

        with patch(
            "civicos.CivicOS",
            return_value=_mock_civicos(storage),
        ), patch("dotenv.load_dotenv"):
            resp = client.get("/legislation/federal/housing")

        assert resp.status_code == 500
        assert "bad query" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Elections
# ---------------------------------------------------------------------------

class TestGetElections:
    def test_returns_elections_for_jurisdiction(self, client):
        storage = MagicMock()
        storage.get_elections.return_value = SAMPLE_ELECTIONS

        with patch(
            "civicos.CivicOS",
            return_value=_mock_civicos(storage),
        ) as mock_cls, patch("dotenv.load_dotenv"):
            resp = client.get("/elections/city-san-rafael")

        assert resp.status_code == 200
        body = resp.json()
        assert body["jurisdiction_id"] == "city-san-rafael"
        assert body["count"] == 1
        assert body["elections"][0]["name"] == "November 2026 General"
        assert body["elections"][0]["date"] == "2026-11-03"
        mock_cls.assert_called_once_with("city-san-rafael")

    def test_upcoming_only_defaults_true(self, client):
        storage = MagicMock()
        storage.get_elections.return_value = []

        with patch(
            "civicos.CivicOS",
            return_value=_mock_civicos(storage),
        ), patch("dotenv.load_dotenv"):
            resp = client.get("/elections/city-san-rafael")

        assert resp.status_code == 200
        assert resp.json()["count"] == 0
        assert resp.json()["elections"] == []
        storage.get_elections.assert_called_once_with(
            jurisdiction_id="city-san-rafael", upcoming_only=True,
        )

    def test_upcoming_only_false_fetches_all(self, client):
        storage = MagicMock()
        storage.get_elections.return_value = SAMPLE_ELECTIONS

        with patch(
            "civicos.CivicOS",
            return_value=_mock_civicos(storage),
        ), patch("dotenv.load_dotenv"):
            resp = client.get("/elections/city-san-rafael?upcoming_only=false")

        storage.get_elections.assert_called_once_with(
            jurisdiction_id="city-san-rafael", upcoming_only=False,
        )
        assert resp.json()["count"] == 1

    def test_empty_elections_list(self, client):
        storage = MagicMock()
        storage.get_elections.return_value = []

        with patch(
            "civicos.CivicOS",
            return_value=_mock_civicos(storage),
        ), patch("dotenv.load_dotenv"):
            resp = client.get("/elections/city-novato")

        assert resp.status_code == 200
        assert resp.json()["count"] == 0
        assert resp.json()["elections"] == []
        assert resp.json()["jurisdiction_id"] == "city-novato"

    def test_import_error_returns_503(self, client):
        with patch(
            "civicos.CivicOS",
            side_effect=ImportError("missing"),
        ), patch(
            "dotenv.load_dotenv",
            side_effect=ImportError("missing"),
        ):
            resp = client.get("/elections/city-san-rafael")

        assert resp.status_code == 503

    def test_storage_error_returns_500(self, client):
        storage = MagicMock()
        storage.get_elections.side_effect = ConnectionError("timeout")

        with patch(
            "civicos.CivicOS",
            return_value=_mock_civicos(storage),
        ), patch("dotenv.load_dotenv"):
            resp = client.get("/elections/city-san-rafael")

        assert resp.status_code == 500
        assert "timeout" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Election detail
# ---------------------------------------------------------------------------

class TestElectionDetail:
    def test_returns_election_when_found(self, client):
        storage = MagicMock()
        storage.get_election.return_value = SAMPLE_ELECTION_DETAIL

        with patch(
            "civicos.CivicOS",
            return_value=_mock_civicos(storage),
        ), patch("dotenv.load_dotenv"):
            resp = client.get("/elections/detail/elec-2026-nov")

        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == "elec-2026-nov"
        assert body["name"] == "November 2026 General"
        assert body["date"] == "2026-11-03"
        assert body["type"] == "general"
        assert len(body["contests"]) == 1
        storage.get_election.assert_called_once_with("elec-2026-nov")

    def test_returns_404_when_not_found(self, client):
        storage = MagicMock()
        storage.get_election.return_value = None

        with patch(
            "civicos.CivicOS",
            return_value=_mock_civicos(storage),
        ), patch("dotenv.load_dotenv"):
            resp = client.get("/elections/detail/nonexistent-id")

        assert resp.status_code == 404
        assert "nonexistent-id" in resp.json()["detail"]

    def test_returns_404_for_empty_string_result(self, client):
        """Falsy but non-None results should still 404."""
        storage = MagicMock()
        storage.get_election.return_value = {}

        with patch(
            "civicos.CivicOS",
            return_value=_mock_civicos(storage),
        ), patch("dotenv.load_dotenv"):
            resp = client.get("/elections/detail/empty-elec")

        # Empty dict is falsy, so the `not election` check triggers 404
        assert resp.status_code == 404

    def test_import_error_returns_503(self, client):
        with patch(
            "civicos.CivicOS",
            side_effect=ImportError("missing"),
        ), patch(
            "dotenv.load_dotenv",
            side_effect=ImportError("missing"),
        ):
            resp = client.get("/elections/detail/elec-2026-nov")

        assert resp.status_code == 503

    def test_storage_error_returns_500(self, client):
        storage = MagicMock()
        storage.get_election.side_effect = RuntimeError("DB error")

        with patch(
            "civicos.CivicOS",
            return_value=_mock_civicos(storage),
        ), patch("dotenv.load_dotenv"):
            resp = client.get("/elections/detail/elec-2026-nov")

        assert resp.status_code == 500
        assert "DB error" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Election contests
# ---------------------------------------------------------------------------

class TestElectionContests:
    def test_returns_contests_for_election(self, client):
        storage = MagicMock()
        storage.get_election_contests.return_value = SAMPLE_CONTESTS

        with patch(
            "civicos.CivicOS",
            return_value=_mock_civicos(storage),
        ), patch("dotenv.load_dotenv"):
            resp = client.get("/elections/detail/elec-2026-nov/contests")

        assert resp.status_code == 200
        body = resp.json()
        assert body["election_id"] == "elec-2026-nov"
        assert body["count"] == 2
        assert body["contests"][0]["name"] == "City Council District 1"
        assert body["contests"][0]["type"] == "candidate"
        assert body["contests"][1]["name"] == "Measure A"
        assert body["contests"][1]["type"] == "measure"
        storage.get_election_contests.assert_called_once_with("elec-2026-nov")

    def test_empty_contests_list(self, client):
        storage = MagicMock()
        storage.get_election_contests.return_value = []

        with patch(
            "civicos.CivicOS",
            return_value=_mock_civicos(storage),
        ), patch("dotenv.load_dotenv"):
            resp = client.get("/elections/detail/elec-old/contests")

        assert resp.status_code == 200
        assert resp.json()["count"] == 0
        assert resp.json()["contests"] == []
        assert resp.json()["election_id"] == "elec-old"

    def test_import_error_returns_503(self, client):
        with patch(
            "civicos.CivicOS",
            side_effect=ImportError("no"),
        ), patch(
            "dotenv.load_dotenv",
            side_effect=ImportError("no"),
        ):
            resp = client.get("/elections/detail/elec-2026-nov/contests")

        assert resp.status_code == 503

    def test_storage_error_returns_500(self, client):
        storage = MagicMock()
        storage.get_election_contests.side_effect = RuntimeError("broken")

        with patch(
            "civicos.CivicOS",
            return_value=_mock_civicos(storage),
        ), patch("dotenv.load_dotenv"):
            resp = client.get("/elections/detail/elec-2026-nov/contests")

        assert resp.status_code == 500
        assert "broken" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Voting record
# ---------------------------------------------------------------------------

class TestVotingRecord:
    def test_returns_votes_for_official(self, client):
        storage = MagicMock()
        storage.get_voting_record.return_value = SAMPLE_VOTES

        with patch(
            "civicos.CivicOS",
            return_value=_mock_civicos(storage),
        ) as mock_cls, patch("dotenv.load_dotenv"):
            resp = client.get("/voting-record/kate-colin/city-san-rafael")

        assert resp.status_code == 200
        body = resp.json()
        assert body["official"] == "kate-colin"
        assert body["jurisdiction"] == "city-san-rafael"
        assert body["count"] == 2
        assert body["votes"][0]["vote"] == "yes"
        assert body["votes"][0]["bill_title"] == "Housing Density Act"
        assert body["votes"][1]["vote"] == "no"
        assert body["votes"][1]["vote_date"] == "2026-04-01"
        mock_cls.assert_called_once_with("city-san-rafael")

    def test_passes_topic_filter(self, client):
        storage = MagicMock()
        storage.get_voting_record.return_value = SAMPLE_VOTES[:1]

        with patch(
            "civicos.CivicOS",
            return_value=_mock_civicos(storage),
        ), patch("dotenv.load_dotenv"):
            resp = client.get("/voting-record/kate-colin/city-san-rafael?topic=housing")

        storage.get_voting_record.assert_called_once_with(
            official="kate-colin",
            jurisdiction_id="city-san-rafael",
            topic="housing",
        )
        assert resp.json()["count"] == 1

    def test_topic_defaults_to_none(self, client):
        storage = MagicMock()
        storage.get_voting_record.return_value = []

        with patch(
            "civicos.CivicOS",
            return_value=_mock_civicos(storage),
        ), patch("dotenv.load_dotenv"):
            resp = client.get("/voting-record/some-official/city-san-rafael")

        assert resp.status_code == 200
        assert resp.json()["count"] == 0
        storage.get_voting_record.assert_called_once_with(
            official="some-official",
            jurisdiction_id="city-san-rafael",
            topic=None,
        )

    def test_empty_votes_list(self, client):
        storage = MagicMock()
        storage.get_voting_record.return_value = []

        with patch(
            "civicos.CivicOS",
            return_value=_mock_civicos(storage),
        ), patch("dotenv.load_dotenv"):
            resp = client.get("/voting-record/unknown-official/city-novato")

        assert resp.status_code == 200
        assert resp.json()["count"] == 0
        assert resp.json()["votes"] == []

    def test_import_error_returns_503(self, client):
        with patch(
            "civicos.CivicOS",
            side_effect=ImportError("missing"),
        ), patch(
            "dotenv.load_dotenv",
            side_effect=ImportError("missing"),
        ):
            resp = client.get("/voting-record/kate-colin/city-san-rafael")

        assert resp.status_code == 503

    def test_storage_error_returns_500(self, client):
        storage = MagicMock()
        storage.get_voting_record.side_effect = RuntimeError("DB down")

        with patch(
            "civicos.CivicOS",
            return_value=_mock_civicos(storage),
        ), patch("dotenv.load_dotenv"):
            resp = client.get("/voting-record/kate-colin/city-san-rafael")

        assert resp.status_code == 500
        assert "DB down" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Legistar events
# ---------------------------------------------------------------------------

class TestLegistarEvents:
    def test_returns_events_for_city(self, client):
        mock_client = MagicMock()
        mock_client.get_events.return_value = SAMPLE_EVENTS

        with patch(
            "civicos_services.clients.legistar_client.create_client",
            return_value=mock_client,
        ) as mock_create:
            resp = client.get("/legistar/san-rafael/events")

        assert resp.status_code == 200
        body = resp.json()
        assert body["city"] == "san-rafael"
        assert body["source"] == "legistar"
        assert body["count"] == 2
        assert body["events"][0]["name"] == "City Council Meeting"
        assert body["events"][1]["id"] == "evt-2"
        mock_create.assert_called_once_with("san-rafael")
        mock_client.get_events.assert_called_once_with(days=30)

    def test_respects_days_parameter(self, client):
        mock_client = MagicMock()
        mock_client.get_events.return_value = SAMPLE_EVENTS[:1]

        with patch(
            "civicos_services.clients.legistar_client.create_client",
            return_value=mock_client,
        ):
            resp = client.get("/legistar/san-rafael/events?days=7")

        mock_client.get_events.assert_called_once_with(days=7)
        assert resp.json()["count"] == 1

    def test_empty_events_list(self, client):
        mock_client = MagicMock()
        mock_client.get_events.return_value = []

        with patch(
            "civicos_services.clients.legistar_client.create_client",
            return_value=mock_client,
        ):
            resp = client.get("/legistar/small-town/events")

        assert resp.status_code == 200
        assert resp.json()["count"] == 0
        assert resp.json()["events"] == []
        assert resp.json()["city"] == "small-town"

    def test_import_error_returns_503(self, client):
        with patch(
            "civicos_services.clients.legistar_client.create_client",
            side_effect=ImportError("no legistar"),
        ):
            resp = client.get("/legistar/san-rafael/events")

        assert resp.status_code == 503
        assert "not available" in resp.json()["detail"]

    def test_client_error_returns_400(self, client):
        mock_client = MagicMock()
        mock_client.get_events.side_effect = ValueError("invalid city slug")

        with patch(
            "civicos_services.clients.legistar_client.create_client",
            return_value=mock_client,
        ):
            resp = client.get("/legistar/bad-city/events")

        assert resp.status_code == 400
        assert "bad-city" in resp.json()["detail"]
        assert "invalid city slug" in resp.json()["detail"]

    def test_days_default_is_30(self, client):
        mock_client = MagicMock()
        mock_client.get_events.return_value = []

        with patch(
            "civicos_services.clients.legistar_client.create_client",
            return_value=mock_client,
        ):
            resp = client.get("/legistar/san-rafael/events")

        assert resp.status_code == 200
        assert resp.json()["count"] == 0
        mock_client.get_events.assert_called_once_with(days=30)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class TestPydanticModels:
    """Verify model schemas enforce expected fields and defaults."""

    def test_bill_required_fields(self):
        from civicos_services.servers.routers.legislative import Bill
        bill = Bill(id="b1", number="AB 100", title="Test Bill")
        assert bill.id == "b1"
        assert bill.number == "AB 100"
        assert bill.title == "Test Bill"
        assert bill.status is None
        assert bill.sponsor is None
        assert bill.url is None

    def test_bill_all_fields(self):
        from civicos_services.servers.routers.legislative import Bill
        bill = Bill(
            id="b1", number="AB 100", title="Test Bill",
            status="active", sponsor="Sen. Jones", chamber="senate",
            last_action="Passed committee", last_action_date="2026-03-01",
            url="https://example.com/ab100",
        )
        assert bill.status == "active"
        assert bill.sponsor == "Sen. Jones"
        assert bill.chamber == "senate"
        assert bill.last_action == "Passed committee"
        assert bill.url == "https://example.com/ab100"

    def test_election_required_fields(self):
        from civicos_services.servers.routers.legislative import Election
        e = Election(
            id="e1", name="Primary", date="2026-06-01",
            type="primary", jurisdiction_id="city-sr",
        )
        assert e.type == "primary"
        assert e.jurisdiction_id == "city-sr"
        assert e.status is None

    def test_contest_required_fields(self):
        from civicos_services.servers.routers.legislative import Contest
        c = Contest(id="c1", election_id="e1", name="Mayor", type="candidate")
        assert c.election_id == "e1"
        assert c.candidates is None
        assert c.description is None

    def test_contest_with_candidates(self):
        from civicos_services.servers.routers.legislative import Contest
        c = Contest(
            id="c1", election_id="e1", name="Mayor", type="candidate",
            candidates=[{"name": "Alice", "party": "D"}, {"name": "Bob", "party": "R"}],
        )
        assert len(c.candidates) == 2
        assert c.candidates[0]["name"] == "Alice"
        assert c.candidates[1]["party"] == "R"

    def test_vote_record_fields(self):
        from civicos_services.servers.routers.legislative import VoteRecord
        v = VoteRecord(
            bill_id="b1", bill_title="Housing Act",
            vote="yes", vote_date="2026-03-15",
        )
        assert v.vote == "yes"
        assert v.bill_title == "Housing Act"
        assert v.vote_date == "2026-03-15"


# ---------------------------------------------------------------------------
# Auth enforcement
# ---------------------------------------------------------------------------

class TestAuthEnforcement:
    """Verify endpoints require authentication."""

    def test_state_legislation_requires_auth(self, app):
        """Without auth override, endpoints should reject unauthenticated requests."""
        with TestClient(app) as c:
            resp = c.get("/legislation/state/housing")
        assert resp.status_code == 401

    def test_federal_legislation_requires_auth(self, app):
        with TestClient(app) as c:
            resp = c.get("/legislation/federal/housing")
        assert resp.status_code == 401

    def test_elections_requires_auth(self, app):
        with TestClient(app) as c:
            resp = c.get("/elections/city-san-rafael")
        assert resp.status_code == 401

    def test_election_detail_requires_auth(self, app):
        with TestClient(app) as c:
            resp = c.get("/elections/detail/elec-1")
        assert resp.status_code == 401

    def test_election_contests_requires_auth(self, app):
        with TestClient(app) as c:
            resp = c.get("/elections/detail/elec-1/contests")
        assert resp.status_code == 401

    def test_voting_record_requires_auth(self, app):
        with TestClient(app) as c:
            resp = c.get("/voting-record/kate-colin/city-san-rafael")
        assert resp.status_code == 401

    def test_legistar_events_requires_auth(self, app):
        with TestClient(app) as c:
            resp = c.get("/legistar/san-rafael/events")
        assert resp.status_code == 401
