#!/usr/bin/env python3
"""
Conversation Service - MCP-powered conversational intelligence for Civic OS

Bridges static frontend responses with MCP server tools for natural conversation flow.
Uses existing schema entities (Message, MessageAction, ConversationContext).
"""

import json
import os
import sys
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path

# Add mcp-civic-server to path for importing MCP tools
sys.path.append(str(Path(__file__).parent / "mcp-civic-server"))

# Try to import MCP tools, fallback if not available
try:
    from civic_server import compose_public_comment, get_comment_guidelines
    MCP_TOOLS_AVAILABLE = True
except ImportError:
    MCP_TOOLS_AVAILABLE = False
    
    # Fallback implementations
    def compose_public_comment(item_id: str, item_title: str, 
                              resident_stance: Optional[str] = None,
                              key_points: Optional[str] = None) -> str:
        """Fallback comment composer when MCP not available"""
        stance_text = f"I {resident_stance or 'am commenting on'}" 
        return f"""Dear Council Members,

{stance_text} the proposal: {item_title}.

{key_points or 'I believe this issue deserves careful consideration for our community.'}

Thank you for your time and consideration.

Sincerely,
A Concerned Resident"""
    
    def get_comment_guidelines(jurisdiction: str = "san-rafael") -> str:
        """Fallback guidelines when MCP not available"""
        return """Public Comment Guidelines:

EMAIL: Send comments to clerk@cityofsanrafael.org
DEADLINE: Submit by 5:00 PM on meeting day
FORMAT: Include your name and address
TIME LIMIT: 3 minutes for in-person comments

For more information, visit the city website."""

# Configure logging before using logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Now check and report MCP availability after logger is configured
if not MCP_TOOLS_AVAILABLE:
    logger.warning("MCP tools not available - using fallback implementations")

