#!/usr/bin/env python3
"""
Simple HTTP server to demonstrate the MCP civic engagement UI
Uses built-in Python HTTP server - no dependencies needed
"""

import http.server
import socketserver
import json
import urllib.parse
import sys
import os
from pathlib import Path
import datetime
import uuid

# Add parent directory to path to import civic_server and validator
sys.path.append(str(Path(__file__).parent.parent))
from civic_server import compose_public_comment, get_comment_guidelines
from civic_input_validator import validate_civic_input

# Simple analytics storage (in production, use proper database)
ANALYTICS_FILE = Path(__file__).parent / "analytics.json"

def load_analytics():
    """Load analytics data from file"""
    if ANALYTICS_FILE.exists():
        try:
            with open(ANALYTICS_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {"sessions": [], "events": []}

def save_analytics(data):
    """Save analytics data to file"""
    try:
        with open(ANALYTICS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Analytics save error: {e}")

def track_event(event_type, data=None):
    """Track an analytics event"""
    analytics = load_analytics()
    
    event = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.datetime.now().isoformat(),
        "type": event_type,
        "data": data or {}
    }
    
    analytics["events"].append(event)
    
    # Keep only last 1000 events to prevent file from growing too large
    analytics["events"] = analytics["events"][-1000:]
    
    save_analytics(analytics)
    return event["id"]

class CivicEngagementHandler(http.server.SimpleHTTPRequestHandler):
    
    def do_GET(self):
        """Handle GET requests"""
        if self.path == '/':
            track_event("page_view", {"page": "index"})
            self.serve_index()
        elif self.path.startswith('/comment-form'):
            track_event("page_view", {"page": "comment_form"})
            self.serve_comment_form()
        elif self.path.startswith('/demo'):
            # Parse parameters to track newsletter integration usage
            parsed_url = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed_url.query)
            
            is_from_newsletter = len(params) > 0
            track_event("page_view", {
                "page": "demo", 
                "from_newsletter": is_from_newsletter,
                "item_id": params.get('item_id', [None])[0],
                "meeting_type": params.get('meeting_type', [None])[0]
            })
            
            self.serve_demo()
        elif self.path == '/analytics':
            self.serve_analytics()
        else:
            super().do_GET()
    
    def do_POST(self):
        """Handle POST requests for API endpoints"""
        if self.path == '/api/generate-draft':
            self.handle_generate_draft()
        else:
            self.send_error(404)
    
    def serve_index(self):
        """Serve the index page"""
        html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MCP Civic Engagement Demo</title>
    <style>
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 700px; 
            margin: 40px auto; 
            padding: 20px;
            background: #f8f9fa;
            line-height: 1.6;
        }
        .container {
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .header { 
            background: linear-gradient(135deg, #2c5aa0 0%, #1e3d72 100%);
            color: white; 
            padding: 25px; 
            border-radius: 8px;
            text-align: center;
            margin-bottom: 25px;
        }
        .demo-link { 
            display: inline-block; 
            background: #2c5aa0; 
            color: white; 
            padding: 14px 28px; 
            text-decoration: none; 
            border-radius: 6px; 
            margin: 15px 0;
            font-weight: 600;
            transition: background 0.2s;
        }
        .demo-link:hover {
            background: #1e3d72;
        }
        .info { 
            background: #e3f2fd; 
            padding: 20px; 
            border-radius: 6px; 
            margin: 20px 0;
            border-left: 4px solid #2196f3;
        }
        .status { 
            background: #e8f5e8; 
            padding: 20px; 
            border-radius: 6px; 
            margin: 20px 0;
            border-left: 4px solid #4caf50;
        }
        .goals { 
            background: #fff3e0; 
            padding: 20px; 
            border-radius: 6px; 
            margin: 20px 0;
            border-left: 4px solid #ff9800;
        }
        .icon { font-style: normal; margin-right: 8px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1><span class="icon">🏛</span>MCP Civic Engagement Demo</h1>
            <p>AI-powered tools to help residents participate in local government</p>
        </div>
        
        <div class="info">
            <h3><span class="icon">🎯</span>How It Works</h3>
            <ol>
                <li><strong>Newsletter Alert:</strong> Receive digest about upcoming city meetings</li>
                <li><strong>Click Action Button:</strong> "Draft Comment" on issues you care about</li>
                <li><strong>AI Assists:</strong> System generates professional comment draft</li>
                <li><strong>Review & Edit:</strong> Personalize the draft with your input</li>
                <li><strong>One-Click Send:</strong> Email directly to city officials</li>
            </ol>
        </div>
        
        <div style="text-align: center;">
            <a href="/demo" class="demo-link">
                <span class="icon">🧪</span>Try Demo Comment Form
            </a>
        </div>
        
        <div class="status">
            <h3><span class="icon">✅</span>Current Status</h3>
            <ul>
                <li>MCP server running with comment composition tools</li>
                <li>Web UI for realistic user experience testing</li>
                <li>Integration framework ready for existing newsletter system</li>
                <li>Professional comment templates for San Rafael</li>
            </ul>
        </div>

        <div class="goals">
            <h3><span class="icon">📊</span>Development Goals</h3>
            <ul>
                <li><strong>Current:</strong> Less than 1% of newsletter readers take civic action</li>
                <li><strong>Target:</strong> 5-10% conversion with bi-directional MCP tools</li>
                <li><strong>Success:</strong> Measurable increase in public comments and meeting attendance</li>
                <li><strong>Vision:</strong> Transform from "civic newsletter" to "participation infrastructure"</li>
            </ul>
        </div>
    </div>
</body>
</html>"""
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))
    
    def serve_demo(self):
        """Serve progressive disclosure comment form with URL parameter support"""
        
        # Parse URL parameters for newsletter integration
        from urllib.parse import urlparse, parse_qs
        parsed_url = urlparse(self.path)
        params = parse_qs(parsed_url.query)
        
        # Extract parameters with defaults
        item_id = params.get('item_id', ['demo-2024-1'])[0]
        item_title = params.get('title', ['Affordable Housing Project - 1234 Main St'])[0]
        meeting_date = params.get('meeting_date', ['TBD'])[0]
        meeting_type = params.get('meeting_type', ['City Council'])[0]
        source_url = params.get('source_url', [''])[0]
        
        # Format meeting info
        meeting_info = f"{meeting_type}"
        if meeting_date != 'TBD':
            meeting_info += f" - {meeting_date}"
        
        # Build the source URL link if provided
        source_link = ""
        if source_url:
            source_link = f'<p style="font-size: 14px; margin-top: 10px;"><a href="{source_url}" target="_blank" style="color: #ccc;">📋 View Original Agenda</a></p>'
        
        # Generate timestamp for aggressive cache busting
        import time
        cache_buster = str(int(time.time()))
        
        html = """
<!DOCTYPE html>
<html>
<head>
    <title>🚀 ULTRA-MODERN Civic Voice Tool v2.0</title>
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <meta http-equiv="Pragma" content="no-cache">
    <meta http-equiv="Expires" content="0">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="cache-buster" content=""" + cache_buster + """>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        /* 🚀 ULTRA-MODERN CSS Variables - Dramatic Visual Update */
        :root {
            --electric-purple: #8b5cf6;
            --electric-blue: #3b82f6;
            --electric-cyan: #06b6d4;
            --electric-green: #10b981;
            --electric-pink: #ec4899;
            --electric-orange: #f59e0b;
            --ultra-dark: #0f0f23;
            --glass-white: rgba(255, 255, 255, 0.95);
            --glass-light: rgba(255, 255, 255, 0.1);
            --neon-glow: 0 0 20px currentColor;
            --shadow-xl: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
            --gradient-electric: linear-gradient(135deg, #8b5cf6 0%, #3b82f6 50%, #06b6d4 100%);
            --gradient-dark: linear-gradient(135deg, #0f0f23 0%, #1e1b4b 100%);
        }
        
        body { 
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif; 
            max-width: 700px; 
            margin: 0 auto; 
            padding: 20px; 
            color: white;
            line-height: 1.7;
            background: var(--gradient-dark);
            min-height: 100vh;
            position: relative;
            overflow-x: hidden;
        }
        
        /* Animated Background Particles */
        body::before {
            content: '';
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: radial-gradient(circle at 20% 50%, rgba(139, 92, 246, 0.1) 0%, transparent 50%),
                        radial-gradient(circle at 80% 20%, rgba(59, 130, 246, 0.1) 0%, transparent 50%),
                        radial-gradient(circle at 40% 80%, rgba(6, 182, 212, 0.1) 0%, transparent 50%);
            z-index: -1;
            animation: pulse 4s ease-in-out infinite alternate;
        }
        
        @keyframes pulse {{
            0% {{ opacity: 0.5; }}
            100% {{ opacity: 0.8; }}
        }}
        
        .header { 
            background: var(--gradient-electric); 
            color: white; 
            padding: 40px; 
            border-radius: 24px; 
            margin-bottom: 40px;
            box-shadow: var(--shadow-xl), var(--neon-glow);
            border: 2px solid var(--glass-light);
            backdrop-filter: blur(20px);
            position: relative;
            overflow: hidden;
            text-align: center;
        }
        
        .header::before {
            content: '';
            position: absolute;
            top: -50%;
            left: -50%;
            width: 200%;
            height: 200%;
            background: linear-gradient(45deg, transparent, rgba(255,255,255,0.1), transparent);
            animation: shine 3s ease-in-out infinite;
            z-index: 0;
        }
        
        @keyframes shine {{
            0% {{ transform: translateX(-100%) translateY(-100%) rotate(30deg); }}
            100% {{ transform: translateX(100%) translateY(100%) rotate(30deg); }}
        }}
        
        .header > * {
            position: relative;
            z-index: 1;
        }
        
        .header h1 {
            font-size: 36px;
            font-weight: 800;
            margin: 0 0 16px 0;
            text-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
            background: linear-gradient(45deg, #ffffff 0%, #f0f9ff 50%, #dbeafe 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            letter-spacing: -0.025em;
        }
        
        .header p {
            font-size: 18px;
            font-weight: 400;
            opacity: 0.95;
            margin: 0;
        }
        
        /* Trust indicators */
        .trust-bar {
            background: #e8f5e8;
            padding: 12px 20px;
            border-radius: 6px;
            margin-bottom: 20px;
            display: flex;
            justify-content: center;
            flex-wrap: wrap;
            gap: 20px;
            font-size: 14px;
            color: #2d5016;
            border-left: 4px solid #4caf50;
        }
        .trust-item {
            display: flex;
            align-items: center;
            gap: 6px;
        }
        
        /* Value proposition */
        .value-prop {
            background: #f0f7ff;
            padding: 16px 20px;
            border-radius: 6px;
            margin-bottom: 25px;
            border-left: 4px solid #2196f3;
            text-align: center;
        }
        .value-prop h3 {
            margin: 0 0 8px 0;
            color: #1565c0;
            font-size: 16px;
        }
        .value-prop p {
            margin: 0;
            color: #666;
            font-size: 14px;
            line-height: 1.4;
        }
        
        /* Progress indicator */
        .progress-bar { 
            background: #e0e0e0; 
            height: 6px; 
            border-radius: 3px; 
            margin-bottom: 25px; 
            overflow: hidden;
        }
        .progress-fill { 
            background: #2c5aa0; 
            height: 100%; 
            width: 33.33%; 
            transition: width 0.3s ease;
            border-radius: 3px;
        }
        .step-indicator {
            display: flex;
            justify-content: space-between;
            margin-bottom: 20px;
            font-size: 14px;
            color: #666;
        }
        .step { padding: 0 10px; }
        .step.active { color: #2c5aa0; font-weight: bold; }
        .step.completed { color: #4caf50; }
        
        /* 🎯 ULTRA-MODERN Glass Card Containers */
        .step-container { 
            display: none;
            background: var(--glass-white);
            border-radius: 20px;
            box-shadow: var(--shadow-xl);
            padding: 40px;
            margin: 32px 0;
            border: 1px solid var(--glass-light);
            backdrop-filter: blur(20px);
            color: var(--ultra-dark);
            position: relative;
            overflow: hidden;
        }
        
        .step-container::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 4px;
            background: var(--gradient-electric);
            z-index: 1;
        }
        .step-container.active { 
            display: block;
            animation: slideInUp 0.3s ease-out;
        }
        
        /* Slide-in animation */
        @keyframes slideInUp {{
            from {{ opacity: 0; transform: translateY(20px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        
        .form-group { margin-bottom: 20px; }
        .form-title { 
            font-size: 18px; 
            font-weight: bold; 
            margin-bottom: 10px; 
            color: #333; 
        }
        .form-subtitle { 
            color: #666; 
            margin-bottom: 15px; 
            line-height: 1.4;
        }
        
        /* 🎆 ELECTRIC Stance Selection */
        .stance-grid { 
            display: grid; 
            grid-template-columns: repeat(2, 1fr); 
            gap: 20px; 
            margin-top: 24px; 
        }
        
        .stance-option { 
            background: linear-gradient(135deg, rgba(255,255,255,0.1) 0%, rgba(255,255,255,0.05) 100%);
            padding: 24px; 
            border-radius: 16px; 
            cursor: pointer; 
            text-align: center;
            border: 2px solid var(--glass-light);
            transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
            font-size: 17px;
            font-weight: 600;
            min-height: 80px;
            display: flex;
            flex-direction: column;
            justify-content: center;
            position: relative;
            backdrop-filter: blur(10px);
            color: white;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
        }
        .stance-option:hover:not(.selected) { 
            border-color: var(--electric-purple);
            box-shadow: 0 12px 40px rgba(139, 92, 246, 0.4), var(--neon-glow);
            transform: translateY(-4px) scale(1.02);
            background: linear-gradient(135deg, var(--electric-purple) 0%, var(--electric-blue) 100%);
        }
        
        .stance-option.selected { 
            border-color: var(--electric-cyan);
            background: var(--gradient-electric);
            color: white;
            font-weight: 700;
            box-shadow: 0 12px 40px rgba(6, 182, 212, 0.5), var(--neon-glow);
            transform: translateY(-4px) scale(1.05);
            text-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
        }
        
        .stance-option.selected::after {
            content: '✨';
            position: absolute;
            top: 8px;
            right: 12px;
            font-size: 20px;
            animation: sparkle 2s ease-in-out infinite;
        }
        
        @keyframes sparkle {{
            0%, 100% {{ opacity: 1; transform: scale(1); }}
            50% {{ opacity: 0.7; transform: scale(1.1); }}
        }}
        
        /* Modern textarea styling */
        textarea { 
            width: 100%; 
            padding: 16px; 
            border: 2px solid var(--neutral-200); 
            border-radius: 8px; 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
            font-size: 16px;
            line-height: 1.5;
            box-sizing: border-box;
            resize: vertical;
            min-height: 120px;
            background: var(--neutral-100);
            transition: all 0.2s ease;
        }
        textarea:focus {
            border-color: var(--primary);
            background: white;
            box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
            outline: none;
        }
        
        /* 💫 HYPER-DRAMATIC Modern buttons */
        .btn { 
            background: var(--gradient-electric);
            color: white; 
            padding: 20px 40px; 
            border: none; 
            border-radius: 16px; 
            cursor: pointer; 
            font-size: 18px;
            font-weight: 800;
            letter-spacing: 0.025em;
            text-transform: uppercase;
            transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
            box-shadow: var(--shadow-xl), var(--neon-glow);
            position: relative;
            overflow: hidden;
            min-height: 64px;
            display: flex;
            align-items: center;
            justify-content: center;
            border: 2px solid var(--glass-light);
        }
        
        .btn::before {
            content: '';
            position: absolute;
            top: 0;
            left: -100%;
            width: 100%;
            height: 100%;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.3), transparent);
            transition: left 0.6s;
        }
        
        .btn:hover::before {
            left: 100%;
        }
        .btn:hover:not(:disabled) { 
            transform: translateY(-6px) scale(1.02);
            box-shadow: 0 20px 60px rgba(139, 92, 246, 0.5), var(--neon-glow);
            background: linear-gradient(135deg, var(--electric-pink) 0%, var(--electric-purple) 50%, var(--electric-blue) 100%);
        }
        .btn:active:not(:disabled) {
            transform: translateY(0);
        }
        .btn:disabled { 
            background: linear-gradient(135deg, rgba(100, 116, 139, 0.5) 0%, rgba(71, 85, 105, 0.5) 100%);
            cursor: not-allowed;
            transform: none;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
            opacity: 0.6;
        }
        
        .btn-secondary {
            background: white;
            color: var(--neutral-600);
            border: 2px solid var(--neutral-200);
            margin-right: 12px;
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
        }
        .btn-secondary:hover:not(:disabled) { 
            background: var(--neutral-100);
            border-color: var(--neutral-600);
            transform: translateY(-1px);
            box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1);
        }
        
        .button-group { 
            display: flex; 
            justify-content: space-between; 
            align-items: center;
            margin-top: 25px;
        }
        
        /* Result styling */
        .result { 
            background: #f8f9fa; 
            padding: 25px; 
            border: 2px solid #ddd; 
            border-radius: 8px; 
            margin-top: 20px;
            white-space: pre-wrap;
            font-family: Georgia, serif;
            line-height: 1.6;
        }
        .result-header {
            background: #e8f5e8;
            padding: 15px;
            border-radius: 6px;
            margin-bottom: 15px;
            border-left: 4px solid #4caf50;
        }
        
        /* Enhanced Mobile Experience */
        @media (max-width: 768px) {
            body { 
                padding: 16px; 
                padding-bottom: 120px; /* Account for sticky button */
                background: #f8fafc;
            }
            .stance-grid { 
                grid-template-columns: 1fr; 
                gap: 12px; 
            }
            .stance-option {
                min-height: 60px; /* Larger touch targets */
                padding: 24px;
                font-size: 18px;
            }
            .button-group { 
                position: fixed;
                bottom: 0;
                left: 0;
                right: 0;
                background: white;
                padding: 16px 20px;
                border-top: 1px solid var(--neutral-200);
                box-shadow: 0 -2px 10px rgba(0, 0, 0, 0.1);
                gap: 12px;
            }
            .btn {
                width: 100%;
                padding: 16px 24px;
                font-size: 18px;
                font-weight: 700;
            }
            .btn-secondary {
                width: 100%;
                margin-right: 0;
                margin-bottom: 8px;
            }
            .trust-bar {
                flex-direction: column;
                gap: 8px;
                text-align: center;
            }
            .step-container {
                padding: 24px;
                margin: 16px 0;
            }
        }
        
        @media (max-width: 480px) {
            .header h1 { font-size: 20px; }
            .form-title { font-size: 16px; }
            textarea { font-size: 16px; } /* Prevent zoom on iOS */
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🚀 YOUR VOICE, AMPLIFIED BY AI</h1>
        <p style="font-size: 20px; font-weight: 500; margin: 16px 0;">Transform Your Thoughts Into Professional Civic Impact</p>
        <div style="background: rgba(255,255,255,0.15); padding: 16px; border-radius: 12px; margin-top: 20px; backdrop-filter: blur(10px);">
            <strong style="font-size: 18px;">🏢 """ + meeting_info + ": " + item_title + """</strong>
        </div>
        """ + source_link + """
    </div>
    
    <div class="trust-bar">
        <div class="trust-item">
            <span>🔒</span>
            <span>Your data stays private</span>
        </div>
        <div class="trust-item">
            <span>🏛</span>
            <span>Nonpartisan civic tool</span>
        </div>
        <div class="trust-item">
            <span>✅</span>
            <span>Trusted by local residents</span>
        </div>
    </div>
    
    <div class="value-prop">
        <h3>⏱ Takes 3-4 minutes • Get a professional comment that makes your voice heard</h3>
        <p>AI helps you craft a well-structured comment that city officials will read and consider. Your input shapes local decisions.</p>
    </div>
    
    <div class="step-indicator" style="display: flex; justify-content: center; gap: 40px; margin: 32px 0; font-weight: 600;">
        <div class="step active" id="step-indicator-1" style="color: var(--electric-cyan); font-size: 18px;">🎯 1. Your Voice</div>
        <div class="step" id="step-indicator-2" style="color: rgba(255,255,255,0.5); font-size: 18px;">🤖 2. AI Magic</div>
    </div>
    
    <div class="progress-bar">
        <div class="progress-fill" id="progress-fill"></div>
    </div>
    
    <form id="commentForm">
        <!-- Step 1: Combined Position and Key Points -->
        <div class="step-container active" id="step-1">
            <div class="form-title" style="font-size: 24px; font-weight: 700; margin-bottom: 12px; color: var(--ultra-dark); background: var(--gradient-electric); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;">🎯 What's Your Take?</div>
            <div class="form-subtitle" style="font-size: 18px; color: rgba(15, 15, 35, 0.8); margin-bottom: 24px; font-weight: 500;">Your perspective shapes the future of your community. Choose your stance and share your thoughts:</div>
            
            <div style="margin-bottom: 28px;">
                <div style="font-weight: 600; margin-bottom: 12px; color: var(--neutral-800);">How do you feel about it?</div>
                <div class="stance-grid">
                    <div class="stance-option" data-stance="support" onclick="selectStance(this, 'support')">
                        <div style="font-size: 20px; margin-bottom: 8px;">🎆</div>
                        <div><strong>I'M ALL FOR IT</strong></div>
                        <div style="font-size: 14px; margin-top: 8px; opacity: 0.9;">This sounds amazing to me</div>
                    </div>
                    <div class="stance-option" data-stance="oppose" onclick="selectStance(this, 'oppose')">
                        <div style="font-size: 20px; margin-bottom: 8px;">⚡</div>
                        <div><strong>I HAVE CONCERNS</strong></div>
                        <div style="font-size: 14px; margin-top: 8px; opacity: 0.9;">I see some serious problems</div>
                    </div>
                    <div class="stance-option" data-stance="question" onclick="selectStance(this, 'question')">
                        <div style="font-size: 20px; margin-bottom: 8px;">🔍</div>
                        <div><strong>NEED MORE INFO</strong></div>
                        <div style="font-size: 14px; margin-top: 8px; opacity: 0.9;">I have burning questions</div>
                    </div>
                    <div class="stance-option" data-stance="neutral" onclick="selectStance(this, 'neutral')">
                        <div style="font-size: 20px; margin-bottom: 8px;">🤔</div>
                        <div><strong>IT'S COMPLICATED</strong></div>
                        <div style="font-size: 14px; margin-top: 8px; opacity: 0.9;">I see multiple angles here</div>
                    </div>
                </div>
            </div>
            
            <div class="form-group">
                <label for="keyPoints" style="font-weight: 600; margin-bottom: 12px; color: var(--neutral-800); display: block;">Tell us what matters to you</label>
                <div style="font-size: 15px; color: var(--neutral-600); margin-bottom: 12px; line-height: 1.4;">Just jot down your thoughts - one per line. AI will turn them into a polished comment.</div>
                <textarea id="keyPoints" rows="5" placeholder="What's on your mind? For example:
• This would help my kids' teachers afford to live here
• Love the transit access - I could bike to work  
• Hope they include playground space for families
• Worried about finding parking on game days"></textarea>
                <div style="font-size: 13px; color: var(--neutral-600); margin-top: 8px; display: flex; align-items: center; gap: 6px;"><span>💡</span><span>2-5 points usually work best</span></div>
            </div>
            
            <div class="button-group">
                <div></div>
                <button type="button" class="btn" id="next-to-step-2" disabled>🤖 TRANSFORM MY VOICE →</button>
            </div>
        </div>
        
        <!-- Step 2: Review and Generate -->
        <div class="step-container" id="step-2">
            <div class="form-title" style="font-size: 24px; font-weight: 700; margin-bottom: 12px; color: var(--ultra-dark); background: var(--gradient-electric); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;">🤖 Ready for AI Magic?</div>
            <div class="form-subtitle" style="font-size: 18px; color: rgba(15, 15, 35, 0.8); margin-bottom: 24px; font-weight: 500;">Watch AI transform your thoughts into a compelling, professional comment that city officials will read and remember.</div>
            
            <div style="background: #f0f7ff; padding: 20px; border-radius: 8px; border-left: 4px solid #2196f3; margin-bottom: 20px;">
                <div style="font-weight: bold; margin-bottom: 10px;">Your selections:</div>
                <div id="summary-stance"></div>
                <div id="summary-points" style="margin-top: 10px;"></div>
            </div>
            
            <div style="background: #fff3e0; padding: 16px; border-radius: 6px; border-left: 4px solid #ff9800; margin-bottom: 20px;">
                <div style="font-weight: bold; margin-bottom: 8px;">📋 What happens next:</div>
                <ul style="margin: 0; padding-left: 20px; font-size: 14px; line-height: 1.5;">
                    <li>AI generates a professional 150-250 word comment</li>
                    <li>You can edit and personalize the draft</li>
                    <li>Copy and email to city officials before the deadline</li>
                    <li>Your voice will be part of the official record</li>
                </ul>
            </div>
            
            <div class="button-group">
                <button type="button" class="btn-secondary btn" id="back-to-step-1">← Edit My Input</button>
                <button type="submit" class="btn">🎯 Generate My Professional Comment</button>
            </div>
        </div>
        
        <input type="hidden" id="stance">
    </form>
    
    <div id="result" class="result" style="display: none;"></div>
    
    <script>
        document.addEventListener('DOMContentLoaded', function() {
            let currentStep = 1;
            let selectedStance = null;
            
            // Step navigation
            function showStep(stepNum) {
                // Hide all steps
                document.querySelectorAll('.step-container').forEach(el => {
                    el.classList.remove('active');
                });
                
                // Show current step
                document.getElementById(`step-${stepNum}`).classList.add('active');
                
                // Update step indicators
                document.querySelectorAll('.step').forEach(el => {
                    el.classList.remove('active', 'completed');
                });
                
                for (let i = 1; i <= 2; i++) {
                    const indicator = document.getElementById(`step-indicator-${i}`);
                    if (i < stepNum) {
                        indicator.classList.add('completed');
                    } else if (i === stepNum) {
                        indicator.classList.add('active');
                    }
                }
                
                // Update progress bar
                const progressFill = document.getElementById('progress-fill');
                progressFill.style.width = `${(stepNum / 2) * 100}%`;
                
                currentStep = stepNum;
            }
        
        // Stance selection function (called by onclick)
        window.selectStance = function(element, stance) {
            console.log('Stance clicked:', stance);
            selectedStance = stance;
            
            // Update UI
            document.querySelectorAll('.stance-option').forEach(el => {
                el.classList.remove('selected');
            });
            element.classList.add('selected');
            
            // Store value
            document.getElementById('stance').value = selectedStance;
            
            // Check if we can enable the button
            checkFormCompletion();
            console.log('Continue button state updated');
        };
        
        // Check if both stance and key points are filled
        function checkFormCompletion() {
            const hasStance = selectedStance !== null;
            const hasKeyPoints = document.getElementById('keyPoints').value.trim().length > 0;
            const nextButton = document.getElementById('next-to-step-2');
            
            if (nextButton) {
                nextButton.disabled = !(hasStance && hasKeyPoints);
            }
        }
        
        // Key points validation
        document.getElementById('keyPoints').addEventListener('input', function() {
            checkFormCompletion();
        });
        
        // Navigation buttons
        document.getElementById('next-to-step-2').addEventListener('click', function() {
            if (selectedStance && document.getElementById('keyPoints').value.trim()) {
                // Update summary
                const stanceLabels = {
                    'support': '✅ Support - I am in favor of this',
                    'oppose': '❌ Oppose - I have concerns about this',
                    'question': '❓ Question - I need more information',
                    'neutral': '💭 Neutral Input - Balanced perspective'
                };
                
                document.getElementById('summary-stance').innerHTML = 
                    `<strong>Position:</strong> ${stanceLabels[selectedStance]}`;
                
                const keyPoints = document.getElementById('keyPoints').value.trim();
                const points = keyPoints.split('\\n').filter(p => p.trim()).slice(0, 5);
                document.getElementById('summary-points').innerHTML = 
                    `<strong>Key Points:</strong><br>• ${points.join('<br>• ')}`;
                
                showStep(2);
            }
        });
        
        document.getElementById('back-to-step-1').addEventListener('click', function() {
            showStep(1);
        });
        
        // Form submission
        document.getElementById('commentForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const keyPoints = document.getElementById('keyPoints').value;
            
            if (!selectedStance || !keyPoints) {
                alert('Please complete all steps');
                return;
            }
            
            // Show enhanced loading state
            const submitBtn = e.target.querySelector('button[type="submit"]');
            const originalText = submitBtn.innerHTML;
            submitBtn.innerHTML = '<span style="display: flex; align-items: center; justify-content: center; gap: 8px;"><span class="spinner">⏳</span>AI is writing your comment...</span>';
            submitBtn.disabled = true;
            
            // Add CSS for spinner animation
            const style = document.createElement('style');
            style.textContent = `
                .spinner {
                    animation: spin 1s linear infinite;
                }
                @keyframes spin {{
                    from {{ transform: rotate(0deg); }}
                    to {{ transform: rotate(360deg); }}
                }}
            `;
            document.head.appendChild(style);
            
            try {
                const response = await fetch('/api/generate-draft', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        item_id: """ + json.dumps(item_id) + """,
                        item_title: """ + json.dumps(item_title) + """,
                        stance: selectedStance,
                        key_points: keyPoints
                    })
                });
                
                const result = await response.json();
                
                if (result.success) {
                    // Show enhanced success message
                    const resultDiv = document.getElementById('result');
                    resultDiv.innerHTML = `
                        <div class="result-header" style="text-align: center; margin-bottom: 20px;">
                            <div style="font-size: 24px; margin-bottom: 8px;">🎉</div>
                            <strong style="color: #2e7d32; font-size: 18px;">Your Professional Comment is Ready!</strong><br>
                            <small style="color: #666;">📊 ${result.word_count} words • ${result.char_count} characters • Perfect length for city council</small>
                        </div>
                        <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; border: 2px solid #e0e0e0; font-family: Georgia, serif; line-height: 1.6; white-space: pre-wrap;">${result.draft}</div>
                        <div style="background: #e3f2fd; padding: 16px; border-radius: 6px; margin-top: 20px; border-left: 4px solid #2196f3;">
                            <div style="font-weight: bold; margin-bottom: 8px;">📧 Next Steps:</div>
                            <ol style="margin: 0; padding-left: 20px; font-size: 14px; line-height: 1.5;">
                                <li><strong>Copy your comment</strong> (select all text above)</li>
                                <li><strong>Email to:</strong> clerk@cityofsanrafael.org</li>
                                <li><strong>Subject:</strong> Public Comment - ${result.item_title || 'Agenda Item'}</li>
                                <li><strong>Include your name and address</strong> in the email</li>
                            </ol>
                            <div style="margin-top: 12px; padding: 8px; background: rgba(76, 175, 80, 0.1); border-radius: 4px; font-size: 13px;">
                                💡 <strong>Tip:</strong> Send before the deadline to ensure your voice is heard at the meeting!
                            </div>
                        </div>
                    `;
                    resultDiv.style.display = 'block';
                    
                    // Add celebration animation
                    setTimeout(() => {
                        resultDiv.scrollIntoView({ behavior: 'smooth' });
                    }, 100);
                } else {
                    alert('Error generating comment: ' + result.error);
                }
            } catch (error) {
                alert('Network error: ' + error.message);
            } finally {
                submitBtn.innerHTML = originalText;
                submitBtn.disabled = false;
            }
        });
        
        }); // End DOMContentLoaded
    </script>
</body>
</html>
        """
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))
    
    def handle_generate_draft(self):
        """
        Handle draft generation API request with comprehensive input validation.
        
        SECURITY: This endpoint implements critical input validation to prevent
        XSS, SQL injection, command injection, and prompt injection attacks.
        """
        data = None
        try:
            # Parse request data with size limits to prevent DoS
            content_length = int(self.headers.get('Content-Length', 0))
            
            # SECURITY: Limit request size to prevent DoS attacks
            if content_length > 50000:  # 50KB limit
                self.send_error(413, "Request entity too large")
                return
            
            if content_length == 0:
                self.send_error(400, "Empty request body")
                return
            
            post_data = self.rfile.read(content_length)
            
            try:
                data = json.loads(post_data.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                self.send_error(400, f"Invalid JSON: {str(e)}")
                return
            
            # SECURITY: Validate all input parameters before processing
            is_valid, sanitized_data, error_message = validate_civic_input(data)
            
            if not is_valid:
                logger.warning(f"Input validation failed from {self.client_address[0]}: {error_message}")
                track_event("validation_failure", {
                    "client_ip": self.client_address[0],
                    "error": error_message,
                    "data_keys": list(data.keys()) if data else []
                })
                
                response = {
                    'success': False, 
                    'error': f'Input validation failed: {error_message}'
                }
                self.send_response(400)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps(response).encode('utf-8'))
                return
            
            # Use sanitized data for all subsequent operations
            logger.info(f"Input validation passed for request from {self.client_address[0]}")
            
            # Track comment generation start with sanitized data
            track_event("comment_generation_start", {
                "item_id": sanitized_data.get('item_id', 'unknown'),
                "item_title": sanitized_data.get('item_title', 'unknown')[:50],
                "stance": sanitized_data.get('stance', 'unknown'),
                "key_points_length": len(sanitized_data.get('key_points', '')),
                "client_ip": self.client_address[0]
            })
            
            # Use MCP server to generate draft with sanitized inputs
            try:
                draft = compose_public_comment(
                    item_id=sanitized_data.get('item_id', ''),
                    item_title=sanitized_data.get('item_title', ''),
                    resident_stance=sanitized_data.get('stance'),
                    key_points=sanitized_data.get('key_points')
                )
            except ValueError as ve:
                # Handle validation errors from the MCP server
                logger.error(f"MCP server validation failed: {str(ve)}")
                track_event("mcp_validation_error", {
                    "error": str(ve),
                    "item_id": sanitized_data.get('item_id', 'unknown')
                })
                
                response = {'success': False, 'error': 'Comment generation failed validation'}
                self.send_response(400)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps(response).encode('utf-8'))
                return
            
            # Validate generated content before sending response
            if not draft or len(draft.strip()) < 20:
                logger.error("Generated draft is suspiciously short or empty")
                response = {'success': False, 'error': 'Failed to generate valid comment'}
                self.send_response(500)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps(response).encode('utf-8'))
                return
            
            word_count = len(draft.split())
            char_count = len(draft)
            
            # SECURITY: Validate output metrics are reasonable
            if word_count > 1000 or char_count > 10000:
                logger.warning(f"Generated content is unusually long: {word_count} words, {char_count} chars")
            
            # Track successful comment generation
            track_event("comment_generation_success", {
                "item_id": sanitized_data.get('item_id', 'unknown'),
                "item_title": sanitized_data.get('item_title', 'unknown')[:50], 
                "stance": sanitized_data.get('stance', 'unknown'),
                "word_count": word_count,
                "char_count": char_count,
                "ai_generated": "Dear Council Members" in draft or word_count > 100,
                "client_ip": self.client_address[0]
            })
            
            response = {
                'success': True,
                'draft': draft,
                'word_count': word_count,
                'char_count': char_count,
                'item_title': sanitized_data.get('item_title', '')  # Include sanitized title for frontend
            }
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('X-Content-Type-Options', 'nosniff')  # Security header
            self.send_header('X-Frame-Options', 'DENY')  # Security header
            self.end_headers()
            self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))
            
        except Exception as e:
            # Track failed comment generation with detailed error info
            error_details = {
                "error": str(e),
                "error_type": type(e).__name__,
                "client_ip": self.client_address[0],
                "item_id": data.get('item_id', 'unknown') if data else 'unknown'
            }
            
            logger.error(f"Comment generation failed: {error_details}")
            track_event("comment_generation_error", error_details)
            
            response = {
                'success': False, 
                'error': 'An internal error occurred while generating your comment'
            }
            self.send_response(500)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode('utf-8'))
    
    def serve_analytics(self):
        """Serve analytics dashboard"""
        analytics = load_analytics()
        
        # Calculate key metrics
        events = analytics.get("events", [])
        
        # Conversion funnel metrics
        page_views = [e for e in events if e["type"] == "page_view"]
        demo_views = [e for e in page_views if e["data"].get("page") == "demo"]
        newsletter_views = [e for e in demo_views if e["data"].get("from_newsletter")]
        comment_starts = [e for e in events if e["type"] == "comment_generation_start"]
        comment_successes = [e for e in events if e["type"] == "comment_generation_success"]
        
        # Calculate conversion rates
        total_views = len(demo_views)
        newsletter_conversion = len(newsletter_views) / max(total_views, 1) * 100
        generation_rate = len(comment_starts) / max(total_views, 1) * 100
        success_rate = len(comment_successes) / max(len(comment_starts), 1) * 100
        
        # Popular stances
        stances = {}
        for event in comment_successes:
            stance = event["data"].get("stance", "unknown")
            stances[stance] = stances.get(stance, 0) + 1
        
        # Average comment quality
        word_counts = [e["data"].get("word_count", 0) for e in comment_successes]
        avg_words = sum(word_counts) / max(len(word_counts), 1)
        
        html = """
<!DOCTYPE html>
<html>
<head>
    <title>Civic Engagement Analytics</title>
    <style>
        body {{ 
            font-family: system-ui; 
            max-width: 900px; 
            margin: 20px auto; 
            padding: 20px; 
            background: #f5f5f5;
        }}
        .header {{ 
            background: #2c5aa0; 
            color: white; 
            padding: 20px; 
            border-radius: 8px; 
            margin-bottom: 25px; 
            text-align: center;
        }}
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .metric-card {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            text-align: center;
        }}
        .metric-value {{
            font-size: 2.5em;
            font-weight: bold;
            color: #2c5aa0;
        }}
        .metric-label {{
            color: #666;
            margin-top: 8px;
        }}
        .conversion-funnel {{
            background: white;
            padding: 25px;
            border-radius: 8px;
            margin-bottom: 25px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .funnel-step {{
            display: flex;
            align-items: center;
            margin-bottom: 15px;
            padding: 15px;
            border-left: 4px solid #2c5aa0;
            background: #f8f9fa;
        }}
        .insights {{
            background: #e8f5e8;
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid #4caf50;
        }}
        .recent-events {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-top: 25px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .event {{
            padding: 10px 0;
            border-bottom: 1px solid #eee;
            font-size: 14px;
        }}
        .timestamp {{ color: #666; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 Civic Engagement Analytics</h1>
        <p>Real-time metrics for newsletter-to-action conversion</p>
    </div>
    
    <div class="metrics-grid">
        <div class="metric-card">
            <div class="metric-value">{total_views}</div>
            <div class="metric-label">Total Form Views</div>
        </div>
        <div class="metric-card">
            <div class="metric-value">{newsletter_conversion:.1f}%</div>
            <div class="metric-label">From Newsletter</div>
        </div>
        <div class="metric-card">
            <div class="metric-value">{generation_rate:.1f}%</div>
            <div class="metric-label">Conversion Rate</div>
        </div>
        <div class="metric-card">
            <div class="metric-value">{success_rate:.1f}%</div>
            <div class="metric-label">Success Rate</div>
        </div>
    </div>
    
    <div class="conversion-funnel">
        <h2>🎯 Conversion Funnel</h2>
        <div class="funnel-step">
            <div style="flex: 1;">
                <strong>Newsletter Readers</strong><br>
                <span style="color: #666;">Receive civic digest with action buttons</span>
            </div>
            <div style="font-size: 1.2em; color: #2c5aa0; font-weight: bold;">
                {len(newsletter_views)} clicks
            </div>
        </div>
        <div class="funnel-step">
            <div style="flex: 1;">
                <strong>Form Engagement</strong><br>
                <span style="color: #666;">Begin comment drafting process</span>
            </div>
            <div style="font-size: 1.2em; color: #2c5aa0; font-weight: bold;">
                {len(comment_starts)} started
            </div>
        </div>
        <div class="funnel-step">
            <div style="flex: 1;">
                <strong>Comment Generation</strong><br>
                <span style="color: #666;">Successfully generate professional draft</span>
            </div>
            <div style="font-size: 1.2em; color: #2c5aa0; font-weight: bold;">
                {len(comment_successes)} completed
            </div>
        </div>
    </div>
    
    <div class="insights">
        <h2>💡 Key Insights</h2>
        <ul>
            <li><strong>Average Comment Quality:</strong> {avg_words:.0f} words per comment (professional length)</li>
            <li><strong>Most Popular Stance:</strong> {max(stances, key=stances.get) if stances else "No data yet"}</li>
            <li><strong>Newsletter Integration:</strong> {newsletter_conversion:.1f}% of users arrive via newsletter buttons</li>
            <li><strong>System Performance:</strong> {success_rate:.1f}% AI generation success rate</li>
        </ul>
        
        <p><strong>Goal:</strong> Transform newsletter-to-action conversion from &lt;1% to 5-10%</p>
        <p><strong>Current Performance:</strong> {generation_rate:.1f}% conversion rate {"🎉 Exceeding target!" if generation_rate > 5 else "📈 Building momentum"}</p>
    </div>
    
    <div class="recent-events">
        <h2>🔄 Recent Activity</h2>
        {"".join([f'<div class="event"><strong>{e["type"].replace("_", " ").title()}:</strong> {e["data"].get("item_title", e["data"].get("page", "Unknown"))}<br><span class="timestamp">{e["timestamp"][:19].replace("T", " ")}</span></div>' for e in events[-10:]])}
    </div>
    
    <p style="text-align: center; margin-top: 30px; color: #666;">
        <a href="/">← Back to Demo</a> | 
        <a href="/demo">🎯 Try Comment Tool</a> | 
        <a href="javascript:location.reload()">🔄 Refresh Data</a>
    </p>
</body>
</html>
        """
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

if __name__ == '__main__':
    PORT = 8000
    
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    with socketserver.TCPServer(("", PORT), CivicEngagementHandler) as httpd:
        print(f"🌐 Civic Engagement UI Demo Server")
        print(f"📱 Open: http://localhost:{PORT}")
        print(f"🎯 Test the MCP comment tools in your browser")
        print(f"⚡ Press Ctrl+C to stop server")
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\\n✅ Server stopped")
            httpd.shutdown()