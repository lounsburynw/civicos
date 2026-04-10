"""
Tests for CaliforniaLegislatureClient — bulk data parser for CA legislature.

Tests focus on real parsing logic (tab-delimited .dat files, normalization,
datetime parsing) with actual temp files. HTTP/R2 downloads are mocked at
the I/O boundary only.
"""

import io
import zipfile
from pathlib import Path

import pytest

from civicos_extraction.clients.california_legislature import (
    CAAgenda,
    CABill,
    CADetailVote,
    CAHearing,
    CAHistoryAction,
    CAVoteSummary,
    CaliforniaLegislatureClient,
    MEASURE_TYPES,
    STATUS_MAP,
)


# ============================================================================
# Helpers
# ============================================================================


def write_dat(path: Path, rows: list[list[str]]) -> Path:
    """Write tab-delimited .dat file with backtick-enclosed fields."""
    with open(path, "w") as f:
        for row in rows:
            f.write("\t".join(f"`{field}`" for field in row) + "\n")
    return path


def make_zip(table_files: dict[str, list[list[str]]]) -> bytes:
    """Create an in-memory ZIP containing .dat table files."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for table_name, rows in table_files.items():
            content = ""
            for row in rows:
                content += "\t".join(f"`{field}`" for field in row) + "\n"
            zf.writestr(f"{table_name}.dat", content)
    return buf.getvalue()


# ============================================================================
# CABill Property Tests
# ============================================================================


class TestCABillProperties:
    """Tests for CABill computed properties."""

    def test_bill_number_formats_type_and_num(self):
        bill = CABill(
            bill_id="202520260AB123",
            session_year="2025-2026",
            measure_type="AB",
            measure_num=123,
            status="Introduced",
        )
        assert bill.bill_number == "AB 123"

    def test_bill_number_senate_bill(self):
        bill = CABill(
            bill_id="202520260SB45",
            session_year="2025-2026",
            measure_type="SB",
            measure_num=45,
            status="Introduced",
        )
        assert bill.bill_number == "SB 45"

    def test_session_num_regular_session(self):
        bill = CABill(
            bill_id="202520260AB123",
            session_year="2025-2026",
            measure_type="AB",
            measure_num=123,
            status="Introduced",
        )
        assert bill.session_num == "0"

    def test_session_num_extraordinary_session(self):
        bill = CABill(
            bill_id="202520261AB5",
            session_year="2025-2026",
            measure_type="AB",
            measure_num=5,
            status="Introduced",
        )
        assert bill.session_num == "1"

    def test_session_num_short_id_returns_zero(self):
        bill = CABill(
            bill_id="SHORT",
            session_year="2025-2026",
            measure_type="AB",
            measure_num=1,
            status="Introduced",
        )
        assert bill.session_num == "0"

    def test_normalized_bill_id_regular_session(self):
        bill = CABill(
            bill_id="202520260AB123",
            session_year="2025-2026",
            measure_type="AB",
            measure_num=123,
            status="Introduced",
        )
        assert bill.normalized_bill_id == "ca-ab123"

    def test_normalized_bill_id_extraordinary_session(self):
        bill = CABill(
            bill_id="202520261SB7",
            session_year="2025-2026",
            measure_type="SB",
            measure_num=7,
            status="Introduced",
        )
        assert bill.normalized_bill_id == "ca-sb7-x1"

    def test_official_url_construction(self):
        bill = CABill(
            bill_id="202520260AB123",
            session_year="2025-2026",
            measure_type="AB",
            measure_num=123,
            status="Introduced",
        )
        expected = (
            "https://leginfo.legislature.ca.gov/faces/billNavClient.xhtml"
            "?bill_id=202520260AB123"
        )
        assert bill.official_url == expected

    def test_official_url_senate_bill(self):
        bill = CABill(
            bill_id="202320240SB999",
            session_year="2023-2024",
            measure_type="SB",
            measure_num=999,
            status="Chaptered",
        )
        assert "bill_id=202320240SB999" in bill.official_url


# ============================================================================
# Datetime Parsing
# ============================================================================


class TestParseDatetime:
    """Tests for _parse_datetime method."""

    @pytest.fixture
    def client(self):
        return CaliforniaLegislatureClient()

    def test_standard_datetime_format(self, client):
        assert client._parse_datetime("2026-03-15 10:30:00") == "2026-03-15"

    def test_datetime_with_microseconds(self, client):
        assert client._parse_datetime("2026-03-15 10:30:00.123456") == "2026-03-15"

    def test_us_12hr_format(self, client):
        assert client._parse_datetime("03/15/2026 10:30:00 AM") == "2026-03-15"

    def test_date_only_format(self, client):
        assert client._parse_datetime("2026-03-15") == "2026-03-15"

    def test_empty_string_returns_none(self, client):
        assert client._parse_datetime("") is None

    def test_whitespace_only_returns_none(self, client):
        assert client._parse_datetime("   ") is None

    def test_unrecognized_format_returns_none(self, client):
        assert client._parse_datetime("March 15th, 2026") is None

    def test_none_input_returns_none(self, client):
        assert client._parse_datetime(None) is None


# ============================================================================
# Session Archive Naming
# ============================================================================


class TestSessionArchiveName:
    """Tests for _session_archive_name method."""

    @pytest.fixture
    def client(self):
        return CaliforniaLegislatureClient()

    def test_standard_session(self, client):
        assert client._session_archive_name("2025-2026") == "pubinfo_2025.zip"

    def test_earlier_session(self, client):
        assert client._session_archive_name("2023-2024") == "pubinfo_2023.zip"


# ============================================================================
# Format Session
# ============================================================================


class TestFormatSession:
    """Tests for _format_session method."""

    @pytest.fixture
    def client(self):
        return CaliforniaLegislatureClient()

    def test_eight_digit_session(self, client):
        assert client._format_session("20252026") == "2025-2026"

    def test_already_formatted_passthrough(self, client):
        assert client._format_session("2025-2026") == "2025-2026"

    def test_whitespace_stripped(self, client):
        assert client._format_session("  20252026  ") == "2025-2026"

    def test_short_string_passthrough(self, client):
        assert client._format_session("2025") == "2025"


# ============================================================================
# Parse .dat File
# ============================================================================


class TestParseDatFile:
    """Tests for _parse_dat_file tab-delimited parsing."""

    @pytest.fixture
    def client(self):
        return CaliforniaLegislatureClient()

    def test_backtick_stripping(self, client, tmp_path):
        dat = write_dat(tmp_path / "test.dat", [["field1", "field2", "field3"]])
        rows = list(client._parse_dat_file(dat))
        assert len(rows) == 1
        assert rows[0] == ["field1", "field2", "field3"]

    def test_multiple_rows(self, client, tmp_path):
        dat = write_dat(tmp_path / "test.dat", [["a", "b"], ["c", "d"]])
        rows = list(client._parse_dat_file(dat))
        assert len(rows) == 2
        assert rows[0] == ["a", "b"]
        assert rows[1] == ["c", "d"]

    def test_empty_file(self, client, tmp_path):
        dat = tmp_path / "empty.dat"
        dat.write_text("")
        rows = list(client._parse_dat_file(dat))
        assert rows == []


# ============================================================================
# Location Codes
# ============================================================================


class TestLoadLocationCodes:
    """Tests for _load_location_codes parsing."""

    @pytest.fixture
    def client(self):
        return CaliforniaLegislatureClient()

    def test_loads_codes_from_dat(self, client, tmp_path):
        # Schema: session_year, location_code, location_type, consent_calendar_code,
        #         description, long_description
        rows = [
            ["20252026", "CX08", "Committee", "", "Housing", "Housing and Community Development"],
            ["20252026", "DESK", "Floor", "", "Desk", ""],
        ]
        dat = write_dat(tmp_path / "LOCATION_CODE_TBL.dat", rows)
        tables = {"LOCATION_CODE_TBL": dat}
        codes = client._load_location_codes(tables)
        assert codes["CX08"] == "Housing and Community Development"
        # Falls back to short description when long_description is empty
        assert codes["DESK"] == "Desk"

    def test_missing_table_returns_empty(self, client):
        codes = client._load_location_codes({})
        assert codes == {}

    def test_skips_short_rows(self, client, tmp_path):
        rows = [["too", "few"]]  # Less than 6 fields
        dat = write_dat(tmp_path / "LOCATION_CODE_TBL.dat", rows)
        tables = {"LOCATION_CODE_TBL": dat}
        codes = client._load_location_codes(tables)
        assert codes == {}


# ============================================================================
# Parse Bills
# ============================================================================


class TestParseBills:
    """Tests for parse_bills from BILL_TBL."""

    @pytest.fixture
    def client(self):
        return CaliforniaLegislatureClient()

    def _make_bill_row(
        self,
        bill_id="202520260AB100",
        session="20252026",
        session_num="0",
        measure_type="AB",
        measure_num="100",
        status="Introduced",
        chapter_year="",
        chapter_type="",
        chapter_session_num="",
        chapter_num="",
        latest_version_id="202520260AB1001INT",
        active="Y",
        trans_uid="",
        trans_update="",
        current_location="DESK",
        current_secondary_loc="",
        current_house="Assembly",
    ):
        return [
            bill_id, session, session_num, measure_type, measure_num,
            status, chapter_year, chapter_type, chapter_session_num,
            chapter_num, latest_version_id, active, trans_uid, trans_update,
            current_location, current_secondary_loc, current_house,
        ]

    def test_parses_single_bill(self, client, tmp_path):
        rows = [self._make_bill_row()]
        dat = write_dat(tmp_path / "BILL_TBL.dat", rows)
        bills = client.parse_bills({"BILL_TBL": dat})

        assert len(bills) == 1
        bill = bills[0]
        assert bill.bill_id == "202520260AB100"
        assert bill.session_year == "2025-2026"
        assert bill.measure_type == "AB"
        assert bill.measure_num == 100
        assert bill.status == "Introduced"
        assert bill.current_location == "DESK"
        assert bill.current_house == "Assembly"
        assert bill.active is True

    def test_inactive_bill(self, client, tmp_path):
        rows = [self._make_bill_row(active="N")]
        dat = write_dat(tmp_path / "BILL_TBL.dat", rows)
        bills = client.parse_bills({"BILL_TBL": dat})
        assert bills[0].active is False

    def test_skips_non_numeric_measure_num(self, client, tmp_path):
        rows = [self._make_bill_row(measure_num="XYZ")]
        dat = write_dat(tmp_path / "BILL_TBL.dat", rows)
        bills = client.parse_bills({"BILL_TBL": dat})
        assert len(bills) == 0

    def test_skips_short_rows(self, client, tmp_path):
        dat = write_dat(tmp_path / "BILL_TBL.dat", [["too", "few", "fields"]])
        bills = client.parse_bills({"BILL_TBL": dat})
        assert len(bills) == 0

    def test_missing_table_returns_empty(self, client):
        bills = client.parse_bills({})
        assert bills == []

    def test_multiple_bills(self, client, tmp_path):
        rows = [
            self._make_bill_row(bill_id="202520260AB100", measure_num="100"),
            self._make_bill_row(bill_id="202520260SB200", measure_type="SB", measure_num="200"),
        ]
        dat = write_dat(tmp_path / "BILL_TBL.dat", rows)
        bills = client.parse_bills({"BILL_TBL": dat})
        assert len(bills) == 2
        assert bills[0].measure_type == "AB"
        assert bills[1].measure_type == "SB"
        assert bills[1].measure_num == 200


# ============================================================================
# Enrich Bills With Versions
# ============================================================================


class TestEnrichBillsWithVersions:
    """Tests for enrich_bills_with_versions from BILL_VERSION_TBL."""

    @pytest.fixture
    def client(self):
        return CaliforniaLegislatureClient()

    def _make_version_row(
        self,
        version_id="202520260AB1001INT",
        bill_id="202520260AB100",
        version_num="1",
        action_date="2026-01-10 00:00:00",
        action="Introduced",
        request_num="",
        subject="Housing affordability",
        vote_required="Majority",
        appropriation="NO",
        fiscal_committee="YES",
        local_program="NO",
        substantive_changes="NO",
        urgency="NO",
        taxlevy="NO",
        bill_xml="",
    ):
        return [
            version_id, bill_id, version_num, action_date, action,
            request_num, subject, vote_required, appropriation,
            fiscal_committee, local_program, substantive_changes,
            urgency, taxlevy, bill_xml,
        ]

    def test_enriches_subject_and_flags(self, client, tmp_path):
        bill = CABill(
            bill_id="202520260AB100",
            session_year="2025-2026",
            measure_type="AB",
            measure_num=100,
            status="Introduced",
            latest_version_id="202520260AB1001INT",
        )
        rows = [self._make_version_row()]
        dat = write_dat(tmp_path / "BILL_VERSION_TBL.dat", rows)
        client.enrich_bills_with_versions([bill], {"BILL_VERSION_TBL": dat})

        assert bill.subject == "Housing affordability"
        assert bill.title == "Housing affordability"
        assert bill.vote_required == "Majority"
        assert bill.fiscal_committee is True
        assert bill.appropriation is False
        assert bill.urgency is False

    def test_appropriation_yes(self, client, tmp_path):
        bill = CABill(
            bill_id="202520260AB100",
            session_year="2025-2026",
            measure_type="AB",
            measure_num=100,
            status="Introduced",
            latest_version_id="202520260AB1001INT",
        )
        rows = [self._make_version_row(appropriation="YES", urgency="YES")]
        dat = write_dat(tmp_path / "BILL_VERSION_TBL.dat", rows)
        client.enrich_bills_with_versions([bill], {"BILL_VERSION_TBL": dat})

        assert bill.appropriation is True
        assert bill.urgency is True

    def test_missing_table_does_nothing(self, client):
        bill = CABill(
            bill_id="202520260AB100",
            session_year="2025-2026",
            measure_type="AB",
            measure_num=100,
            status="Introduced",
        )
        client.enrich_bills_with_versions([bill], {})
        assert bill.subject == ""

    def test_include_text_extracts_xml_content(self, client, tmp_path):
        bill = CABill(
            bill_id="202520260AB100",
            session_year="2025-2026",
            measure_type="AB",
            measure_num=100,
            status="Introduced",
            latest_version_id="202520260AB1001INT",
        )
        xml = "<p>Section 1.</p><p>The Legislature finds.</p>"
        rows = [self._make_version_row(bill_xml=xml)]
        dat = write_dat(tmp_path / "BILL_VERSION_TBL.dat", rows)
        client.enrich_bills_with_versions([bill], {"BILL_VERSION_TBL": dat}, include_text=True)

        assert "Section 1." in bill.full_text
        assert "Legislature finds" in bill.full_text
        assert "<p>" not in bill.full_text  # Tags stripped


# ============================================================================
# Enrich Bills With Authors
# ============================================================================


class TestEnrichBillsWithAuthors:
    """Tests for enrich_bills_with_authors from BILL_VERSION_AUTHORS_TBL."""

    @pytest.fixture
    def client(self):
        return CaliforniaLegislatureClient()

    def test_primary_author_first(self, client, tmp_path):
        bill = CABill(
            bill_id="202520260AB100",
            session_year="2025-2026",
            measure_type="AB",
            measure_num=100,
            status="Introduced",
            latest_version_id="202520260AB1001INT",
        )
        # Schema: bill_version_id, type, house, name, contribution,
        #         active_flg, primary_author_flg, trans_uid, trans_update
        rows = [
            ["202520260AB1001INT", "LEAD_AUTHOR", "A", "Smith", "LEAD_AUTHOR", "Y", "Y", "", ""],
            ["202520260AB1001INT", "COAUTHOR", "A", "Jones", "COAUTHOR", "Y", "N", "", ""],
        ]
        dat = write_dat(tmp_path / "BILL_VERSION_AUTHORS_TBL.dat", rows)
        client.enrich_bills_with_authors([bill], {"BILL_VERSION_AUTHORS_TBL": dat})

        assert bill.authors[0] == "Smith"
        assert "Jones" in bill.authors
        assert len(bill.authors) == 2

    def test_missing_table_does_nothing(self, client):
        bill = CABill(
            bill_id="202520260AB100",
            session_year="2025-2026",
            measure_type="AB",
            measure_num=100,
            status="Introduced",
        )
        client.enrich_bills_with_authors([bill], {})
        assert bill.authors == []

    def test_skips_empty_names(self, client, tmp_path):
        bill = CABill(
            bill_id="202520260AB100",
            session_year="2025-2026",
            measure_type="AB",
            measure_num=100,
            status="Introduced",
            latest_version_id="202520260AB1001INT",
        )
        rows = [
            ["202520260AB1001INT", "LEAD_AUTHOR", "A", "", "LEAD_AUTHOR", "Y", "Y", "", ""],
            ["202520260AB1001INT", "COAUTHOR", "A", "Jones", "COAUTHOR", "Y", "N", "", ""],
        ]
        dat = write_dat(tmp_path / "BILL_VERSION_AUTHORS_TBL.dat", rows)
        client.enrich_bills_with_authors([bill], {"BILL_VERSION_AUTHORS_TBL": dat})

        assert bill.authors == ["Jones"]


# ============================================================================
# Parse History
# ============================================================================


class TestParseHistory:
    """Tests for parse_history from BILL_HISTORY_TBL."""

    @pytest.fixture
    def client(self):
        return CaliforniaLegislatureClient()

    def test_parses_action(self, client, tmp_path):
        # Schema: bill_id, history_id, action_date, action, trans_uid,
        #         trans_update, seq, action_code, action_status, primary_loc, ...
        rows = [[
            "202520260AB100", "1", "2026-01-15 00:00:00",
            "Introduced and read first time.", "", "", "1",
            "1000", "I", "DESK", "", "", "",
        ]]
        dat = write_dat(tmp_path / "BILL_HISTORY_TBL.dat", rows)
        actions = client.parse_history({"BILL_HISTORY_TBL": dat})

        assert len(actions) == 1
        assert actions[0].bill_id == "202520260AB100"
        assert actions[0].action_date == "2026-01-15"
        assert actions[0].action == "Introduced and read first time."
        assert actions[0].action_code == "1000"
        assert actions[0].action_status == "I"
        assert actions[0].primary_location == "DESK"

    def test_skips_empty_action_text(self, client, tmp_path):
        rows = [["202520260AB100", "1", "2026-01-15 00:00:00", ""]]
        dat = write_dat(tmp_path / "BILL_HISTORY_TBL.dat", rows)
        actions = client.parse_history({"BILL_HISTORY_TBL": dat})
        assert len(actions) == 0

    def test_skips_empty_bill_id(self, client, tmp_path):
        rows = [["", "1", "2026-01-15 00:00:00", "Some action"]]
        dat = write_dat(tmp_path / "BILL_HISTORY_TBL.dat", rows)
        actions = client.parse_history({"BILL_HISTORY_TBL": dat})
        assert len(actions) == 0

    def test_missing_table_returns_empty(self, client):
        assert client.parse_history({}) == []


# ============================================================================
# Parse Vote Summaries
# ============================================================================


class TestParseVoteSummaries:
    """Tests for parse_vote_summaries from BILL_SUMMARY_VOTE_TBL."""

    @pytest.fixture
    def client(self):
        return CaliforniaLegislatureClient()

    def test_parses_vote_tally(self, client, tmp_path):
        # Schema: bill_id, location_code, vote_datetime, vote_date_seq,
        #         motion_id, ayes, noes, abstain, result, ...
        rows = [[
            "202520260AB100", "AF", "2026-03-20 14:30:00", "1",
            "42", "30", "8", "2", "(PASS)", "", "", "", "", "", "",
        ]]
        dat = write_dat(tmp_path / "BILL_SUMMARY_VOTE_TBL.dat", rows)
        votes = client.parse_vote_summaries({"BILL_SUMMARY_VOTE_TBL": dat})

        assert len(votes) == 1
        v = votes[0]
        assert v.bill_id == "202520260AB100"
        assert v.location_code == "AF"
        assert v.vote_datetime == "2026-03-20"
        assert v.ayes == 30
        assert v.noes == 8
        assert v.abstain == 2
        assert v.result == "(PASS)"
        assert v.motion_id == 42

    def test_empty_vote_counts_default_to_zero(self, client, tmp_path):
        rows = [[
            "202520260AB100", "AF", "2026-03-20 14:30:00", "1",
            "", "", "", "", "FAIL", "", "", "", "", "", "",
        ]]
        dat = write_dat(tmp_path / "BILL_SUMMARY_VOTE_TBL.dat", rows)
        votes = client.parse_vote_summaries({"BILL_SUMMARY_VOTE_TBL": dat})

        assert votes[0].ayes == 0
        assert votes[0].noes == 0
        assert votes[0].abstain == 0
        assert votes[0].motion_id == 0

    def test_skips_invalid_vote_counts(self, client, tmp_path):
        rows = [[
            "202520260AB100", "AF", "2026-03-20 14:30:00", "1",
            "1", "not_a_number", "8", "2", "PASS", "", "", "", "", "", "",
        ]]
        dat = write_dat(tmp_path / "BILL_SUMMARY_VOTE_TBL.dat", rows)
        votes = client.parse_vote_summaries({"BILL_SUMMARY_VOTE_TBL": dat})
        assert len(votes) == 0

    def test_skips_empty_bill_id(self, client, tmp_path):
        rows = [["", "AF", "2026-03-20 14:30:00", "1", "1", "30", "8", "2", "PASS"]]
        dat = write_dat(tmp_path / "BILL_SUMMARY_VOTE_TBL.dat", rows)
        votes = client.parse_vote_summaries({"BILL_SUMMARY_VOTE_TBL": dat})
        assert len(votes) == 0

    def test_missing_table_returns_empty(self, client):
        assert client.parse_vote_summaries({}) == []


# ============================================================================
# Parse Detail Votes
# ============================================================================


class TestParseDetailVotes:
    """Tests for parse_detail_votes from BILL_DETAIL_VOTE_TBL."""

    @pytest.fixture
    def client(self):
        return CaliforniaLegislatureClient()

    def test_parses_legislator_vote(self, client, tmp_path):
        # Schema: bill_id, location_code, legislator_name, vote_datetime,
        #         vote_date_seq, vote_code, motion_id, ...
        rows = [[
            "202520260AB100", "AF", "Wiener", "2026-03-20 14:30:00",
            "1", "AYE", "42", "", "", "", "", "",
        ]]
        dat = write_dat(tmp_path / "BILL_DETAIL_VOTE_TBL.dat", rows)
        votes = client.parse_detail_votes({"BILL_DETAIL_VOTE_TBL": dat})

        assert len(votes) == 1
        v = votes[0]
        assert v.bill_id == "202520260AB100"
        assert v.legislator_name == "Wiener"
        assert v.vote_code == "AYE"
        assert v.vote_datetime == "2026-03-20"
        assert v.location_code == "AF"
        assert v.motion_id == 42

    def test_skips_empty_legislator(self, client, tmp_path):
        rows = [["202520260AB100", "AF", "", "2026-03-20 14:30:00", "1", "AYE"]]
        dat = write_dat(tmp_path / "BILL_DETAIL_VOTE_TBL.dat", rows)
        votes = client.parse_detail_votes({"BILL_DETAIL_VOTE_TBL": dat})
        assert len(votes) == 0

    def test_invalid_motion_id_defaults_to_zero(self, client, tmp_path):
        rows = [[
            "202520260AB100", "AF", "Wiener", "2026-03-20 14:30:00",
            "1", "NOE", "bad_id", "", "",
        ]]
        dat = write_dat(tmp_path / "BILL_DETAIL_VOTE_TBL.dat", rows)
        votes = client.parse_detail_votes({"BILL_DETAIL_VOTE_TBL": dat})
        assert votes[0].motion_id == 0

    def test_missing_table_returns_empty(self, client):
        assert client.parse_detail_votes({}) == []


# ============================================================================
# Parse Hearings
# ============================================================================


class TestParseHearings:
    """Tests for parse_hearings from COMMITTEE_HEARING_TBL."""

    @pytest.fixture
    def client(self):
        return CaliforniaLegislatureClient()

    def test_parses_hearing(self, client, tmp_path):
        # Schema: bill_id, committee_type, committee_nr, hearing_date,
        #         location_code, trans_uid, trans_update
        rows = [[
            "202520260AB100", "Assembly", "8", "2026-02-10 00:00:00",
            "CX08", "", "",
        ]]
        dat = write_dat(tmp_path / "COMMITTEE_HEARING_TBL.dat", rows)
        hearings = client.parse_hearings({"COMMITTEE_HEARING_TBL": dat})

        assert len(hearings) == 1
        h = hearings[0]
        assert h.bill_id == "202520260AB100"
        assert h.committee_type == "Assembly"
        assert h.committee_nr == 8
        assert h.hearing_date == "2026-02-10"
        assert h.location_code == "CX08"

    def test_empty_committee_nr_defaults_to_zero(self, client, tmp_path):
        rows = [["202520260AB100", "Senate", "", "2026-02-10 00:00:00", "SF"]]
        dat = write_dat(tmp_path / "COMMITTEE_HEARING_TBL.dat", rows)
        hearings = client.parse_hearings({"COMMITTEE_HEARING_TBL": dat})
        assert hearings[0].committee_nr == 0

    def test_skips_empty_bill_id(self, client, tmp_path):
        rows = [["", "Assembly", "8", "2026-02-10 00:00:00", "CX08"]]
        dat = write_dat(tmp_path / "COMMITTEE_HEARING_TBL.dat", rows)
        hearings = client.parse_hearings({"COMMITTEE_HEARING_TBL": dat})
        assert len(hearings) == 0

    def test_missing_table_returns_empty(self, client):
        assert client.parse_hearings({}) == []


# ============================================================================
# Parse Agendas
# ============================================================================


class TestParseAgendas:
    """Tests for parse_agendas from COMMITTEE_AGENDA_TBL."""

    @pytest.fixture
    def client(self):
        return CaliforniaLegislatureClient()

    def test_parses_agenda_with_location(self, client, tmp_path):
        # Schema: committee_code, committee_desc, agenda_date, agenda_time,
        #         line1, line2, line3, building_type, room_num
        rows = [[
            "CX08", "Housing and Community Development",
            "2026-03-15 00:00:00", "1:30 PM",
            "", "", "", "State Capitol", "Room 437",
        ]]
        dat = write_dat(tmp_path / "COMMITTEE_AGENDA_TBL.dat", rows)
        agendas = client.parse_agendas({"COMMITTEE_AGENDA_TBL": dat})

        assert len(agendas) == 1
        a = agendas[0]
        assert a.committee_code == "CX08"
        assert a.committee_desc == "Housing and Community Development"
        assert a.agenda_date == "2026-03-15"
        assert a.agenda_time == "1:30 PM"
        assert a.location == "State Capitol Room 437"

    def test_empty_location_fields(self, client, tmp_path):
        rows = [["CX08", "Housing", "2026-03-15 00:00:00", "1:30 PM"]]
        dat = write_dat(tmp_path / "COMMITTEE_AGENDA_TBL.dat", rows)
        agendas = client.parse_agendas({"COMMITTEE_AGENDA_TBL": dat})
        assert agendas[0].location == ""

    def test_skips_empty_committee_code(self, client, tmp_path):
        rows = [["", "Housing", "2026-03-15 00:00:00", "1:30 PM"]]
        dat = write_dat(tmp_path / "COMMITTEE_AGENDA_TBL.dat", rows)
        agendas = client.parse_agendas({"COMMITTEE_AGENDA_TBL": dat})
        assert len(agendas) == 0

    def test_missing_table_returns_empty(self, client):
        assert client.parse_agendas({}) == []


# ============================================================================
# Normalize Bill For Storage
# ============================================================================


class TestNormalizeBillForStorage:
    """Tests for normalize_bill_for_storage mapping."""

    @pytest.fixture
    def client(self):
        return CaliforniaLegislatureClient()

    def test_basic_normalization(self, client):
        bill = CABill(
            bill_id="202520260AB100",
            session_year="2025-2026",
            measure_type="AB",
            measure_num=100,
            status="Introduced",
            subject="Housing affordability",
            current_location="DESK",
            current_house="Assembly",
        )
        result = client.normalize_bill_for_storage(bill)

        assert result["bill_id"] == "ca-ab100"
        assert result["bill_number"] == "AB 100"
        assert result["bill_name"] == "Housing affordability"
        assert result["status"] == "Introduced"
        assert result["summary"] == "Housing affordability"
        assert result["jurisdiction_id"] == "state-california"
        assert "leginfo.legislature.ca.gov" in result["official_url"]
        assert result["enacted_date"] is None
        assert result["metadata"]["measure_type"] == "AB"
        assert result["metadata"]["measure_type_label"] == "Assembly Bill"
        assert result["metadata"]["session"] == "2025-2026"
        assert result["metadata"]["source"] == "leginfo_bulk"

    def test_chaptered_bill_has_enacted_date(self, client):
        bill = CABill(
            bill_id="202520260SB50",
            session_year="2025-2026",
            measure_type="SB",
            measure_num=50,
            status="Chaptered",
            chapter_year="2026",
            chapter_num="142",
        )
        result = client.normalize_bill_for_storage(bill)
        assert result["status"] == "Chaptered"
        assert result["enacted_date"] == "2026-01-01"

    def test_null_chapter_year_no_enacted_date(self, client):
        bill = CABill(
            bill_id="202520260AB100",
            session_year="2025-2026",
            measure_type="AB",
            measure_num=100,
            status="Introduced",
            chapter_year="NULL",
            chapter_num="",
        )
        result = client.normalize_bill_for_storage(bill)
        assert result["enacted_date"] is None

    def test_status_mapping_engrossed(self, client):
        bill = CABill(
            bill_id="202520260AB100",
            session_year="2025-2026",
            measure_type="AB",
            measure_num=100,
            status="Engrossed",
        )
        result = client.normalize_bill_for_storage(bill)
        assert result["status"] == "Passed House"

    def test_status_mapping_vetoed(self, client):
        bill = CABill(
            bill_id="202520260AB100",
            session_year="2025-2026",
            measure_type="AB",
            measure_num=100,
            status="Vetoed",
        )
        result = client.normalize_bill_for_storage(bill)
        assert result["status"] == "Vetoed"

    def test_unknown_status_passes_through(self, client):
        bill = CABill(
            bill_id="202520260AB100",
            session_year="2025-2026",
            measure_type="AB",
            measure_num=100,
            status="In Committee",
        )
        result = client.normalize_bill_for_storage(bill)
        assert result["status"] == "In Committee"

    def test_bill_name_fallback_to_bill_number(self, client):
        bill = CABill(
            bill_id="202520260AB100",
            session_year="2025-2026",
            measure_type="AB",
            measure_num=100,
            status="Introduced",
        )
        result = client.normalize_bill_for_storage(bill)
        assert result["bill_name"] == "AB 100"

    def test_location_code_resolution(self, client):
        client._location_codes = {"DESK": "Assembly Desk"}
        bill = CABill(
            bill_id="202520260AB100",
            session_year="2025-2026",
            measure_type="AB",
            measure_num=100,
            status="Introduced",
            current_location="DESK",
        )
        result = client.normalize_bill_for_storage(bill)
        assert result["metadata"]["current_location_name"] == "Assembly Desk"

    def test_full_text_included_when_present(self, client):
        bill = CABill(
            bill_id="202520260AB100",
            session_year="2025-2026",
            measure_type="AB",
            measure_num=100,
            status="Introduced",
            full_text="The people of the State of California do enact as follows:",
        )
        result = client.normalize_bill_for_storage(bill)
        assert result["full_text"] == "The people of the State of California do enact as follows:"

    def test_empty_full_text_is_none(self, client):
        bill = CABill(
            bill_id="202520260AB100",
            session_year="2025-2026",
            measure_type="AB",
            measure_num=100,
            status="Introduced",
            full_text="",
        )
        result = client.normalize_bill_for_storage(bill)
        assert result["full_text"] is None


# ============================================================================
# Normalize Hearing/Vote/History for Storage
# ============================================================================


class TestNormalizeHearingForStorage:
    """Tests for normalize_hearing_for_storage."""

    @pytest.fixture
    def client(self):
        c = CaliforniaLegislatureClient()
        c._location_codes = {"CX08": "Housing and Community Development"}
        return c

    def test_hearing_with_known_bill(self, client):
        bill = CABill(
            bill_id="202520260AB100",
            session_year="2025-2026",
            measure_type="AB",
            measure_num=100,
            status="Introduced",
        )
        hearing = CAHearing(
            bill_id="202520260AB100",
            committee_type="Assembly",
            committee_nr=8,
            hearing_date="2026-02-10",
            location_code="CX08",
        )
        result = client.normalize_hearing_for_storage(hearing, {"202520260AB100": bill})

        assert result["bill_id"] == "ca-ab100"
        assert result["event_type"] == "hearing"
        assert result["event_date"] == "2026-02-10"
        assert result["committee"] == "Housing and Community Development"
        assert "AB 100" in result["description"]
        assert result["state"] == "CA"
        assert result["source"] == "leginfo_bulk"

    def test_hearing_with_unknown_bill(self, client):
        hearing = CAHearing(
            bill_id="202520260AB999",
            committee_type="Assembly",
            committee_nr=8,
            hearing_date="2026-02-10",
            location_code="CX08",
        )
        result = client.normalize_hearing_for_storage(hearing, {})
        assert result["bill_id"] == "ca-ab999"


class TestNormalizeVoteForStorage:
    """Tests for normalize_vote_for_storage."""

    @pytest.fixture
    def client(self):
        c = CaliforniaLegislatureClient()
        c._location_codes = {"AF": "Assembly Floor"}
        return c

    def test_passing_vote(self, client):
        bill = CABill(
            bill_id="202520260AB100",
            session_year="2025-2026",
            measure_type="AB",
            measure_num=100,
            status="Introduced",
        )
        vote = CAVoteSummary(
            bill_id="202520260AB100",
            location_code="AF",
            vote_datetime="2026-03-20",
            ayes=30,
            noes=8,
            abstain=2,
            result="(PASS)",
        )
        result = client.normalize_vote_for_storage(vote, {"202520260AB100": bill})

        assert result["bill_id"] == "ca-ab100"
        assert result["event_type"] == "vote"
        assert "passed" in result["description"]
        assert "30 ayes" in result["description"]
        assert "8 noes" in result["description"]
        assert "Assembly Floor" in result["description"]

    def test_failing_vote(self, client):
        vote = CAVoteSummary(
            bill_id="202520260AB100",
            location_code="AF",
            vote_datetime="2026-03-20",
            ayes=10,
            noes=28,
            abstain=2,
            result="FAIL",
        )
        result = client.normalize_vote_for_storage(vote, {})
        assert "failed" in result["description"]


class TestNormalizeHistoryForStorage:
    """Tests for normalize_history_for_storage."""

    @pytest.fixture
    def client(self):
        c = CaliforniaLegislatureClient()
        c._location_codes = {"CX08": "Housing Committee"}
        return c

    def test_hearing_event_type_detection(self, client):
        action = CAHistoryAction(
            bill_id="202520260AB100",
            action_date="2026-02-10",
            action="Heard in committee and held",
            primary_location="CX08",
        )
        result = client.normalize_history_for_storage(action, {})
        assert result["event_type"] == "hearing"

    def test_vote_event_type_detection(self, client):
        action = CAHistoryAction(
            bill_id="202520260AB100",
            action_date="2026-03-20",
            action="Read second time. Ordered to third reading. Ayes 30, Noes 8.",
        )
        result = client.normalize_history_for_storage(action, {})
        assert result["event_type"] == "vote"

    def test_signing_event_type_detection(self, client):
        action = CAHistoryAction(
            bill_id="202520260AB100",
            action_date="2026-09-10",
            action="Chaptered by Secretary of State.",
        )
        result = client.normalize_history_for_storage(action, {})
        assert result["event_type"] == "signing"

    def test_committee_referral_event_type_detection(self, client):
        action = CAHistoryAction(
            bill_id="202520260AB100",
            action_date="2026-01-20",
            action="Referred to Com. on HOUSING.",
        )
        result = client.normalize_history_for_storage(action, {})
        assert result["event_type"] == "committee_referral"

    def test_generic_action_event_type(self, client):
        action = CAHistoryAction(
            bill_id="202520260AB100",
            action_date="2026-01-15",
            action="Introduced and read first time.",
        )
        result = client.normalize_history_for_storage(action, {})
        assert result["event_type"] == "action"

    def test_description_truncated_to_500_chars(self, client):
        long_action = "A" * 600
        action = CAHistoryAction(
            bill_id="202520260AB100",
            action_date="2026-01-15",
            action=long_action,
        )
        result = client.normalize_history_for_storage(action, {})
        assert len(result["description"]) == 500

    def test_location_code_resolved(self, client):
        action = CAHistoryAction(
            bill_id="202520260AB100",
            action_date="2026-02-10",
            action="Some action",
            primary_location="CX08",
        )
        result = client.normalize_history_for_storage(action, {})
        assert result["committee"] == "Housing Committee"


# ============================================================================
# Normalize Raw Bill ID
# ============================================================================


class TestNormalizeRawBillId:
    """Tests for _normalize_raw_bill_id utility."""

    @pytest.fixture
    def client(self):
        return CaliforniaLegislatureClient()

    def test_regular_session_ab(self, client):
        assert client._normalize_raw_bill_id("202520260AB123") == "ca-ab123"

    def test_regular_session_sb(self, client):
        assert client._normalize_raw_bill_id("202520260SB45") == "ca-sb45"

    def test_extraordinary_session(self, client):
        assert client._normalize_raw_bill_id("202520261AB5") == "ca-ab5-x1"

    def test_resolution_types(self, client):
        assert client._normalize_raw_bill_id("202520260ACR10") == "ca-acr10"
        assert client._normalize_raw_bill_id("202520260SJR3") == "ca-sjr3"

    def test_unrecognized_format_lowercased(self, client):
        assert client._normalize_raw_bill_id("UNKNOWN_ID") == "unknown_id"


# ============================================================================
# Strip XML Tags
# ============================================================================


class TestStripXmlTags:
    """Tests for _strip_xml_tags utility."""

    @pytest.fixture
    def client(self):
        return CaliforniaLegislatureClient()

    def test_strips_html_tags(self, client):
        result = client._strip_xml_tags("<p>Hello</p><p>World</p>")
        assert result == "Hello World"

    def test_collapses_whitespace(self, client):
        result = client._strip_xml_tags("<p>  Multiple   spaces  </p>")
        assert result == "Multiple spaces"

    def test_nested_tags(self, client):
        result = client._strip_xml_tags("<div><span>Inner</span> text</div>")
        assert result == "Inner text"

    def test_empty_string(self, client):
        assert client._strip_xml_tags("") == ""

    def test_plain_text_unchanged(self, client):
        assert client._strip_xml_tags("no tags here") == "no tags here"


# ============================================================================
# Extract Tables from ZIP
# ============================================================================


class TestExtractTables:
    """Tests for _extract_tables ZIP extraction."""

    @pytest.fixture
    def client(self):
        return CaliforniaLegislatureClient()

    def test_extracts_requested_tables(self, client):
        zip_bytes = make_zip({
            "BILL_TBL": [["row1_field1", "row1_field2"]],
            "OTHER_TBL": [["other"]],
        })
        tables = client._extract_tables(zip_bytes, ["BILL_TBL"])
        assert "BILL_TBL" in tables
        assert "OTHER_TBL" not in tables
        # Verify the extracted file content
        rows = list(client._parse_dat_file(tables["BILL_TBL"]))
        assert rows[0] == ["row1_field1", "row1_field2"]

    def test_missing_table_not_in_result(self, client):
        zip_bytes = make_zip({"BILL_TBL": [["data"]]})
        tables = client._extract_tables(zip_bytes, ["BILL_TBL", "NONEXISTENT_TBL"])
        assert "BILL_TBL" in tables
        assert "NONEXISTENT_TBL" not in tables


# ============================================================================
# Constants
# ============================================================================


class TestConstants:
    """Tests for module-level constants."""

    def test_measure_types_has_standard_types(self):
        assert MEASURE_TYPES["AB"] == "Assembly Bill"
        assert MEASURE_TYPES["SB"] == "Senate Bill"
        assert MEASURE_TYPES["ACA"] == "Assembly Constitutional Amendment"
        assert MEASURE_TYPES["SCA"] == "Senate Constitutional Amendment"
        assert len(MEASURE_TYPES) == 10

    def test_status_map_has_standard_statuses(self):
        assert STATUS_MAP["Introduced"] == "Introduced"
        assert STATUS_MAP["Chaptered"] == "Chaptered"
        assert STATUS_MAP["Vetoed"] == "Vetoed"
        assert STATUS_MAP["Engrossed"] == "Passed House"
        assert STATUS_MAP["Enrolled"] == "Enrolled"