class ConversationService:
    """
    MCP-powered conversation service that transforms static responses 
    into dynamic, context-aware civic conversations.
    """
    
    def __init__(self, enable_mcp: bool = True):
        """
        Initialize conversation service
        
        Args:
            enable_mcp: Feature flag - use MCP tools vs static fallback
        """
        self.enable_mcp = enable_mcp
        self.civic_opportunities = []
        self.user_profiles = {}  # In-memory user storage (production: use database)
        
        # Load civic events from existing schema data
        self._load_civic_opportunities()
    
    def _load_civic_opportunities(self):
        """Load civic events from schema output directory"""
        schema_dir = Path(__file__).parent / "output" / "schema"
        
        if not schema_dir.exists():
            logger.warning("Schema directory not found - no civic events loaded")
            return
        
        # Load all schema files
        for schema_file in schema_dir.glob("*.json"):
            try:
                with open(schema_file, 'r') as f:
                    data = json.load(f)
                    if "civic_opportunities" in data:
                        self.civic_opportunities.extend(data["civic_opportunities"])
                        logger.info(f"Loaded {len(data['civic_opportunities'])} events from {schema_file.name}")
            except Exception as e:
                logger.error(f"Error loading {schema_file}: {e}")
    
    def handle_conversation(self, 
                                user_message: str, 
                                user_profile: Dict[str, Any],
                                conversation_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Handle user message and return schema-compliant response
        
        Args:
            user_message: User's chat input
            user_profile: CivicProfile entity from schema
            conversation_context: ConversationContext entity from schema
            
        Returns:
            Response containing Message and MessageAction entities
        """
        try:
            # Update user interaction tracking
            self._update_user_activity(user_profile)
            
            # Initialize conversation context if needed
            if not conversation_context:
                conversation_context = self._create_conversation_context(user_message, user_profile)
            else:
                conversation_context = self._update_conversation_context(conversation_context, user_message)
            
            # Generate response based on user experience and MCP capability
            if self.enable_mcp:
                response = self._generate_mcp_response(user_message, user_profile, conversation_context)
            else:
                response = self._generate_static_response(user_message, user_profile, conversation_context)
            
            return {
                "message": response["message"],
                "actions": response["actions"],
                "conversation_context": conversation_context
            }
            
        except Exception as e:
            logger.error(f"Conversation handling error: {e}")
            return self._generate_error_response()
    
    def _update_user_activity(self, user_profile: Dict[str, Any]):
        """Update user activity tracking"""
        user_profile["last_active"] = datetime.now().isoformat()
        user_profile["civic_profile"]["interactions"] += 1
        
        # Update experience level based on interactions
        interactions = user_profile["civic_profile"]["interactions"]
        visits = user_profile["civic_profile"]["visits"]
        
        if interactions >= 8 and visits >= 3:
            user_profile["experience_level"] = "expert"
        elif visits >= 2:
            user_profile["experience_level"] = "returning"
    
    def _create_conversation_context(self, message: str, user_profile: Dict[str, Any]) -> Dict[str, Any]:
        """Create initial conversation context from user message"""
        message_lower = message.lower()
        
        # Detect civic issues mentioned
        civic_issues = []
        issue_keywords = {
            "housing": ["housing", "rent", "apartment", "development"],
            "traffic": ["traffic", "parking", "transportation", "roads"],
            "environment": ["environment", "climate", "pollution", "green"],
            "budget": ["budget", "tax", "spending", "finance"],
            "education": ["school", "education", "learning", "students"]
        }
        
        for issue, keywords in issue_keywords.items():
            if any(keyword in message_lower for keyword in keywords):
                civic_issues.append(issue)
        
        return {
            "current_topic": self._extract_topic(message),
            "civic_issues_mentioned": civic_issues,
            "user_goals": self._extract_user_goals(message_lower),
            "related_opportunities": self._find_related_opportunities(civic_issues),
            "conversation_phase": "engagement",
            "message_count": 1
        }
    
    def _update_conversation_context(self, context: Dict[str, Any], message: str) -> Dict[str, Any]:
        """Update existing conversation context with new message"""
        context["current_topic"] = self._extract_topic(message)
        context["message_count"] = context.get("message_count", 0) + 1
        
        # Update conversation phase based on message count and content
        message_lower = message.lower()
        if any(word in message_lower for word in ["yes", "tell me more", "interested"]):
            context["conversation_phase"] = "action_planning"
        elif any(word in message_lower for word in ["draft", "comment", "submit"]):
            context["conversation_phase"] = "civic_action"
        
        return context
    
    def _extract_topic(self, message: str) -> str:
        """Extract main topic from user message"""
        message_lower = message.lower()
        
        # Topic detection keywords
        if any(word in message_lower for word in ["planning", "development", "zoning"]):
            return "urban_planning"
        elif any(word in message_lower for word in ["budget", "tax", "spending"]):
            return "municipal_budget"
        elif any(word in message_lower for word in ["traffic", "transportation", "parking"]):
            return "transportation"
        elif any(word in message_lower for word in ["environment", "climate", "green"]):
            return "environment"
        else:
            return "general_civic"
    
    def _extract_user_goals(self, message_lower: str) -> List[str]:
        """Extract user goals from message"""
        goals = []
        
        if any(word in message_lower for word in ["learn", "understand", "know"]):
            goals.append("learn_about_issue")
        if any(word in message_lower for word in ["participate", "get involved", "help"]):
            goals.append("civic_participation")
        if any(word in message_lower for word in ["comment", "submit", "draft"]):
            goals.append("submit_public_comment")
        if any(word in message_lower for word in ["meeting", "attend", "when"]):
            goals.append("attend_meeting")
        
        return goals
    
    def _find_related_opportunities(self, civic_issues: List[str]) -> List[str]:
        """Find civic events related to mentioned issues"""
        related = []
        
        for opportunity in self.civic_opportunities:
            # Match by tags or title keywords
            opp_text = (opportunity.get("title", "") + " " + 
                       " ".join(opportunity.get("tags", []))).lower()
            
            for issue in civic_issues:
                if issue in opp_text:
                    related.append(opportunity.get("id", ""))
                    break
        
        return related[:3]  # Limit to 3 most relevant
    
    def _generate_mcp_response(self, 
                                   message: str, 
                                   user_profile: Dict[str, Any], 
                                   context: Dict[str, Any]) -> Dict[str, Any]:
        """Generate response using MCP tools for natural conversation"""
        
        # Determine if user wants to compose a comment
        message_lower = message.lower()
        wants_comment = any(word in message_lower for word in ["draft", "comment", "write", "compose"])
        
        if wants_comment and context["related_opportunities"]:
            # Use MCP compose_public_comment tool
            opportunity_id = context["related_opportunities"][0]
            opportunity = self._get_opportunity_by_id(opportunity_id)
            
            if opportunity:
                try:
                    # Call MCP tool
                    draft_comment = compose_public_comment(
                        item_id=opportunity["id"],
                        item_title=opportunity["title"],
                        resident_stance=self._infer_stance(message),
                        key_points=self._extract_key_points(message)
                    )
                    
                    return {
                        "message": {
                            "id": str(uuid.uuid4()),
                            "role": "assistant",
                            "content": f"I've drafted a public comment for you:\n\n{draft_comment}\n\nWould you like me to help you submit this or make any changes?",
                            "timestamp": datetime.now().isoformat(),
                            "metadata": {
                                "mcp_tool_used": "compose_public_comment",
                                "opportunity_id": opportunity_id
                            }
                        },
                        "actions": [
                            {
                                "id": str(uuid.uuid4()),
                                "label": "Get Submission Guidelines",
                                "action_type": "mcp_tool_call",
                                "mcp_tool": "get_comment_guidelines",
                                "mcp_parameters": {"jurisdiction": "san-rafael"}
                            },
                            {
                                "id": str(uuid.uuid4()),
                                "label": "Revise Comment",
                                "action_type": "draft_comment",
                                "parameters": {"opportunity_id": opportunity_id}
                            }
                        ]
                    }
                except Exception as e:
                    logger.error(f"MCP tool error: {e}")
                    return self._generate_static_response(message, user_profile, context)
        
        # Handle guidelines request
        if any(word in message_lower for word in ["guidelines", "how to submit", "submission"]):
            try:
                guidelines = get_comment_guidelines("san-rafael")
                return {
                    "message": {
                        "id": str(uuid.uuid4()),
                        "role": "assistant", 
                        "content": f"Here are the submission guidelines:\n\n{guidelines}",
                        "timestamp": datetime.now().isoformat(),
                        "metadata": {
                            "mcp_tool_used": "get_comment_guidelines"
                        }
                    },
                    "actions": []
                }
            except Exception as e:
                logger.error(f"MCP guidelines error: {e}")
                return self._generate_static_response(message, user_profile, context)
        
        # Default: Enhanced static response with MCP context
        return self._generate_contextual_response(message, user_profile, context)
    
    def _generate_static_response(self, 
                                message: str, 
                                user_profile: Dict[str, Any], 
                                context: Dict[str, Any]) -> Dict[str, Any]:
        """Generate static response (fallback when MCP disabled)"""
        
        experience = user_profile.get("experience_level", "new")
        message_lower = message.lower()
        
        # Simple keyword-based responses
        if any(word in message_lower for word in ["hello", "hi", "hey"]):
            content = f"Hello! I'm here to help you engage with local civic issues in {user_profile.get('location', {}).get('city', 'your city')}."
        elif any(word in message_lower for word in ["help", "what can you do"]):
            content = "I can help you find civic events, draft public comments, and connect with local government. What interests you?"
        elif context["related_opportunities"]:
            opp = self._get_opportunity_by_id(context["related_opportunities"][0])
            content = f"I found a relevant civic opportunity: {opp['title'] if opp else 'Local meeting'}. Would you like to learn more?"
        else:
            content = "I'm here to help you participate in local government. You can ask me about meetings, comment drafting, or civic issues."
        
        # Experience-based actions
        actions = []
        if experience == "new":
            actions.append({
                "id": str(uuid.uuid4()),
                "label": "Show Me Opportunities",
                "action_type": "quick_start"
            })
        elif experience == "expert":
            actions.extend([
                {
                    "id": str(uuid.uuid4()),
                    "label": "Draft Comment",
                    "action_type": "draft_comment",
                    "style": "primary"
                },
                {
                    "id": str(uuid.uuid4()),
                    "label": "View Impact Dashboard", 
                    "action_type": "view_impact",
                    "experience_gate": "expert"
                }
            ])
        
        return {
            "message": {
                "id": str(uuid.uuid4()),
                "role": "assistant",
                "content": content,
                "timestamp": datetime.now().isoformat(),
                "metadata": {
                    "response_type": "static_fallback"
                }
            },
            "actions": actions
        }
    
    def _generate_contextual_response(self, 
                                    message: str, 
                                    user_profile: Dict[str, Any], 
                                    context: Dict[str, Any]) -> Dict[str, Any]:
        """Generate enhanced contextual response using conversation context"""
        
        # Use context to provide more relevant responses
        topic = context.get("current_topic", "general_civic")
        issues = context.get("civic_issues_mentioned", [])
        phase = context.get("conversation_phase", "engagement")
        
        if phase == "action_planning" and context["related_opportunities"]:
            opportunity = self._get_opportunity_by_id(context["related_opportunities"][0])
            content = f"Perfect! Here's how you can participate in {opportunity['title'] if opportunity else 'this opportunity'}:\n\n"
            content += "• Submit written comments before the meeting\n"
            content += "• Attend virtually or in-person\n" 
            content += "• Connect with neighbors who share your interests\n\n"
            content += "Would you like me to help draft a comment?"
            
            actions = [
                {
                    "id": str(uuid.uuid4()),
                    "label": "Draft My Comment",
                    "action_type": "mcp_tool_call",
                    "mcp_tool": "compose_public_comment",
                    "mcp_parameters": {
                        "item_id": opportunity["id"] if opportunity else "general",
                        "item_title": opportunity["title"] if opportunity else "Civic Issue"
                    },
                    "style": "primary"
                },
                {
                    "id": str(uuid.uuid4()),
                    "label": "Get Guidelines",
                    "action_type": "mcp_tool_call", 
                    "mcp_tool": "get_comment_guidelines"
                }
            ]
        else:
            # General contextual response
            if issues:
                content = f"I see you're interested in {', '.join(issues)}. "
                content += f"There are {len(context['related_opportunities'])} related civic events coming up. "
                content += "Would you like to see what's available?"
            else:
                content = "I'm here to help you engage with local civic issues. What would you like to explore?"
            
            actions = [
                {
                    "id": str(uuid.uuid4()),
                    "label": "Show Opportunities",
                    "action_type": "quick_start"
                }
            ]
        
        return {
            "message": {
                "id": str(uuid.uuid4()),
                "role": "assistant",
                "content": content,
                "timestamp": datetime.now().isoformat(),
                "metadata": {
                    "response_type": "contextual",
                    "conversation_context": context
                }
            },
            "actions": actions
        }
    
    def _generate_error_response(self) -> Dict[str, Any]:
        """Generate error response following schema"""
        return {
            "message": {
                "id": str(uuid.uuid4()),
                "role": "assistant",
                "content": "I'm having trouble processing that right now. Please try again, or ask me about civic events in your area.",
                "timestamp": datetime.now().isoformat(),
                "metadata": {
                    "response_type": "error"
                }
            },
            "actions": [
                {
                    "id": str(uuid.uuid4()),
                    "label": "Try Again",
                    "action_type": "quick_start"
                }
            ],
            "conversation_context": {}
        }
    
    # Helper methods
    def _get_opportunity_by_id(self, opportunity_id: str) -> Optional[Dict[str, Any]]:
        """Get civic opportunity by ID"""
        for opp in self.civic_opportunities:
            if opp.get("id") == opportunity_id:
                return opp
        return None
    
    def _infer_stance(self, message: str) -> Optional[str]:
        """Infer user's stance from message content"""
        message_lower = message.lower()
        
        if any(word in message_lower for word in ["support", "favor", "like", "agree"]):
            return "support"
        elif any(word in message_lower for word in ["oppose", "against", "disagree", "concern"]):
            return "oppose"
        elif any(word in message_lower for word in ["question", "unclear", "more info"]):
            return "question"
        else:
            return None
    
    def _extract_key_points(self, message: str) -> Optional[str]:
        """Extract key points from user message for comment drafting"""
        # Simple extraction - in production, use more sophisticated NLP
        sentences = message.split('.')
        key_sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
        
        if key_sentences:
            return '\n'.join(key_sentences[:3])  # Limit to 3 key points
        return None

# Service instance for import
conversation_service = ConversationService(enable_mcp=os.getenv("CIVIC_MCP_ENABLED", "true").lower() == "true")