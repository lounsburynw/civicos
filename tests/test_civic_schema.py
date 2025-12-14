#!/usr/bin/env python3
"""
Comprehensive Test Suite for Civic Schema Adapter
Ensures reliable integration between civic_digest.py and civic-app-schema.json

Usage:
  python tests/test_civic_schema.py                 # Run all tests
  python tests/test_civic_schema.py TestClass       # Run specific test class
  python tests/test_civic_schema.py -v              # Verbose output
  python tests/test_civic_schema.py --performance   # Include performance tests

Test Coverage:
- DateTime parsing accuracy
- Phone number extraction
- HTML to text conversion
- Schema compliance validation
- Error handling robustness
- Integration with civic_digest.py
- Performance under load

"""

import unittest
import json
import sys
import os
import time
from datetime import datetime, timezone
from unittest.mock import Mock, patch

# Import the schema adapter
try:
    from civic_schema_adapter import CivicSchemaAdapter, SchemaCivicOpportunity, SchemaNewsletter
except ImportError:
    print("❌ Cannot import civic_schema_adapter.py - ensure it's in the same directory")
    sys.exit(1)


class TestDateTimeParsing(unittest.TestCase):
    """Test datetime conversion accuracy with civic meeting formats"""
    
    def setUp(self):
        self.adapter = CivicSchemaAdapter()
    
    def test_march_format_parsing(self):
        """Test 'March 15, 2024' format parsing"""
        result = self.adapter.convert_to_iso_datetime("March 15, 2024", "18:00")
        expected_date = "2024-03-15"
        expected_time = "18:00"
        
        self.assertIn(expected_date, result)
        self.assertIn(expected_time, result)
        self.assertTrue(result.endswith("+00:00"))  # UTC timezone
    
    def test_march_with_time_parsing(self):
        """Test 'March 15, 2024 18:00' format parsing"""
        result = self.adapter.convert_to_iso_datetime("March 15, 2024 18:00", "19:00")
        # Should use the provided time, not default
        self.assertIn("18:00", result)
        self.assertNotIn("19:00", result)
    
    def test_iso_date_format(self):
        """Test '2024-03-15' format parsing"""
        result = self.adapter.convert_to_iso_datetime("2024-03-15", "18:00")
        self.assertIn("2024-03-15T18:00:00+00:00", result)
    
    def test_slash_date_format(self):
        """Test '03/15/2024' format parsing"""
        result = self.adapter.convert_to_iso_datetime("03/15/2024", "18:00")
        self.assertIn("2024-03-15T18:00:00+00:00", result)
    
    def test_month_day_current_year(self):
        """Test 'March 15' format (assume current year)"""
        result = self.adapter.convert_to_iso_datetime("March 15", "18:00")
        current_year = datetime.now().year
        expected = f"{current_year}-03-15T18:00:00+00:00"
        self.assertEqual(result, expected)
    
    def test_empty_date_fallback(self):
        """Test empty date string fallback"""
        result = self.adapter.convert_to_iso_datetime("", "18:00")
        # Should return current timestamp
        parsed = datetime.fromisoformat(result.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        # Should be within 2 seconds
        self.assertLess(abs((parsed - now).total_seconds()), 2)
    
    def test_invalid_date_fallback(self):
        """Test invalid date string fallback"""
        result = self.adapter.convert_to_iso_datetime("Not a date", "18:00")
        # Should return current timestamp
        parsed = datetime.fromisoformat(result.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        self.assertLess(abs((parsed - now).total_seconds()), 2)


class TestPhoneExtraction(unittest.TestCase):
    """Test phone number extraction from mixed virtual meeting data"""
    
    def setUp(self):
        self.adapter = CivicSchemaAdapter()
    
    def test_standard_phone_formats(self):
        """Test extraction of standard phone number formats"""
        test_cases = [
            ("(415) 485-3100", "(415) 485-3100"),
            ("415-485-3100", "415-485-3100"),  
            ("4154853100", "4154853100"),
            ("+1 (415) 485-3100", "+1 (415) 485-3100")
        ]
        
        for input_phone, expected in test_cases:
            result = self.adapter._extract_phone_number(input_phone)
            self.assertEqual(result, expected, f"Failed for input: {input_phone}")
    
    def test_zoom_meeting_filtering(self):
        """Test filtering out Zoom meeting info from phone fields"""
        zoom_data = "1 (669) 444-9171, ID: 894 4903 7326, Passcode: 123456"
        result = self.adapter._extract_phone_number(zoom_data)
        self.assertEqual(result, "(669) 444-9171")  # Should extract just the phone
    
    def test_mixed_virtual_meeting_data(self):
        """Test handling of mixed virtual meeting information"""
        mixed_data = "Zoom: 1-669-900-6833, Meeting ID: 123 456 789"
        result = self.adapter._extract_phone_number(mixed_data)
        # Should return empty since this is clearly virtual meeting info, not a city phone
        self.assertEqual(result, "")
    
    def test_empty_phone_handling(self):
        """Test handling of empty phone data"""
        result = self.adapter._extract_phone_number("")
        self.assertEqual(result, "")
        
        result = self.adapter._extract_phone_number(None)
        self.assertEqual(result, "")


class TestHtmlToTextConversion(unittest.TestCase):
    """Test HTML newsletter conversion to readable text"""
    
    def setUp(self):
        self.adapter = CivicSchemaAdapter()
    
    def test_basic_html_structure(self):
        """Test conversion of basic HTML structure"""
        html = """
        <h1>Meeting Agenda</h1>
        <p>This is a paragraph.</p>
        <div>This is a div.</div>
        """
        result = self.adapter.html_to_text(html)
        
        self.assertIn("Meeting Agenda", result)
        self.assertIn("This is a paragraph.", result)
        self.assertIn("This is a div.", result)
        # Should have proper line breaks
        lines = result.split('\n')
        self.assertGreater(len(lines), 1)
    
    def test_list_conversion(self):
        """Test HTML list conversion with bullet points"""
        html = """
        <ul>
            <li>First item</li>
            <li>Second item</li>
        </ul>
        """
        result = self.adapter.html_to_text(html)
        
        self.assertIn("• First item", result)
        self.assertIn("• Second item", result)
    
    def test_html_entity_decoding(self):
        """Test proper HTML entity decoding"""
        html = "Contact: info@city.gov &amp; planning@city.gov"
        result = self.adapter.html_to_text(html)
        
        self.assertIn("info@city.gov & planning@city.gov", result)
        self.assertNotIn("&amp;", result)
    
    def test_table_structure_preservation(self):
        """Test table structure preservation"""
        html = """
        <table>
            <tr><td>Item 1</td><td>Description 1</td></tr>
            <tr><td>Item 2</td><td>Description 2</td></tr>
        </table>
        """
        result = self.adapter.html_to_text(html)
        
        # Should use | separator for table cells
        self.assertIn("Item 1 | Description 1", result)
        self.assertIn("Item 2 | Description 2", result)
    
    def test_empty_html_handling(self):
        """Test handling of empty HTML"""
        result = self.adapter.html_to_text("")
        self.assertEqual(result, "")
        
        result = self.adapter.html_to_text("   ")
        self.assertEqual(result, "")
    
    def test_malformed_html_fallback(self):
        """Test fallback for malformed HTML"""
        malformed = "<div><p>Unclosed tags<span>More content"
        result = self.adapter.html_to_text(malformed)
        
        # Should still extract text content
        self.assertIn("Unclosed tags", result)
        self.assertIn("More content", result)


class TestSchemaCompliance(unittest.TestCase):
    """Test schema compliance and validation"""
    
    def setUp(self):
        self.adapter = CivicSchemaAdapter()
        self.sample_civic_data = {
            "meeting": {
                "city": "San Rafael",
                "date": "March 15, 2024",
                "start_time": "18:00",
                "location": "Council Chambers",
                "public_comment_email": "clerk@cityofsanrafael.org",
                "meeting_type": "Planning Commission"
            },
            "items": [
                {
                    "title": "Oak Street Housing Development",
                    "change": "New 50-unit apartment complex",
                    "impact": "Increased housing supply but potential traffic concerns",
                    "how_to_participate": "Email comments by March 12 or attend meeting",
                    "project_type": "housing",
                    "location": "123 Oak Street"
                }
            ],
            "bottom_line": "One housing project up for review"
        }
    
    def test_enum_normalization(self):
        """Test project type enum normalization"""
        test_cases = [
            ("housing", "housing"),
            ("transportation", "traffic"),
            ("public safety", "public_safety"),
            ("parks/recreation", "community"),
            ("taxes/finance", "budget"),
            ("unknown_type", "community")  # Fallback
        ]
        
        for input_type, expected in test_cases:
            result = self.adapter.normalize_project_type(input_type)
            self.assertEqual(result, expected, f"Failed for: {input_type}")
    
    def test_meeting_type_normalization(self):
        """Test meeting type enum normalization"""
        test_cases = [
            ("Planning Commission", "planning_commission"),
            ("City Council", "city_council"),
            ("Public Hearing", "public_hearing"),
            ("Unknown Meeting", "community_meeting")  # Fallback
        ]
        
        for input_type, expected in test_cases:
            result = self.adapter.normalize_meeting_type(input_type)
            self.assertEqual(result, expected, f"Failed for: {input_type}")
    
    def test_opportunity_validation(self):
        """Test civic opportunity validation"""
        # Create valid opportunity
        jurisdiction = self.adapter.extract_jurisdiction_from_meeting(self.sample_civic_data["meeting"])
        opportunity = self.adapter.adapt_civic_opportunity(
            self.sample_civic_data["items"][0],
            self.sample_civic_data["meeting"],
            jurisdiction,
            "https://example.com"
        )
        
        self.assertIsNotNone(opportunity)
        self.assertTrue(self.adapter.validate_opportunity(opportunity))
        
        # Test required fields
        self.assertIsNotNone(opportunity.title)
        self.assertIsNotNone(opportunity.description)
        self.assertIsNotNone(opportunity.jurisdiction.name)
        self.assertIsNotNone(opportunity.contact_info.email)
    
    def test_newsletter_adaptation(self):
        """Test complete newsletter adaptation"""
        html_content = """
        Subject: Planning Commission Meeting - March 15, 2024
        <h1>San Rafael Planning Commission</h1>
        <p>Your guide to what's on the agenda...</p>
        """
        
        newsletter = self.adapter.adapt_newsletter(
            self.sample_civic_data,
            html_content,
            "https://example.com",
            ["test@example.com"]
        )
        
        self.assertIsNotNone(newsletter)
        self.assertEqual(len(newsletter.events), 1)
        self.assertEqual(newsletter.jurisdiction.name, "San Rafael")
        self.assertEqual(newsletter.subject_line, "Planning Commission Meeting - March 15, 2024")
        self.assertIn("test@example.com", newsletter.recipients)


class TestErrorHandling(unittest.TestCase):
    """Test error handling and edge cases"""
    
    def setUp(self):
        self.adapter = CivicSchemaAdapter()
    
    def test_missing_meeting_data(self):
        """Test handling of missing meeting data"""
        empty_data = {"meeting": {}, "items": []}
        
        newsletter = self.adapter.adapt_newsletter(empty_data, "", "https://example.com")
        self.assertIsNotNone(newsletter)
        self.assertEqual(len(newsletter.events), 0)
    
    def test_malformed_opportunity_data(self):
        """Test handling of malformed opportunity data"""
        malformed_data = {
            "meeting": {"city": "Test City"},
            "items": [
                {},  # Empty item
                {"title": ""},  # Empty title
                {"title": "Valid Item", "impact": "Valid impact"}  # Valid item
            ]
        }
        
        newsletter = self.adapter.adapt_newsletter(malformed_data, "", "https://example.com")
        self.assertIsNotNone(newsletter)
        # Should have at least the valid item
        self.assertGreaterEqual(len(newsletter.events), 1)
    
    def test_json_serialization(self):
        """Test JSON serialization of schema objects"""
        sample_data = {
            "meeting": {"city": "Test City", "date": "March 15, 2024"},
            "items": [{"title": "Test Item", "impact": "Test impact", 
                      "how_to_participate": "Test participation", "project_type": "housing"}]
        }
        
        newsletter = self.adapter.adapt_newsletter(sample_data, "Test content", "https://example.com")
        json_dict = self.adapter.to_dict(newsletter)
        
        # Should be JSON serializable
        json_str = json.dumps(json_dict)
        self.assertIsInstance(json_str, str)
        
        # Should be deserializable
        deserialized = json.loads(json_str)
        self.assertIsInstance(deserialized, dict)


class TestPerformance(unittest.TestCase):
    """Test performance with larger datasets"""
    
    def setUp(self):
        self.adapter = CivicSchemaAdapter()
    
    def test_large_opportunity_set(self):
        """Test performance with 50+ events"""
        # Create large dataset
        large_data = {
            "meeting": {
                "city": "Large City",
                "date": "March 15, 2024",
                "start_time": "18:00",
                "public_comment_email": "clerk@largecity.org"
            },
            "items": []
        }
        
        # Generate 50 events
        for i in range(50):
            large_data["items"].append({
                "title": f"Development Project {i+1}",
                "impact": f"Impact description {i+1}",
                "how_to_participate": "Email comments or attend meeting",
                "project_type": "housing" if i % 2 == 0 else "traffic",
                "location": f"Address {i+1}"
            })
        
        start_time = time.time()
        newsletter = self.adapter.adapt_newsletter(large_data, "Large newsletter", "https://example.com")
        end_time = time.time()
        
        processing_time = end_time - start_time
        
        self.assertIsNotNone(newsletter)
        self.assertEqual(len(newsletter.events), 50)
        self.assertLess(processing_time, 5.0)  # Should complete in under 5 seconds
        
        print(f"  Performance: Processed 50 events in {processing_time:.2f} seconds")


class TestIntegration(unittest.TestCase):
    """Test integration with civic_digest.py patterns"""
    
    def setUp(self):
        self.adapter = CivicSchemaAdapter()
    
    def test_realistic_san_rafael_data(self):
        """Test with realistic San Rafael meeting data structure"""
        realistic_data = {
            "meeting": {
                "city": "San Rafael",
                "date": "September 2, 2025",
                "start_time": "7:00 PM",
                "location": "City Council Chambers, 1400 Fifth Avenue, San Rafael",
                "livestream": "https://www.youtube.com/watch?v=example",
                "public_comment_email": "citycouncil@cityofsanrafael.org",
                "public_comment_deadline": "September 2, 2025 at 4:00 PM",
                "meeting_type": "City Council"
            },
            "items": [
                {
                    "title": "Fourth Street Redesign Project",
                    "change": "Complete reconstruction of Fourth Street from A to E Streets",
                    "impact": "Major traffic disruption for 18 months, improved bike/pedestrian safety after completion",
                    "how_to_participate": "Email citycouncil@cityofsanrafael.org by Sept 2 at 4 PM or attend meeting for 3-minute public comment",
                    "project_type": "transportation",
                    "location": "Fourth Street, A-E Streets"
                },
                {
                    "title": "Affordable Housing Development - 1500 Fifth Avenue",
                    "change": "120-unit affordable housing complex with ground-floor retail",
                    "impact": "Increased housing supply, potential parking concerns, new retail events",
                    "how_to_participate": "Submit written comments to planning@cityofsanrafael.org or speak at meeting",
                    "project_type": "housing",
                    "location": "1500 Fifth Avenue"
                }
            ],
            "recap_rows": [
                {
                    "topic": "Street Redesign",
                    "why_it_matters": "Major traffic changes affecting daily commutes",
                    "act_by": "Sept 2, 4 PM"
                }
            ],
            "bottom_line": "Two major projects affecting transportation and housing - public input requested by Sept 2"
        }
        
        html_content = """
        Subject: San Rafael City Council - September 2, 2025
        <h1>🏛️ San Rafael City Council</h1>
        <p><em>Your quick guide to what's on the City Council agenda — Tuesday, September 2, 2025</em></p>
        <h2>🗣️ How to Participate</h2>
        <ul>
        <li><strong>Meeting:</strong> Tuesday, September 2 at 7:00 PM 📅</li>
        <li><strong>Where:</strong> City Council Chambers, 1400 Fifth Avenue, San Rafael</li>
        <li><strong>Watch Online:</strong> <a href="https://www.youtube.com/watch?v=example">YouTube Live Stream</a></li>
        <li><strong>Email Comments:</strong> citycouncil@cityofsanrafael.org — <strong>deadline:</strong> Sept 2 at 4 PM</li>
        <li><strong>Attend & Speak:</strong> Public comment allowed - 3 minutes per person</li>
        </ul>
        """
        
        newsletter = self.adapter.adapt_newsletter(realistic_data, html_content, 
                                                 "https://cityofsanrafael.org/meetings/city-council-september-2-2025")
        
        # Validate results
        self.assertIsNotNone(newsletter)
        self.assertEqual(newsletter.jurisdiction.name, "San Rafael")
        self.assertEqual(len(newsletter.events), 2)
        
        # Check first opportunity
        traffic_opp = newsletter.events[0]
        self.assertEqual(traffic_opp.title, "Fourth Street Redesign Project")
        self.assertEqual(traffic_opp.project_type, "traffic")  # Normalized from "transportation"
        self.assertEqual(traffic_opp.meeting_type, "city_council")
        
        # Check datetime parsing
        self.assertIn("2025-09-02", traffic_opp.when)
        self.assertIn("19:00", traffic_opp.when)  # 7:00 PM should convert to 19:00
        
        # Check contact info
        self.assertEqual(traffic_opp.contact_info.email, "citycouncil@cityofsanrafael.org")
        
        # Check HTML to text conversion
        self.assertIn("San Rafael City Council", newsletter.text_content)
        self.assertIn("How to Participate", newsletter.text_content)
        self.assertNotIn("<h1>", newsletter.text_content)  # HTML tags should be removed


def run_test_suite():
    """Run the complete test suite with reporting"""
    print("🧪 Civic Schema Adapter - Comprehensive Test Suite")
    print("=" * 60)
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    test_classes = [
        TestDateTimeParsing,
        TestPhoneExtraction,
        TestHtmlToTextConversion,
        TestSchemaCompliance,
        TestErrorHandling,
        TestPerformance,
        TestIntegration
    ]
    
    for test_class in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(test_class))
    
    # Run tests with detailed output
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)
    
    # Summary
    print("\n" + "=" * 60)
    print(f"🎯 TEST SUMMARY")
    print(f"   Tests run: {result.testsRun}")
    print(f"   Failures: {len(result.failures)}")
    print(f"   Errors: {len(result.errors)}")
    print(f"   Success rate: {((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100):.1f}%")
    
    if result.wasSuccessful():
        print("✅ All tests passed! Schema adapter is ready for production.")
        return True
    else:
        print("❌ Some tests failed. Review output above.")
        return False


if __name__ == "__main__":
    # Check for performance flag
    run_performance = "--performance" in sys.argv
    if run_performance:
        sys.argv.remove("--performance")
    
    # Run specific test if provided
    if len(sys.argv) > 1 and sys.argv[1] != "-v":
        unittest.main()
    else:
        # Run full test suite
        success = run_test_suite()
        sys.exit(0 if success else 1)