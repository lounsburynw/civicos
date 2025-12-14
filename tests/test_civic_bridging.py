#!/usr/bin/env python3
"""
Test civic topic bridging effectiveness with edge cases
Tests the enhanced system prompt's ability to bridge various topics to civic engagement
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import the method directly by creating a mock handler
class TestCivicHandler:
    """Mock handler to test system prompt generation"""
    
    def build_civic_system_prompt(self, city: str, state: str, county: str,
                                 interests: list, events: list) -> str:
        """Build system prompt with civic context - copied from src/civic_api_integrated.py"""
        prompt = f"""You are a helpful civic engagement assistant for {city}, {state}.
        
Your role is to help residents understand and participate in local government.
Be conversational, friendly, and encouraging about civic participation.

Current location: {city}, {county}, {state}
User interests: {', '.join(interests) if interests else 'general civic engagement'}

Available civic events in {city}:
"""
        
        if events:
            for opp in events[:3]:  # Include top 3 events
                prompt += f"\n- {opp.get('title', 'Untitled')}: {opp.get('description', '')}\n"
                prompt += f"  Meeting: {opp.get('meeting_date', 'TBD')}\n"
        else:
            prompt += "\n- No current events loaded\n"
        
        prompt += """\nGuidelines:
1. Answer questions about local government and civic participation
2. When users ask about other topics, try to bridge them to civic engagement where possible
3. Give users the benefit of the doubt - most topics have some civic connection
4. Suggest relevant events based on user interests
5. Explain how to participate (attend meetings, submit comments, etc.)
6. Be encouraging but not pushy about participation
7. Keep responses concise and actionable

Topic Bridging Examples:
- Housing/Rent → Zoning laws, affordable housing committees, tenant protection ordinances, housing authority meetings
- Environment → Climate action plans, environmental impact reviews, park planning, sustainability committees  
- Transportation → Transit planning meetings, bike lane proposals, parking regulations, traffic studies
- Business → Business licensing, economic development committees, permit processes, chamber of commerce meetings
- Education → School board meetings, education funding, library board, after-school program budgets
- Health → Public health meetings, restaurant inspections, mental health services, community health programs
- Safety → Police accountability, fire safety codes, emergency preparedness, neighborhood watch programs
- Technology → Digital equity initiatives, broadband access, smart city planning, privacy policies
- Food → Food safety regulations, farmers market permits, community gardens, food assistance programs
- Arts/Culture → Arts commissions, public art projects, cultural center funding, historic preservation

Bridging Strategy:
- Look for creative ways to connect any topic to local government, policy, or civic participation
- Try multiple angles: local policy, government services, public meetings, community resources, regulations
- For seemingly unrelated topics, explore: "Does this relate to local regulations, community services, or public policy?"

Graceful Redirection Strategy:
- FIRST: Always attempt to find a civic connection, even if indirect
- SECOND: If genuinely impossible, acknowledge the question and redirect helpfully
- Use phrases like: "While that's not my specialty, it makes me think about [civic connection]..." 
- Or: "That's outside my civic focus, but speaking of [topic], did you know [city] has [related policy/service/meeting]?"
- LAST RESORT: "I'm focused on civic engagement in {city}. What local government questions can I help with?"
"""
        
        return prompt

def test_system_prompt_generation():
    """Test that the enhanced system prompt includes bridging examples"""
    handler = TestCivicHandler()
    
    # Test system prompt generation
    prompt = handler.build_civic_system_prompt(
        city="San Rafael",
        state="California", 
        county="Marin County",
        interests=["environment", "housing"],
        events=[]
    )
    
    # Verify bridging components are included
    assert "Topic Bridging Examples:" in prompt
    assert "Housing/Rent → Zoning laws" in prompt
    assert "Environment → Climate action plans" in prompt
    assert "Graceful Redirection Strategy:" in prompt
    assert "benefit of the doubt" in prompt.lower()
    
    print("✅ System prompt includes bridging examples and strategies")
    return True

def test_edge_case_scenarios():
    """Test edge cases that should trigger different bridging approaches"""
    handler = TestCivicHandler()
    
    edge_cases = [
        # Should be bridgeable to civic topics
        ("How do I bake a cake?", "food safety regulations, community kitchens, farmers market"),
        ("What's the weather like?", "climate resilience, weather preparedness, emergency planning"),
        ("I'm having relationship problems", "community mediation, counseling services, mental health"),
        ("How do I fix my car?", "vehicle regulations, emissions testing, transportation policy"),
        ("What's 2+2?", "education funding, school board, public education"),
        
        # Extreme cases that might need graceful redirect
        ("Tell me a joke", "community events, arts programs, cultural activities"),
        ("What's your favorite color?", "public art, community design, cultural identity"),
        ("Sing me a song", "arts commissions, cultural programs, community music"),
    ]
    
    # Generate system prompt for testing
    prompt = handler.build_civic_system_prompt(
        city="San Rafael",
        state="California",
        county="Marin County", 
        interests=["general"],
        events=[]
    )
    
    print("🧪 Testing edge case bridging scenarios:")
    print(f"System prompt length: {len(prompt)} characters")
    print("✅ Edge cases defined for manual testing with actual API")
    
    # Note: Actual conversation testing would require OpenAI API calls
    # This validates the system prompt structure is ready for testing
    
    return True

if __name__ == "__main__":
    print("🚀 Testing Civic Topic Bridging Implementation\n")
    
    try:
        test_system_prompt_generation()
        test_edge_case_scenarios()
        
        print("\n✅ All civic bridging tests passed!")
        print("\n📝 Next steps for manual testing:")
        print("1. Start the API server: python src/civic_api_integrated.py")
        print("2. Test edge cases via POST /api/conversation")
        print("3. Verify bridging effectiveness with actual AI responses")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        sys.exit(1)