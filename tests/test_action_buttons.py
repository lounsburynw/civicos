#!/usr/bin/env python3
"""Test action buttons in conversation API responses"""

import json
import requests
import sys

# API configuration
API_URL = "http://localhost:8001/api/conversation"
API_KEY = "dev_key_local"

def test_conversation_with_actions(message, interests=None):
    """Test conversation endpoint and display response with actions"""
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    
    payload = {
        "message": message,
        "city": "San Rafael",
        "state": "California",
        "county": "Marin County",
        "interests": interests or []
    }
    
    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        print("\n" + "="*60)
        print(f"QUERY: {message}")
        print("="*60)
        print(f"\nRESPONSE:\n{data.get('response', 'No response')}")
        
        actions = data.get('actions', [])
        if actions:
            print(f"\n✅ ACTION BUTTONS ({len(actions)}):")
            for i, action in enumerate(actions, 1):
                print(f"\n  {i}. Type: {action.get('type')}")
                print(f"     Label: {action.get('label')}")
                if action.get('type') == 'email':
                    print(f"     To: {action.get('mailto')}")
                    print(f"     Subject: {action.get('subject', 'N/A')}")
                elif action.get('type') == 'calendar':
                    event = action.get('event', {})
                    print(f"     Event: {event.get('title')}")
                    print(f"     Date: {event.get('start')}")
                elif action.get('type') == 'link':
                    print(f"     URL: {action.get('url')}")
        else:
            print("\n⚠️  No action buttons returned")
            
        return data
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Error: {e}")
        return None

def main():
    print("Testing Civic Conversation API with Action Buttons")
    print("="*60)
    
    # Test 1: General housing query
    test_conversation_with_actions(
        "What housing events are available?",
        ["housing"]
    )
    
    # Test 2: Specific action request with keywords
    test_conversation_with_actions(
        "I want to comment on the Electric Bicycle Safety Regulations. How can I email my comments?",
        ["transportation", "safety"]
    )
    
    # Test 3: Meeting attendance request
    test_conversation_with_actions(
        "When is the next meeting about housing? I'd like to attend.",
        ["housing"]
    )
    
    # Test 4: General participation
    test_conversation_with_actions(
        "How can I contact the city about development issues?",
        ["housing", "development"]
    )

if __name__ == "__main__":
    main()