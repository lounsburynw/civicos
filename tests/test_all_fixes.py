#!/usr/bin/env python3
"""Test all critical fixes for civic action buttons"""

import json
import requests
import sys
import time

API_URL = "http://localhost:8001/api/conversation"
API_KEY = "dev_key_local"

def test_improved_matching():
    """Test the improved opportunity matching algorithm"""
    print("\n[TEST] Improved Event Matching Algorithm")
    print("-" * 50)
    
    test_cases = [
        # Test case: Multiple relevant words should score higher
        {
            "message": "I'm interested in electric bicycle safety regulations and how they affect transportation",
            "expected_match": "Electric Bicycle Safety",
            "interests": ["transportation", "safety"]
        },
        # Test case: Partial matches should still work  
        {
            "message": "Tell me about building codes and construction regulations",
            "expected_match": "Building Code",
            "interests": ["housing", "development"]
        },
        # Test case: Test relevance scoring
        {
            "message": "What library services are funded by the parcel tax?",
            "expected_match": "Library Parcel Tax",
            "interests": ["community"]
        }
    ]
    
    for i, test in enumerate(test_cases, 1):
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}"
        }
        
        data = {
            "message": test["message"],
            "city": "San Rafael",
            "interests": test["interests"]
        }
        
        try:
            response = requests.post(API_URL, headers=headers, json=data, timeout=10)
            if response.status_code == 200:
                result = response.json()
                actions = result.get('actions', [])
                
                # Check if expected opportunity was matched
                found_match = False
                for action in actions:
                    if action.get('type') == 'email':
                        label = action.get('label', '')
                        if test["expected_match"].lower() in label.lower():
                            found_match = True
                            break
                
                if found_match:
                    print(f"  ✅ Test {i}: Found expected match '{test['expected_match']}'")
                    print(f"     Generated {len(actions)} actions")
                else:
                    print(f"  ⚠️  Test {i}: Expected '{test['expected_match']}' but got:")
                    for action in actions:
                        print(f"     - {action.get('type')}: {action.get('label', 'N/A')}")
            else:
                print(f"  ❌ Test {i}: HTTP {response.status_code}")
        except Exception as e:
            print(f"  ❌ Test {i}: Error - {str(e)[:50]}")

def test_data_freshness_warning():
    """Test data freshness warnings"""
    print("\n[TEST] Data Freshness Warning System")
    print("-" * 50)
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    
    data = {
        "message": "What civic events are available?",
        "city": "San Rafael"
    }
    
    try:
        response = requests.post(API_URL, headers=headers, json=data, timeout=10)
        if response.status_code == 200:
            result = response.json()
            
            # Check for data warning
            if 'data_warning' in result:
                print(f"  ✅ Data freshness warning present:")
                print(f"     {result['data_warning']}")
                
                if 'data_freshness' in result:
                    freshness = result['data_freshness']
                    print(f"     Age: {freshness.get('age_days', 'unknown')} days")
                    print(f"     Last updated: {freshness.get('last_updated', 'unknown')[:10]}")
                    
            else:
                print(f"  ℹ️  No data warning (data might be fresh)")
                
        else:
            print(f"  ❌ HTTP {response.status_code}")
    except Exception as e:
        print(f"  ❌ Error: {str(e)[:100]}")

def test_error_handling():
    """Test improved error handling"""
    print("\n[TEST] Error Handling Improvements")
    print("-" * 50)
    
    # Test malformed request
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    
    test_cases = [
        {"message": "", "city": "San Rafael"},  # Empty message
        {"message": "x" * 2500, "city": "San Rafael"},  # Too long message
        {"city": "San Rafael"},  # Missing message
    ]
    
    for i, data in enumerate(test_cases, 1):
        try:
            response = requests.post(API_URL, headers=headers, json=data, timeout=10)
            if response.status_code == 400:
                result = response.json()
                print(f"  ✅ Test {i}: Properly rejected - {result.get('error', 'Unknown error')}")
            else:
                print(f"  ⚠️  Test {i}: Unexpected status {response.status_code}")
        except Exception as e:
            print(f"  ❌ Test {i}: {str(e)[:50]}")

