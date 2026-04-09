"""Tests for civicos._internal.meetings.minutes — parsing and extraction logic.

Focuses on regex-based extraction methods that parse meeting minutes text.
Does NOT require PDF files (fitz/PyMuPDF) — tests the text parsing directly.
"""

from civicos._internal.meetings.minutes import (
    MinutesExtractor,
    VoteRecord,
    AgendaItemMinutes,
    MeetingMinutes,
)


def make_extractor():
    return MinutesExtractor(jurisdiction_id=None)


class TestVoteRecordToDict:
    """VoteRecord serialization."""

    def test_to_dict_all_fields(self):
        vote = VoteRecord(
            motion_by="Councilmember Smith",
            second_by="Vice Mayor Jones",
            ayes=["Councilmember Smith", "Vice Mayor Jones", "Mayor Brown"],
            noes=[],
            absent=["Councilmember Lee"],
            outcome="adopted",
            resolution_number="15432",
            ordinance_number=None,
        )
        d = vote.to_dict()
        assert d["motion_by"] == "Councilmember Smith"
        assert d["second_by"] == "Vice Mayor Jones"
        assert len(d["ayes"]) == 3
        assert d["noes"] == []
        assert d["absent"] == ["Councilmember Lee"]
        assert d["outcome"] == "adopted"
        assert d["resolution_number"] == "15432"
        assert d["ordinance_number"] is None


class TestAgendaItemMinutesToDict:
    """AgendaItemMinutes serialization."""

    def test_to_dict_with_votes(self):
        vote = VoteRecord(
            motion_by="Mayor Brown",
            second_by="Councilmember Smith",
            ayes=["Mayor Brown", "Councilmember Smith"],
            noes=[],
            absent=[],
            outcome="adopted",
        )
        item = AgendaItemMinutes(
            item_number="6.a",
            title="Housing Element Update",
            description="Staff report on housing element",
            presenters=["City Manager Cristine"],
            public_speakers=["John Doe", "Jane Smith"],
            votes=[vote],
            summary_notes="Council directed staff to proceed",
        )
        d = item.to_dict()
        assert d["item_number"] == "6.a"
        assert d["title"] == "Housing Element Update"
        assert len(d["votes"]) == 1
        assert d["votes"][0]["motion_by"] == "Mayor Brown"
        assert d["public_speakers"] == ["John Doe", "Jane Smith"]


class TestExtractMeetingDate:
    """Test regex extraction of meeting dates."""

    def test_standard_format(self):
        ext = make_extractor()
        text = "SAN RAFAEL CITY COUNCIL - REGULAR MEETING\nMONDAY, OCTOBER 6, 2024"
        result = ext._extract_meeting_date(text)
        assert "OCTOBER" in result
        assert "2024" in result

    def test_no_match(self):
        ext = make_extractor()
        result = ext._extract_meeting_date("Some random text")
        assert result == ""


class TestExtractMeetingType:
    """Test extraction of meeting type."""

    def test_regular_meeting(self):
        ext = make_extractor()
        result = ext._extract_meeting_type("SAN RAFAEL CITY COUNCIL REGULAR MEETING")
        assert result == "regular"

    def test_special_meeting(self):
        ext = make_extractor()
        result = ext._extract_meeting_type("SPECIAL MEETING OF THE CITY COUNCIL")
        assert result == "special"

    def test_default_when_not_found(self):
        ext = make_extractor()
        result = ext._extract_meeting_type("City Council Session")
        assert result == "regular"


class TestExtractMeetingTime:
    """Test extraction of meeting time."""

    def test_standard_time(self):
        ext = make_extractor()
        result = ext._extract_meeting_time("REGULAR MEETING AT 7:00 P.M.")
        assert "7:00" in result

    def test_no_match(self):
        ext = make_extractor()
        result = ext._extract_meeting_time("No time here")
        assert result == ""


class TestExtractCalledToOrder:
    """Test extraction of called-to-order time."""

    def test_standard_format(self):
        ext = make_extractor()
        text = "Mayor Kate called the meeting to order at 7:02 p.m."
        result = ext._extract_called_to_order(text)
        assert result is not None
        assert "7:02" in result

    def test_no_match(self):
        ext = make_extractor()
        result = ext._extract_called_to_order("The meeting began.")
        assert result is None


