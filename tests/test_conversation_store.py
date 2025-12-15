"""
Tests for ConversationStore - Persistent conversation storage.

Session 79 Phase 1 - Comprehensive test coverage for conversation storage.

Tests:
- ✅ Conversation creation and retrieval
- ✅ Message storage with full OpenAI format (including tool_calls)
- ✅ Active context injection (ephemeral, not stored)
- ✅ Smart truncation for context windows
- ✅ List conversations
- ✅ Archive/unarchive
- ✅ Tool call preservation (fixes bug)
"""

import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from civic_services.conversation_store import ConversationStore


class TestConversationStore(unittest.TestCase):
    """Test ConversationStore functionality."""

    def setUp(self):
        """Create temporary database for testing."""
        self.temp_db = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.db')
        self.temp_db.close()
        self.store = ConversationStore(db_path=self.temp_db.name)

    def tearDown(self):
        """Clean up temporary database."""
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)

    # ========== Conversation Management Tests ==========

    def test_create_conversation(self):
        """Test conversation creation."""
        conv_id = self.store.create_conversation(
            user_id="test_user",
            title="Test Conversation"
        )

        self.assertTrue(conv_id.startswith("conv_"))
        self.assertEqual(len(conv_id), 21)  # conv_ + 16 hex chars

        # Verify retrieval
        conv = self.store.get_conversation(conv_id)
        self.assertIsNotNone(conv)
        self.assertEqual(conv['id'], conv_id)
        self.assertEqual(conv['user_id'], "test_user")
        self.assertEqual(conv['title'], "Test Conversation")
        self.assertFalse(conv['archived'])

    def test_get_nonexistent_conversation(self):
        """Test getting conversation that doesn't exist."""
        conv = self.store.get_conversation("nonexistent")
        self.assertIsNone(conv)

    def test_list_conversations(self):
        """Test listing conversations."""
        # Create multiple conversations
        conv1_id = self.store.create_conversation(user_id="user1", title="Conv 1")
        conv2_id = self.store.create_conversation(user_id="user1", title="Conv 2")
        conv3_id = self.store.create_conversation(user_id="user2", title="Conv 3")

        # List all conversations
        all_convs = self.store.list_conversations()
        self.assertEqual(len(all_convs), 3)

        # List by user
        user1_convs = self.store.list_conversations(user_id="user1")
        self.assertEqual(len(user1_convs), 2)

        # Verify both user1 conversations are present (order may vary due to timestamp precision)
        user1_ids = {conv['id'] for conv in user1_convs}
        self.assertIn(conv1_id, user1_ids)
        self.assertIn(conv2_id, user1_ids)

    def test_update_title(self):
        """Test updating conversation title."""
        conv_id = self.store.create_conversation(title="Old Title")
        self.store.update_title(conv_id, "New Title")

        conv = self.store.get_conversation(conv_id)
        self.assertEqual(conv['title'], "New Title")

    def test_archive_conversation(self):
        """Test archiving and unarchiving conversations."""
        conv_id = self.store.create_conversation(title="Test")

        # Archive
        self.store.archive_conversation(conv_id, archived=True)
        conv = self.store.get_conversation(conv_id)
        self.assertTrue(conv['archived'])

        # Should not appear in default list
        convs = self.store.list_conversations(archived=False)
        self.assertEqual(len(convs), 0)

        # Should appear in archived list
        archived = self.store.list_conversations(archived=True)
        self.assertEqual(len(archived), 1)

        # Unarchive
        self.store.archive_conversation(conv_id, archived=False)
        conv = self.store.get_conversation(conv_id)
        self.assertFalse(conv['archived'])

    # ========== Message Management Tests ==========

    def test_add_user_message(self):
        """Test adding user message."""
        conv_id = self.store.create_conversation()
        msg_id = self.store.add_message(
            conv_id,
            role='user',
            content='Show me housing meetings in Berkeley'
        )

        self.assertTrue(msg_id.startswith("msg_"))

        messages = self.store.get_messages(conv_id)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]['role'], 'user')
        self.assertEqual(messages[0]['content'], 'Show me housing meetings in Berkeley')

    def test_add_assistant_message_with_tool_calls(self):
        """Test adding assistant message with tool_calls (THE BUG FIX)."""
        conv_id = self.store.create_conversation()

        # Add user message
        self.store.add_message(conv_id, role='user', content='Show housing in Berkeley')

        # Add assistant message with tool_calls
        tool_calls = [{
            'id': 'call_abc123',
            'type': 'function',
            'function': {
                'name': 'search_events',
                'arguments': json.dumps({
                    'jurisdiction': 'city-berkeley',
                    'topic': 'housing'
                })
            }
        }]

        msg_id = self.store.add_message(
            conv_id,
            role='assistant',
            content='Searching for housing meetings in Berkeley',
            tool_calls=tool_calls,
            metadata={
                'model': 'gpt-4o-mini',
                'provider': 'openai',
                'tokens': 150
            }
        )

        # Verify tool_calls are stored
        messages = self.store.get_messages(conv_id)
        self.assertEqual(len(messages), 2)

        assistant_msg = messages[1]
        self.assertEqual(assistant_msg['role'], 'assistant')
        self.assertIn('tool_calls', assistant_msg)
        self.assertEqual(len(assistant_msg['tool_calls']), 1)
        self.assertEqual(assistant_msg['tool_calls'][0]['id'], 'call_abc123')
        self.assertEqual(assistant_msg['tool_calls'][0]['function']['name'], 'search_events')

    def test_add_tool_result_message(self):
        """Test adding tool result message."""
        conv_id = self.store.create_conversation()

        # Add tool result
        self.store.add_message(
            conv_id,
            role='tool',
            tool_call_id='call_abc123',
            name='search_events',
            content=json.dumps({'events': [{'id': '123', 'title': 'Housing Meeting'}]})
        )

        messages = self.store.get_messages(conv_id)
        self.assertEqual(len(messages), 1)

        tool_msg = messages[0]
        self.assertEqual(tool_msg['role'], 'tool')
        self.assertEqual(tool_msg['tool_call_id'], 'call_abc123')
        self.assertEqual(tool_msg['name'], 'search_events')

    def test_full_conversation_flow(self):
        """Test complete conversation with user -> assistant -> tool -> assistant."""
        conv_id = self.store.create_conversation(title="Housing Search")

        # 1. User message
        self.store.add_message(conv_id, role='user', content='Show housing in Berkeley')

        # 2. Assistant function call
        self.store.add_message(
            conv_id,
            role='assistant',
            content='Searching...',
            tool_calls=[{
                'id': 'call_123',
                'type': 'function',
                'function': {
                    'name': 'search_events',
                    'arguments': '{"jurisdiction": "city-berkeley", "topic": "housing"}'
                }
            }]
        )

        # 3. Tool result
        self.store.add_message(
            conv_id,
            role='tool',
            tool_call_id='call_123',
            name='search_events',
            content='{"events": [...]}'
        )

        # 4. Assistant response
        self.store.add_message(
            conv_id,
            role='assistant',
            content='Found 5 housing meetings in Berkeley'
        )

        # Verify sequence
        messages = self.store.get_messages(conv_id)
        self.assertEqual(len(messages), 4)
        self.assertEqual(messages[0]['role'], 'user')
        self.assertEqual(messages[1]['role'], 'assistant')
        self.assertIn('tool_calls', messages[1])
        self.assertEqual(messages[2]['role'], 'tool')
        self.assertEqual(messages[3]['role'], 'assistant')

    def test_conversation_with_multiple_turns(self):
        """Test multi-turn conversation (tests bug scenario)."""
        conv_id = self.store.create_conversation()

        # Turn 1: Housing in Berkeley
        self.store.add_message(conv_id, role='user', content='Show housing in Berkeley')
        self.store.add_message(
            conv_id,
            role='assistant',
            tool_calls=[{
                'id': 'call_1',
                'type': 'function',
                'function': {
                    'name': 'search_events',
                    'arguments': '{"jurisdiction": "city-berkeley", "topic": "housing"}'
                }
            }]
        )

        # Turn 2: Transportation in Oakland (different params!)
        self.store.add_message(conv_id, role='user', content='Show transportation in Oakland')
        self.store.add_message(
            conv_id,
            role='assistant',
            tool_calls=[{
                'id': 'call_2',
                'type': 'function',
                'function': {
                    'name': 'search_events',
                    'arguments': '{"jurisdiction": "city-oakland", "topic": "transportation"}'
                }
            }]
        )

        # Verify both function calls stored correctly
        messages = self.store.get_messages(conv_id)
        self.assertEqual(len(messages), 4)

        # Check Turn 1 params
        turn1_args = json.loads(messages[1]['tool_calls'][0]['function']['arguments'])
        self.assertEqual(turn1_args['jurisdiction'], 'city-berkeley')
        self.assertEqual(turn1_args['topic'], 'housing')

        # Check Turn 2 params (THIS WAS THE BUG - they would be same as Turn 1)
        turn2_args = json.loads(messages[3]['tool_calls'][0]['function']['arguments'])
        self.assertEqual(turn2_args['jurisdiction'], 'city-oakland')
        self.assertEqual(turn2_args['topic'], 'transportation')

    # ========== Active Context Injection Tests ==========

    def test_get_messages_for_llm_basic(self):
        """Test getting messages formatted for LLM."""
        conv_id = self.store.create_conversation()
        self.store.add_message(conv_id, role='user', content='Hello')
        self.store.add_message(conv_id, role='assistant', content='Hi there!')

        messages = self.store.get_messages_for_llm(conv_id)

        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]['role'], 'user')
        self.assertEqual(messages[1]['role'], 'assistant')

    def test_active_context_injection(self):
        """Test that active context is injected but NOT stored."""
        conv_id = self.store.create_conversation()
        self.store.add_message(conv_id, role='user', content='Show meetings')

        # Get messages with active context
        active_context = {
            'serialized_artifacts': '## Open Tabs\n- Event: Housing Meeting\n- Jurisdiction: Berkeley',
            'current_jurisdiction': 'city-berkeley'
        }

        messages_with_context = self.store.get_messages_for_llm(conv_id, active_context=active_context)

        # Should have: system (injected) + user
        self.assertEqual(len(messages_with_context), 2)
        self.assertEqual(messages_with_context[0]['role'], 'system')
        self.assertIn('Open Tabs', messages_with_context[0]['content'])
        self.assertEqual(messages_with_context[1]['role'], 'user')

        # Verify context NOT stored in DB
        stored_messages = self.store.get_messages(conv_id)
        self.assertEqual(len(stored_messages), 1)  # Only user message
        self.assertEqual(stored_messages[0]['role'], 'user')

    def test_system_message_preserved(self):
        """Test that system message stays at top."""
        conv_id = self.store.create_conversation()
        self.store.add_message(conv_id, role='system', content='You are a helpful assistant')
        self.store.add_message(conv_id, role='user', content='Hello')

        messages = self.store.get_messages_for_llm(conv_id)

        self.assertEqual(messages[0]['role'], 'system')
        self.assertEqual(messages[0]['content'], 'You are a helpful assistant')

    # ========== Truncation Tests ==========

    def test_truncation_preserves_recent_messages(self):
        """Test that truncation keeps recent messages."""
        conv_id = self.store.create_conversation()

        # Add many messages with substantial content
        for i in range(100):
            # Make messages longer to exceed token budget
            content = f'Message {i}: ' + ('This is a long message with lots of content. ' * 10)
            self.store.add_message(conv_id, role='user', content=content)

        # Get with small token budget
        messages = self.store.get_messages_for_llm(conv_id, max_tokens=1000)

        # Should have fewer than 100
        self.assertLess(len(messages), 100)

        # Most recent should be preserved
        last_msg = messages[-1]
        self.assertIn('Message 99', last_msg['content'])

    def test_count_conversation_tokens(self):
        """Test token counting."""
        conv_id = self.store.create_conversation()
        self.store.add_message(conv_id, role='user', content='Hello' * 100)  # ~500 chars = ~125 tokens

        token_count = self.store.count_conversation_tokens(conv_id)
        self.assertGreater(token_count, 100)
        self.assertLess(token_count, 200)

    # ========== Snapshot Tests (Phase 2+) ==========

    def test_snapshot_ui_state(self):
        """Test optional UI state snapshot capture."""
        conv_id = self.store.create_conversation()
        msg_id = self.store.add_message(conv_id, role='user', content='Test')

        # Capture UI snapshot
        ui_state = {
            'open_tabs': ['event-123'],
            'filters': {'topic': 'housing'},
            'active_artifact': 'event-123'
        }
        self.store.snapshot_ui_state(conv_id, msg_id, ui_state)

        # Retrieve snapshots
        snapshots = self.store.get_snapshots(conv_id)
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0]['message_id'], msg_id)
        self.assertEqual(snapshots[0]['snapshot_data']['open_tabs'], ['event-123'])

    def test_multiple_snapshots(self):
        """Test multiple UI snapshots over conversation."""
        conv_id = self.store.create_conversation()

        msg1_id = self.store.add_message(conv_id, role='user', content='Query 1')
        self.store.snapshot_ui_state(conv_id, msg1_id, {'tabs': 1})

        msg2_id = self.store.add_message(conv_id, role='user', content='Query 2')
        self.store.snapshot_ui_state(conv_id, msg2_id, {'tabs': 2})

        snapshots = self.store.get_snapshots(conv_id)
        self.assertEqual(len(snapshots), 2)


if __name__ == '__main__':
    unittest.main()