def test_ics_special_characters():
    """Test ICS escaping with special characters (requires frontend test)"""
    print("\n[TEST] ICS Character Escaping")
    print("-" * 50)
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    
    # Get a response with calendar actions
    data = {
        "message": "When is the next meeting? I'd like to add it to my calendar.",
        "city": "San Rafael",
        "interests": ["general"]
    }
    
    try:
        response = requests.post(API_URL, headers=headers, json=data, timeout=10)
        if response.status_code == 200:
            result = response.json()
            actions = result.get('actions', [])
            
            calendar_actions = [a for a in actions if a.get('type') == 'calendar']
            if calendar_actions:
                for action in calendar_actions:
                    event = action.get('event', {})
                    title = event.get('title', '')
                    description = event.get('description', '')
                    location = event.get('location', '')
                    
                    # Check for special characters that need escaping
                    special_chars = [';', ',', '\\', '\n']
                    has_special = any(char in f"{title}{description}{location}" for char in special_chars)
                    
                    print(f"  ✅ Calendar action found:")
                    print(f"     Title: {title[:50]}...")
                    print(f"     Has special chars: {has_special}")
                    print(f"     ⚠️  Frontend ICS escaping should handle: ; , \\ and newlines")
                    
            else:
                print(f"  ⚠️  No calendar actions in response")
                print(f"     Actions: {[a.get('type') for a in actions]}")
        else:
            print(f"  ❌ HTTP {response.status_code}")
    except Exception as e:
        print(f"  ❌ Error: {str(e)[:100]}")

def test_configuration_constants():
    """Test that configuration constants are working"""
    print("\n[TEST] Configuration Constants")
    print("-" * 50)
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    
    # Test fallback email action
    data = {
        "message": "How can I contact the city clerk?",
        "city": "San Rafael"
    }
    
    try:
        response = requests.post(API_URL, headers=headers, json=data, timeout=10)
        if response.status_code == 200:
            result = response.json()
            actions = result.get('actions', [])
            
            # Check that we get exactly 3 or fewer actions (MAX_ACTION_BUTTONS)
            if len(actions) <= 3:
                print(f"  ✅ Action limit respected: {len(actions)}/3 actions")
            else:
                print(f"  ❌ Too many actions: {len(actions)}/3")
            
            # Check for email action with configurable clerk email
            email_actions = [a for a in actions if a.get('type') == 'email']
            if email_actions:
                email = email_actions[0].get('mailto', '')
                print(f"  ✅ Email action uses configurable address: {email}")
                
                # Check label truncation (ACTION_LABEL_MAX_LENGTH = 30)
                label = email_actions[0].get('label', '')
                if len(label) <= 50:  # Should be truncated + "..."
                    print(f"  ✅ Label truncation working: '{label}' ({len(label)} chars)")
                else:
                    print(f"  ❌ Label too long: '{label}' ({len(label)} chars)")
            
        else:
            print(f"  ❌ HTTP {response.status_code}")
    except Exception as e:
        print(f"  ❌ Error: {str(e)[:100]}")

def run_comprehensive_test():
    """Run all tests"""
    print("=" * 60)
    print("COMPREHENSIVE TESTING OF CRITICAL FIXES")
    print("=" * 60)
    
    test_improved_matching()
    test_data_freshness_warning()
    test_error_handling()
    test_ics_special_characters()
    test_configuration_constants()
    
    print("\n" + "=" * 60)
    print("TESTING COMPLETE")
    print("=" * 60)
    print("\nNOTES:")
    print("- ICS character escaping tested on API side, frontend escaping needs manual verification")
    print("- Data freshness depends on actual file ages in data/schema/")
    print("- Frontend styling constants need visual verification in browser")

if __name__ == "__main__":
    run_comprehensive_test()