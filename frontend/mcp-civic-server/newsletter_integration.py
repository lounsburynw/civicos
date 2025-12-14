#!/usr/bin/env python3
"""
Newsletter Integration for MCP Civic Engagement Tools
Enhances existing civic_digest.py newsletters with action buttons
"""

import sys
import re
from pathlib import Path
from urllib.parse import urlencode
import uuid

# Add parent directory to import civic_digest
sys.path.append(str(Path(__file__).parent.parent))

def add_action_buttons_to_newsletter(newsletter_html: str, base_url: str = "http://localhost:8000") -> str:
    """
    Add MCP action buttons to existing newsletter HTML
    
    Args:
        newsletter_html: Original newsletter HTML from civic_digest.py
        base_url: Base URL for the MCP web interface
        
    Returns:
        Enhanced newsletter HTML with action buttons
    """
    
    # Pattern to find agenda items in the newsletter
    # Looks for sections like "### Plain-English Title"
    item_pattern = r'### ([^#\n]+)\n- \*\*Change:\*\* ([^\n]+)\n- \*\*Impact:\*\* ([^\n]+)\n- \*\*Action:\*\* ([^\n]+)'
    
    enhanced_html = newsletter_html
    
    def add_buttons_to_item(match):
        title = match.group(1).strip()
        change = match.group(2).strip() 
        impact = match.group(3).strip()
        action = match.group(4).strip()
        
        # Generate unique item ID
        item_id = f"item-{uuid.uuid4().hex[:8]}"
        
        # Extract meeting info from newsletter (simplified for demo)
        meeting_date = "TBD"  # Would extract from newsletter header
        meeting_type = "City Council"  # Would extract from newsletter
        source_url = ""  # Would extract from newsletter
        
        # Create action button URL
        button_params = {
            'item_id': item_id,
            'title': title,
            'meeting_date': meeting_date,
            'meeting_type': meeting_type,
            'source_url': source_url
        }
        
        comment_url = f"{base_url}/demo?" + urlencode(button_params)
        
        # Create enhanced item HTML with action buttons
        enhanced_item = f"""
### {title}
- **Change:** {change}
- **Impact:** {impact}  
- **Action:** {action}

<div style="background: #f0f7ff; padding: 15px; border-radius: 6px; margin: 15px 0; border-left: 4px solid #2196f3;">
<strong>🎯 Take Action:</strong><br>
<a href="{comment_url}" style="display: inline-block; background: #2c5aa0; color: white; padding: 8px 16px; text-decoration: none; border-radius: 4px; margin: 5px 5px 5px 0;">
📝 Draft Comment
</a>
<a href="#" style="display: inline-block; background: #28a745; color: white; padding: 8px 16px; text-decoration: none; border-radius: 4px; margin: 5px;">
📅 Add to Calendar  
</a>
<a href="#" style="display: inline-block; background: #6c757d; color: white; padding: 8px 16px; text-decoration: none; border-radius: 4px; margin: 5px;">
💡 Guidelines
</a>
</div>
        """
        
        return enhanced_item
    
    # Replace agenda items with enhanced versions
    enhanced_html = re.sub(item_pattern, add_buttons_to_item, enhanced_html)
    
    return enhanced_html

def create_enhanced_newsletter_demo():
    """Create a demo of enhanced newsletter with action buttons"""
    
    # Sample newsletter content (similar to civic_digest.py output)
    sample_newsletter = """
# ✉️ San Rafael City Council 
*Your quick guide to what's on the City Council agenda — Monday September 2, 2024*

## 🗣️ How to Participate  
- **Meeting:** [Monday September 2 at 7:00 PM](https://calendar.google.com/calendar/...) 📅
- **Where:** City Council Chambers, 1400 Fifth Avenue
- **Watch Online:** [Live Stream](https://sanrafael.org/live)
- **Call In:** (415) 555-0123, Meeting ID: 12345
- **Email Comments:** clerk@cityofsanrafael.org — **deadline:** 5:00 PM Monday
- **Attend & Speak:** Public comment allowed - 3 minutes per person
- **Full Agenda:** [View original meeting agenda](https://example.com/agenda)

## 🚨 What's on the Agenda

### Affordable Housing Project - 1234 Main St
- **Change:** City considering approval of 50-unit affordable housing development
- **Impact:** Could provide housing for teachers, firefighters, and working families. Construction would begin Spring 2025.
- **Action:** Email clerk@cityofsanrafael.org by 5 PM Monday or attend meeting to speak during public comment

### Downtown Parking Meter Expansion  
- **Change:** Proposed expansion of paid parking meters to include Third Street and Fourth Street
- **Impact:** Would affect 200 parking spaces, $2/hour rates. Revenue estimated at $150,000 annually for street maintenance.
- **Action:** Public input welcome via email or in-person comment at meeting

## ✅ Bottom Line
Two major items affecting housing and downtown access. Public input encouraged on both issues.

⚡ *Independent and nonpartisan summary. Facts only; no spin.*
    """
    
    # Add action buttons to the newsletter
    enhanced = add_action_buttons_to_newsletter(sample_newsletter)
    
    return enhanced

def test_integration_with_civic_digest():
    """Test integration with actual civic_digest.py system"""
    try:
        from civic_digest import CivicDigest
        
        # Create instance of existing system
        digest = CivicDigest()
        
        print("✅ Successfully imported civic_digest.py")
        print("✅ CivicDigest class accessible")
        print("✅ Ready for integration")
        
        return True
        
    except ImportError as e:
        print(f"❌ Could not import civic_digest: {e}")
        return False
    except Exception as e:
        print(f"❌ Error testing integration: {e}")
        return False

if __name__ == "__main__":
    print("🔗 MCP Newsletter Integration Demo")
    print("="*50)
    
    # Test integration
    if test_integration_with_civic_digest():
        print("\n✅ Integration test passed")
    else:
        print("\n⚠️ Integration test failed - but MCP tools still work independently")
    
    # Create enhanced newsletter demo
    print("\n📧 Creating enhanced newsletter demo...")
    enhanced = create_enhanced_newsletter_demo()
    
    # Save demo for viewing
    demo_file = Path(__file__).parent / "enhanced_newsletter_demo.html"
    
    html_wrapper = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Enhanced Civic Newsletter Demo</title>
    <style>
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            max-width: 600px; 
            margin: 40px auto; 
            padding: 20px;
            line-height: 1.6;
        }}
        h1 {{ color: #2c5aa0; }}
        h2 {{ color: #1e3d72; }}
        h3 {{ color: #333; }}
        a {{ color: #2c5aa0; }}
        pre {{ background: #f8f9fa; padding: 15px; border-radius: 6px; overflow-x: auto; }}
    </style>
</head>
<body>
    <pre>{enhanced}</pre>
</body>
</html>
    """
    
    with open(demo_file, 'w') as f:
        f.write(html_wrapper)
    
    print(f"✅ Demo saved to: {demo_file}")
    print(f"🌐 Open in browser to see enhanced newsletter with action buttons")
    print(f"🎯 Action buttons link to MCP comment tools at http://localhost:8000")
    
    print("\n📋 Next Steps:")
    print("1. Modify civic_digest.py to use add_action_buttons_to_newsletter()")
    print("2. Test with real San Rafael meeting data")
    print("3. Launch A/B test: enhanced vs current newsletter")
    print("4. Measure conversion rates and civic participation increase")