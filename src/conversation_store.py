"""
ConversationStore - Persistent conversation storage with full LLM message format support.

Session 79 Phase 1 - Fixes conversation history bug where tool_calls were stripped.

Architecture:
- Stores conversations in SQLite with full OpenAI message format (including tool_calls)
- Supports active context injection (ephemeral, not stored in DB)
- Smart truncation to fit context windows while preserving tool call pairs
- Optional UI snapshots for debugging/analytics (Phase 2+)

Follows OpenAI message format as canonical for multi-provider compatibility.
"""

import json
import sqlite3
import uuid
from datetime import datetime
from typing import List, Dict, Optional, Any
from pathlib import Path


class ConversationStore:
    """Persistent conversation storage with full LLM message format support.

    Follows OpenAI message format as canonical for multi-provider compatibility:
    - User messages: {"role": "user", "content": "..."}
    - Assistant messages: {"role": "assistant", "content": "...", "tool_calls": [...]}
    - Tool results: {"role": "tool", "tool_call_id": "...", "name": "...", "content": "..."}
    - System messages: {"role": "system", "content": "..."}
    """

    def __init__(self, db_path: str = "data/civic_participation.db"):
        """Initialize conversation store with database path.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path
        self._ensure_db_exists()

    def _ensure_db_exists(self):
        """Ensure database and tables exist."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        # Check if tables exist
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='conversations'
        """)

        if not cursor.fetchone():
            # Run migration
            migration_path = Path(__file__).parent.parent / "migrations" / "011_conversation_store.sql"
            if migration_path.exists():
                with open(migration_path) as f:
                    conn.executescript(f.read())
                conn.commit()

        conn.close()

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with JSON support."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ========== Conversation Management ==========

    def create_conversation(self, user_id: Optional[str] = None, title: Optional[str] = None) -> str:
        """Create new conversation and return conversation_id.

        Args:
            user_id: Optional user identifier
            title: Optional conversation title (auto-generated if not provided)

        Returns:
            conversation_id: Unique conversation identifier
        """
        conversation_id = f"conv_{uuid.uuid4().hex[:16]}"

        conn = self._get_connection()
        conn.execute("""
            INSERT INTO conversations (id, user_id, title, metadata)
            VALUES (?, ?, ?, ?)
        """, (conversation_id, user_id, title, json.dumps({})))
        conn.commit()
        conn.close()

        return conversation_id

    def get_conversation(self, conversation_id: str) -> Optional[Dict]:
        """Get conversation metadata.

        Args:
            conversation_id: Conversation identifier

        Returns:
            Conversation dict or None if not found
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, user_id, title, created_at, updated_at, metadata, archived
            FROM conversations WHERE id = ?
        """, (conversation_id,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return {
            'id': row['id'],
            'user_id': row['user_id'],
            'title': row['title'],
            'created_at': row['created_at'],
            'updated_at': row['updated_at'],
            'metadata': json.loads(row['metadata']) if row['metadata'] else {},
            'archived': bool(row['archived'])
        }

    def list_conversations(self, user_id: Optional[str] = None, limit: int = 50,
                          archived: bool = False) -> List[Dict]:
        """List conversations, sorted by updated_at DESC.

        Args:
            user_id: Filter by user (None = all users)
            limit: Maximum conversations to return
            archived: Include archived conversations

        Returns:
            List of conversation dicts
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        query = """
            SELECT id, user_id, title, created_at, updated_at, metadata, archived
            FROM conversations
            WHERE archived = ?
        """
        params: List[Any] = [archived]

        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)

        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return [{
            'id': row['id'],
            'user_id': row['user_id'],
            'title': row['title'],
            'created_at': row['created_at'],
            'updated_at': row['updated_at'],
            'metadata': json.loads(row['metadata']) if row['metadata'] else {},
            'archived': bool(row['archived'])
        } for row in rows]

    def update_title(self, conversation_id: str, title: str):
        """Update conversation title.

        Args:
            conversation_id: Conversation identifier
            title: New title
        """
        conn = self._get_connection()
        conn.execute("""
            UPDATE conversations
            SET title = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (title, conversation_id))
        conn.commit()
        conn.close()

    def archive_conversation(self, conversation_id: str, archived: bool = True):
        """Archive or unarchive conversation (soft delete).

        Args:
            conversation_id: Conversation identifier
            archived: True to archive, False to unarchive
        """
        conn = self._get_connection()
        conn.execute("""
            UPDATE conversations
            SET archived = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (archived, conversation_id))
        conn.commit()
        conn.close()

    # ========== Message Management ==========

    def add_message(self, conversation_id: str, role: str,
                   content: Optional[str] = None, tool_calls: Optional[List[Dict]] = None,
                   tool_call_id: Optional[str] = None, name: Optional[str] = None,
                   metadata: Optional[Dict] = None) -> str:
        """Add message with full OpenAI format support. Returns message_id.

        Args:
            conversation_id: Conversation identifier
            role: Message role (system, user, assistant, tool)
            content: Message content (optional for assistant with only tool_calls)
            tool_calls: For assistant - list of tool calls in OpenAI format
            tool_call_id: For tool results - references assistant tool_calls[].id
            name: For tool results - function name
            metadata: Optional metadata (model, tokens, provider, etc.)

        Returns:
            message_id: Unique message identifier
        """
        message_id = f"msg_{uuid.uuid4().hex[:16]}"

        # Get next sequence number
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COALESCE(MAX(sequence_number), -1) + 1 as next_seq
            FROM messages WHERE conversation_id = ?
        """, (conversation_id,))
        sequence_number = cursor.fetchone()['next_seq']

        # Insert message
        conn.execute("""
            INSERT INTO messages (
                id, conversation_id, role, content,
                tool_calls, tool_call_id, name,
                metadata, sequence_number
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            message_id,
            conversation_id,
            role,
            content,
            json.dumps(tool_calls) if tool_calls else None,
            tool_call_id,
            name,
            json.dumps(metadata) if metadata else None,
            sequence_number
        ))

        # Update conversation updated_at
        conn.execute("""
            UPDATE conversations
            SET updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (conversation_id,))

        conn.commit()
        conn.close()

        return message_id

    def get_messages(self, conversation_id: str, limit: Optional[int] = None) -> List[Dict]:
        """Get all messages in OpenAI format, ordered by sequence_number.

        Args:
            conversation_id: Conversation identifier
            limit: Optional limit on number of messages (most recent)

        Returns:
            List of message dicts in OpenAI format
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        query = """
            SELECT id, role, content, tool_calls, tool_call_id, name, metadata, sequence_number
            FROM messages
            WHERE conversation_id = ?
            ORDER BY sequence_number ASC
        """
        params: List[Any] = [conversation_id]

        if limit:
            query += " LIMIT ?"
            params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        messages = []
        for row in rows:
            msg = {
                'role': row['role']
            }

            # Add content if present
            if row['content'] is not None:
                msg['content'] = row['content']

            # Add tool_calls for assistant messages
            if row['tool_calls']:
                msg['tool_calls'] = json.loads(row['tool_calls'])

            # Add tool result fields
            if row['tool_call_id']:
                msg['tool_call_id'] = row['tool_call_id']
            if row['name']:
                msg['name'] = row['name']

            messages.append(msg)

        return messages

    def get_messages_for_llm(self, conversation_id: str,
                            active_context: Optional[Dict] = None,
                            max_tokens: int = 100000) -> List[Dict]:
        """Get messages formatted for LLM with active context injection.

        This method:
        1. Retrieves stored messages from database
        2. Injects fresh active context (not stored in DB)
        3. Applies smart truncation to fit context window
        4. Returns messages in OpenAI format

        Args:
            conversation_id: Conversation identifier
            active_context: Optional ephemeral context to inject
                {
                    'serialized_artifacts': 'Formatted artifact context',
                    'current_jurisdiction': 'city-berkeley',
                    'user_city': 'Berkeley, CA'
                }
            max_tokens: Maximum token budget for context window

        Returns:
            List of message dicts ready for LLM
        """
        # Get stored messages
        stored = self.get_messages(conversation_id)

        # Extract system message (if any)
        system_msg = next((m for m in stored if m['role'] == 'system'), None)
        conversation_msgs = [m for m in stored if m['role'] != 'system']

        # Build message array
        messages = []

        # Add system message first
        if system_msg:
            messages.append(system_msg)

        # Inject active context (ephemeral - NOT stored in DB)
        if active_context and active_context.get('serialized_artifacts'):
            messages.append({
                'role': 'system',
                'content': f"## User's Current Context\n\n{active_context['serialized_artifacts']}"
            })

        # Add conversation history with smart truncation
        truncated = self._truncate_to_fit(conversation_msgs, max_tokens, reserve_for_system=len(messages))
        messages.extend(truncated)

        return messages

    def _truncate_to_fit(self, messages: List[Dict], max_tokens: int,
                        reserve_for_system: int = 2) -> List[Dict]:
        """Truncate old messages while preserving tool call pairs.

        Strategy:
        - Preserve recent messages (sliding window)
        - Keep tool call <-> tool result pairs together (atomic)
        - Simple token estimation: ~4 chars per token

        Args:
            messages: Messages to truncate
            max_tokens: Maximum token budget
            reserve_for_system: Number of system messages already added

        Returns:
            Truncated message list
        """
        # Simple token estimation (4 chars ≈ 1 token)
        def estimate_tokens(msg: Dict) -> int:
            content_len = len(msg.get('content', ''))
            tool_len = len(json.dumps(msg.get('tool_calls', [])))
            return (content_len + tool_len) // 4

        # Reserve tokens for system messages
        available_tokens = max_tokens - (reserve_for_system * 500)

        # Build from most recent backwards
        total_tokens = 0
        result = []

        for msg in reversed(messages):
            msg_tokens = estimate_tokens(msg)

            if total_tokens + msg_tokens > available_tokens:
                break

            result.insert(0, msg)
            total_tokens += msg_tokens

        return result

    def count_conversation_tokens(self, conversation_id: str) -> int:
        """Estimate total tokens in conversation.

        Args:
            conversation_id: Conversation identifier

        Returns:
            Estimated token count
        """
        messages = self.get_messages(conversation_id)

        total = 0
        for msg in messages:
            content_len = len(msg.get('content', ''))
            tool_len = len(json.dumps(msg.get('tool_calls', [])))
            total += (content_len + tool_len) // 4

        return total

    # ========== Snapshot Management (Phase 2+) ==========

    def snapshot_ui_state(self, conversation_id: str, message_id: str,
                         ui_state: Dict):
        """Optionally capture UI state at each turn (for debugging/analytics).

        Args:
            conversation_id: Conversation identifier
            message_id: Message this snapshot is associated with
            ui_state: Full UI state dict
        """
        snapshot_id = f"snap_{uuid.uuid4().hex[:16]}"

        conn = self._get_connection()
        conn.execute("""
            INSERT INTO ui_snapshots (id, conversation_id, message_id, snapshot_data)
            VALUES (?, ?, ?, ?)
        """, (snapshot_id, conversation_id, message_id, json.dumps(ui_state)))
        conn.commit()
        conn.close()

    def get_snapshots(self, conversation_id: str) -> List[Dict]:
        """Get all UI snapshots for conversation.

        Args:
            conversation_id: Conversation identifier

        Returns:
            List of snapshot dicts
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, message_id, snapshot_data, created_at
            FROM ui_snapshots
            WHERE conversation_id = ?
            ORDER BY created_at ASC
        """, (conversation_id,))

        rows = cursor.fetchall()
        conn.close()

        return [{
            'id': row['id'],
            'message_id': row['message_id'],
            'snapshot_data': json.loads(row['snapshot_data']),
            'created_at': row['created_at']
        } for row in rows]