class TestExtractAdjourned:
    """Test extraction of adjournment time."""

    def test_standard_format(self):
        ext = make_extractor()
        text = "Mayor Kate adjourned the meeting at 9:45 p.m."
        result = ext._extract_adjourned(text)
        assert result is not None
        assert "9:45" in result

    def test_no_match(self):
        ext = make_extractor()
        result = ext._extract_adjourned("End of meeting.")
        assert result is None


class TestExtractRecesses:
    """Test extraction of recess times."""

    def test_single_recess(self):
        ext = make_extractor()
        text = "Mayor Kate called a recess at 8:15 p.m."
        result = ext._extract_recesses(text)
        assert len(result) == 1
        assert "8:15" in result[0]

    def test_no_recesses(self):
        ext = make_extractor()
        result = ext._extract_recesses("The meeting continued.")
        assert result == []


class TestParseNames:
    """Test name parsing from attendance text."""

    def test_council_members(self):
        ext = make_extractor()
        text = "Mayor Kate, Vice Mayor Llorens, Councilmember Bushey, Councilmember Hill"
        names = ext._parse_names(text)
        assert len(names) >= 3
        assert any("Mayor Kate" in n for n in names)
        assert any("Bushey" in n for n in names)

    def test_filters_none(self):
        ext = make_extractor()
        text = "Mayor Kate, Councilmember None"
        names = ext._parse_names(text)
        # "None" should be filtered out
        assert not any("None" in n for n in names)

    def test_empty_text(self):
        ext = make_extractor()
        names = ext._parse_names("")
        assert names == []


class TestParseStaffNames:
    """Test staff name parsing."""

    def test_staff_with_titles(self):
        ext = make_extractor()
        text = "City Manager Cristine Alilovich, City Attorney Robert Epstein, City Clerk Lindsay Lara"
        staff = ext._parse_staff_names(text)
        assert len(staff) == 3
        assert any("Cristine" in s for s in staff)
        assert any("City Manager" in s for s in staff)

    def test_director(self):
        ext = make_extractor()
        text = "Director Sarah Chen presented the budget"
        staff = ext._parse_staff_names(text)
        assert len(staff) == 1
        assert "Director Sarah" in staff[0]


class TestExtractAttendance:
    """Test full attendance extraction."""

    def test_full_attendance_block(self):
        ext = make_extractor()
        text = """
Present: Mayor Kate, Vice Mayor Llorens, Councilmember Bushey, Councilmember Hill
Absent: Councilmember Kertz
Also Present: City Manager Cristine Alilovich, City Attorney Robert Epstein
"""
        present, absent, also_present = ext._extract_attendance(text)
        assert len(present) >= 3
        assert len(absent) >= 1
        assert len(also_present) >= 2


class TestExtractLocation:
    """Test location extraction."""

    def test_chambers_in_text(self):
        ext = make_extractor()
        text = "REGULAR MEETING AT 7:00 P.M.\nCity Council Chambers, 1400 Fifth Avenue"
        result = ext._extract_location(text)
        assert "Chambers" in result

    def test_default_city_hall(self):
        ext = MinutesExtractor(jurisdiction_id=None)
        result = ext._extract_location("No location info here at all")
        assert result == "City Hall"


class TestMeetingMinutesToDict:
    """Test MeetingMinutes full serialization."""

    def test_to_dict_structure(self):
        vote = VoteRecord(
            motion_by="Mayor Brown",
            second_by="Councilmember Smith",
            ayes=["Mayor Brown"],
            noes=[],
            absent=[],
            outcome="adopted",
        )
        item = AgendaItemMinutes(
            item_number="1",
            title="Approval of Minutes",
            description="",
            presenters=[],
            public_speakers=[],
            votes=[vote],
            summary_notes="",
        )
        minutes = MeetingMinutes(
            meeting_type="regular",
            meeting_date="2024-10-06",
            meeting_time="7:00 P.M.",
            location="City Council Chambers",
            present=["Mayor Brown"],
            absent=[],
            also_present=["City Manager Doe"],
            called_to_order="7:02 p.m.",
            adjourned="9:30 p.m.",
            recesses=[],
            items=[item],
            public_expression_speakers=["John Q. Public"],
        )
        d = minutes.to_dict()
        assert d["meeting_type"] == "regular"
        assert d["meeting_date"] == "2024-10-06"
        assert len(d["items"]) == 1
        assert d["items"][0]["votes"][0]["outcome"] == "adopted"
        assert d["public_expression_speakers"] == ["John Q. Public"]
        assert d["called_to_order"] == "7:02 p.m."
        assert d["adjourned"] == "9:30 p.m."
        assert d["approval_status"] == "pending"
