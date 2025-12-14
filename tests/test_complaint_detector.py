#!/usr/bin/env python3
"""
Tests for complaint detection system (Layer 4)

Validates >80% detection accuracy and <10% false positive rate
"""

import pytest
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from complaint_detector import ComplaintDetector, ComplaintIntent


# Test data: True complaints (should detect)
TRUE_COMPLAINTS = [
    {
        'message': "My landlord won't fix the broken heating in my Berkeley apartment",
        'expected_type': 'housing',
        'expected_jurisdiction': 'city-berkeley'
    },
    {
        'message': "There's a huge pothole on Main Street that's been there for weeks",
        'expected_type': 'infrastructure',
        'expected_jurisdiction': None  # No location mentioned
    },
    {
        'message': "The bus route to Oakland was cancelled without notice",
        'expected_type': 'transportation',
        'expected_jurisdiction': 'city-oakland'
    },
    {
        'message': "Excessive noise from construction site in San Rafael waking everyone up",
        'expected_type': 'community',  # or public_safety
        'expected_jurisdiction': 'city-san-rafael'
    },
    {
        'message': "Park in my neighborhood is full of trash and broken equipment",
        'expected_type': 'environment',
        'expected_jurisdiction': None
    },
    {
        'message': "My rent went up 30% and I can't afford it anymore",
        'expected_type': 'housing',
        'expected_jurisdiction': None
    },
    {
        'message': "Bike lane on 5th street is blocked by parked cars every day",
        'expected_type': 'transportation',
        'expected_jurisdiction': None
    },
    {
        'message': "Library in Hayward has been closed for months with no explanation",
        'expected_type': 'community',
        'expected_jurisdiction': 'city-hayward'
    },
    {
        'message': "Air quality is terrible near the industrial area",
        'expected_type': 'environment',
        'expected_jurisdiction': None
    },
    {
        'message': "Street lights haven't worked in weeks making it unsafe at night",
        'expected_type': 'infrastructure',  # or public_safety
        'expected_jurisdiction': None
    }
]

# Test data: Non-complaints (should NOT detect)
NON_COMPLAINTS = [
    "When is the next city council meeting?",
    "What's the zoning code for residential areas?",
    "How do I apply for a building permit?",
    "They fixed the pothole on my street yesterday, thanks!",
    "Where can I find information about upcoming events?",
    "Can you explain how the budget process works?",
    "What time does the library close?",
    "I love the new park that opened last month",
    "Call 911 there's a fire!",  # Emergency, not complaint
    "Hello, can you help me?"
]


@pytest.fixture
def detector():
    """Create detector instance"""
    return ComplaintDetector()


