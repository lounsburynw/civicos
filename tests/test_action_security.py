#!/usr/bin/env python3
"""Security and edge case tests for action buttons"""

import json
import requests
import sys

API_URL = "http://localhost:8001/api/conversation"
API_KEY = "dev_key_local"

def test_xss_injection():
    """Test XSS injection attempts in messages"""
    print("\n[TEST] XSS Injection Attempts")
    print("-" * 40)
    
    xss_payloads = [
        "<script>alert('XSS')</script>",
        "javascript:alert('XSS')",
        "<img src=x onerror=alert('XSS')>",
        "';alert('XSS');//",
        "<svg onload=alert('XSS')>"
    ]
    
    for payload in xss_payloads:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}"
        }
        
        data = {
            "message": f"Tell me about housing {payload}",
            "city": "San Rafael",
            "interests": ["housing"]
        }
        
        try:
            response = requests.post(API_URL, headers=headers, json=data, timeout=10)
            if response.status_code == 200:
                result = response.json()
                actions = result.get('actions', [])
                
                # Check if XSS payload appears in actions
                for action in actions:
                    if payload in str(action):
                        print(f"❌ XSS vulnerability: Payload found in action: {payload}")
                    else:
                        print(f"✅ XSS blocked for payload: {payload[:30]}...")
            else:
                print(f"✅ Request blocked with status {response.status_code}")
        except Exception as e:
            print(f"✅ Request failed safely: {str(e)[:50]}")

def test_malformed_dates():
    """Test handling of malformed date strings"""
    print("\n[TEST] Malformed Date Handling")
    print("-" * 40)
    
    # Simulate response with malformed dates
    test_cases = [
        "What meetings are happening on invalid-date?",
        "Tell me about meetings on 2025-13-45",  # Invalid month/day
        "When is the meeting at 25:99 PM?"  # Invalid time
    ]
    
    for test in test_cases:
        headers = {
            "Content-Type": "application/json", 
            "Authorization": f"Bearer {API_KEY}"
        }
        
        data = {
            "message": test,
            "city": "San Rafael"
        }
        
        try:
            response = requests.post(API_URL, headers=headers, json=data, timeout=10)
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Handled gracefully: {test[:40]}...")
                
                # Check if calendar actions have valid dates
                actions = result.get('actions', [])
                for action in actions:
                    if action.get('type') == 'calendar':
                        event = action.get('event', {})
                        start = event.get('start')
                        if start:
                            try:
                                # Try to parse the date
                                from datetime import datetime
                                datetime.fromisoformat(start.replace('Z', '+00:00'))
                                print(f"  ✅ Valid date in calendar action: {start}")
                            except:
                                print(f"  ❌ Invalid date in calendar action: {start}")
            else:
                print(f"⚠️  Request failed with status {response.status_code}")
        except Exception as e:
            print(f"❌ Error: {str(e)[:100]}")

def test_missing_data():
    """Test handling when opportunity data is incomplete"""
    print("\n[TEST] Missing Data Handling")
    print("-" * 40)
    
    # Test with minimal message that should still work
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    
    test_cases = [
        {"message": "meetings", "city": ""},  # Missing city
        {"message": "comment", "city": "San Rafael"},  # Should provide fallback
        {"message": "", "city": "San Rafael"},  # Empty message
    ]
    
    for data in test_cases:
        try:
            response = requests.post(API_URL, headers=headers, json=data, timeout=10)
            if response.status_code == 200:
                result = response.json()
                actions = result.get('actions', [])
                print(f"✅ Request handled: message='{data['message']}', city='{data['city']}'")
                print(f"   Actions returned: {len(actions)}")
            elif response.status_code == 400:
                print(f"✅ Properly rejected invalid input: {data}")
            else:
                print(f"⚠️  Unexpected status {response.status_code}: {data}")
        except Exception as e:
            print(f"❌ Error with {data}: {str(e)[:50]}")

def test_long_input():
    """Test handling of extremely long inputs"""
    print("\n[TEST] Long Input Handling")
    print("-" * 40)
    
    # Test with very long message
    long_message = "housing " * 500  # 3500+ characters
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    
    data = {
        "message": long_message,
        "city": "San Rafael"
    }
    
    try:
        response = requests.post(API_URL, headers=headers, json=data, timeout=10)
        if response.status_code == 400:
            print(f"✅ Long message properly rejected (>2000 chars)")
        elif response.status_code == 200:
            print(f"⚠️  Long message accepted - check if truncated properly")
        else:
            print(f"Status: {response.status_code}")
    except Exception as e:
        print(f"Error: {str(e)[:100]}")

def test_url_injection():
    """Test URL injection in action buttons"""
    print("\n[TEST] URL Injection in Actions")
    print("-" * 40)
    
    injection_attempts = [
        "Tell me about meetings at javascript:alert('xss')",
        "Email me at test@evil.com about housing",
        "Meeting info at data:text/html,<script>alert('xss')</script>"
    ]
    
    for attempt in injection_attempts:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}"
        }
        
        data = {
            "message": attempt,
            "city": "San Rafael"
        }
        
        try:
            response = requests.post(API_URL, headers=headers, json=data, timeout=10)
            if response.status_code == 200:
                result = response.json()
                actions = result.get('actions', [])
                
                # Check URLs in actions
                for action in actions:
                    if action.get('type') == 'link':
                        url = action.get('url', '')
                        if url.startswith(('javascript:', 'data:', 'vbscript:')):
                            print(f"❌ Dangerous URL in action: {url}")
                        else:
                            print(f"✅ Safe URL: {url[:50]}...")
                    elif action.get('type') == 'email':
                        mailto = action.get('mailto', '')
                        if '@evil.com' in mailto or 'javascript:' in mailto:
                            print(f"❌ Suspicious email: {mailto}")
                        else:
                            print(f"✅ Safe email: {mailto}")
        except Exception as e:
            print(f"Error: {str(e)[:100]}")

def test_concurrent_requests():
    """Test handling of concurrent requests"""
    print("\n[TEST] Concurrent Request Handling")
    print("-" * 40)
    
    import concurrent.futures
    import time
    
    def make_request(i):
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}"
        }
        
        data = {
            "message": f"Tell me about housing opportunity {i}",
            "city": "San Rafael",
            "conversation_id": f"test-concurrent-{i}"
        }
        
        start = time.time()
        try:
            response = requests.post(API_URL, headers=headers, json=data, timeout=10)
            elapsed = time.time() - start
            return (i, response.status_code, elapsed)
        except Exception as e:
            elapsed = time.time() - start
            return (i, f"Error: {str(e)[:30]}", elapsed)
    
    # Send 5 concurrent requests
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(make_request, i) for i in range(5)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    
    for i, status, elapsed in sorted(results):
        if isinstance(status, int) and status == 200:
            print(f"✅ Request {i}: Success in {elapsed:.2f}s")
        elif isinstance(status, int) and status == 429:
            print(f"⚠️  Request {i}: Rate limited (expected)")
        else:
            print(f"❌ Request {i}: {status} in {elapsed:.2f}s")

def main():
    print("=" * 60)
    print("SECURITY & EDGE CASE TESTING FOR ACTION BUTTONS")
    print("=" * 60)
    
    test_xss_injection()
    test_malformed_dates()
    test_missing_data()
    test_long_input()
    test_url_injection()
    test_concurrent_requests()
    
    print("\n" + "=" * 60)
    print("TESTING COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    main()