class TestComplaintDetection:
    """Test complaint detection accuracy"""

    def test_detect_true_complaints(self, detector):
        """Should detect all true complaints"""
        detected_count = 0

        for test_case in TRUE_COMPLAINTS:
            message = test_case['message']
            intent = detector.detect_complaint(message)

            if intent is not None:
                detected_count += 1
                print(f"✓ Detected: {message[:50]}...")
                print(f"  Type: {intent.issue_type}, Jurisdiction: {intent.jurisdiction_id}")
            else:
                print(f"✗ MISSED: {message[:50]}...")

        detection_rate = detected_count / len(TRUE_COMPLAINTS)
        print(f"\nDetection rate: {detection_rate:.1%} ({detected_count}/{len(TRUE_COMPLAINTS)})")

        # Must detect at least 80% of complaints
        assert detection_rate >= 0.80, f"Detection rate {detection_rate:.1%} below 80% threshold"

    def test_reject_non_complaints(self, detector):
        """Should NOT detect non-complaints (false positive rate <10%)"""
        false_positives = 0

        for message in NON_COMPLAINTS:
            intent = detector.detect_complaint(message)

            if intent is not None:
                false_positives += 1
                print(f"✗ FALSE POSITIVE: {message[:50]}...")
                print(f"  Type: {intent.issue_type}, Desc: {intent.description[:50]}...")
            else:
                print(f"✓ Correctly rejected: {message[:50]}...")

        false_positive_rate = false_positives / len(NON_COMPLAINTS)
        print(f"\nFalse positive rate: {false_positive_rate:.1%} ({false_positives}/{len(NON_COMPLAINTS)})")

        # False positive rate must be <10%
        assert false_positive_rate < 0.10, f"False positive rate {false_positive_rate:.1%} exceeds 10% threshold"

    def test_issue_type_classification(self, detector):
        """Should classify issue types correctly"""
        correct_classifications = 0

        for test_case in TRUE_COMPLAINTS:
            message = test_case['message']
            expected_type = test_case['expected_type']
            intent = detector.detect_complaint(message)

            if intent and intent.issue_type == expected_type:
                correct_classifications += 1
                print(f"✓ Correct type: {message[:40]}... → {intent.issue_type}")
            elif intent:
                # Allow some flexibility (environment/community can be ambiguous)
                print(f"⚠ Different type: {message[:40]}... → {intent.issue_type} (expected {expected_type})")
            else:
                print(f"✗ Not detected: {message[:40]}...")

        classification_rate = correct_classifications / len(TRUE_COMPLAINTS)
        print(f"\nClassification accuracy: {classification_rate:.1%} ({correct_classifications}/{len(TRUE_COMPLAINTS)})")

        # Should get at least 60% exactly right (allow some flexibility)
        assert classification_rate >= 0.60, f"Classification accuracy {classification_rate:.1%} below 60%"

    def test_jurisdiction_resolution(self, detector):
        """Should resolve jurisdiction from location mentions"""
        correct_jurisdictions = 0
        testable_cases = [tc for tc in TRUE_COMPLAINTS if tc['expected_jurisdiction']]

        for test_case in testable_cases:
            message = test_case['message']
            expected_jurisdiction = test_case['expected_jurisdiction']
            intent = detector.detect_complaint(message)

            if intent and intent.jurisdiction_id == expected_jurisdiction:
                correct_jurisdictions += 1
                print(f"✓ Correct jurisdiction: {message[:40]}... → {intent.jurisdiction_id}")
            elif intent:
                print(f"✗ Wrong jurisdiction: {message[:40]}... → {intent.jurisdiction_id} (expected {expected_jurisdiction})")
            else:
                print(f"✗ Not detected: {message[:40]}...")

        if testable_cases:
            jurisdiction_rate = correct_jurisdictions / len(testable_cases)
            print(f"\nJurisdiction accuracy: {jurisdiction_rate:.1%} ({correct_jurisdictions}/{len(testable_cases)})")

            # Should get at least 70% of jurisdictions right
            assert jurisdiction_rate >= 0.70, f"Jurisdiction accuracy {jurisdiction_rate:.1%} below 70%"

    def test_empty_message(self, detector):
        """Should handle empty messages gracefully"""
        assert detector.detect_complaint("") is None
        assert detector.detect_complaint("   ") is None
        assert detector.detect_complaint("hi") is None  # Too short

    def test_with_user_context(self, detector):
        """Should use user context for jurisdiction fallback"""
        message = "My landlord won't fix the heating"  # No location mentioned
        user_context = {'jurisdiction_id': 'city-berkeley'}

        intent = detector.detect_complaint(message, user_context)

        assert intent is not None
        assert intent.issue_type == 'housing'
        assert intent.jurisdiction_id == 'city-berkeley'  # From user context


class TestComplaintIntent:
    """Test ComplaintIntent dataclass"""

    def test_to_dict(self):
        """Should convert to dictionary"""
        intent = ComplaintIntent(
            description="Test complaint",
            issue_type="housing",
            jurisdiction_id="city-test",
            location_mention="Test City",
            confidence="high"
        )

        d = intent.to_dict()
        assert d['description'] == "Test complaint"
        assert d['issue_type'] == "housing"
        assert d['jurisdiction_id'] == "city-test"
        assert d['location_mention'] == "Test City"
        assert d['confidence'] == "high"


if __name__ == '__main__':
    # Run with pytest
    pytest.main([__file__, '-v', '-s'])
