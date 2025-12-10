# app/actions.py - Action queue management for website -> bot communication
"""
Action Queue System

The Django website queues actions here, and the Discord bot polls the pending_actions
table to process them. This enables immediate Discord actions from the web dashboard
without requiring WebSocket communication.
"""

import json
import logging
from typing import Dict, Any, Optional
from .db import get_db_session
from .models import PendingAction, ActionType, ActionStatus

logger = logging.getLogger(__name__)

# Re-export ActionType for convenience
__all__ = [
    'queue_action',
    'queue_xp_add',
    'queue_xp_set',
    'queue_tokens_add',
    'queue_clear_featured',
    'ActionType',
    'ActionStatus'
]


def queue_action(
    guild_id: int,
    action_type: ActionType,
    payload: Dict[str, Any],
    triggered_by: Optional[int] = None,
    triggered_by_name: Optional[str] = None,
    source: str = 'website',
    priority: int = 5
) -> int:
    """
    Queue an action for the bot to process.

    Args:
        guild_id: Discord guild (server) ID
        action_type: Type of action (from ActionType enum)
        payload: Action-specific data (will be JSON serialized)
        triggered_by: Discord user ID who triggered this action
        triggered_by_name: Display name of user who triggered action
        source: Where the action came from (website, api, csv_import, etc.)
        priority: Priority level (1=highest, 10=lowest, default=5)

    Returns:
        int: ID of the queued action

    Example:
        action_id = queue_action(
            guild_id=123456789,
            action_type=ActionType.ROLE_ADD,
            payload={'user_id': 987654321, 'role_id': 111222333},
            triggered_by=555666777,
            triggered_by_name='Admin User',
            source='website'
        )
    """
    try:
        # Serialize payload to JSON
        payload_json = json.dumps(payload)

        with get_db_session() as db:
            action = PendingAction(
                guild_id=guild_id,
                action_type=action_type,
                status=ActionStatus.PENDING,
                priority=priority,
                payload=payload_json,
                triggered_by=triggered_by,
                triggered_by_name=triggered_by_name,
                source=source
            )

            db.add(action)
            db.flush()  # Get the ID before commit

            action_id = action.id

            # Commit happens automatically when context manager exits
            logger.info(
                f"Queued action {action_id}: {action_type.value} for guild {guild_id} "
                f"(triggered by {triggered_by_name or triggered_by or 'system'})"
            )

            return action_id

    except Exception as e:
        logger.error(f"Failed to queue action {action_type.value}: {e}", exc_info=True)
        raise


def get_action_status(action_id: int) -> Optional[Dict[str, Any]]:
    """
    Get the status of a queued action.

    Args:
        action_id: ID of the action

    Returns:
        dict: Action status information, or None if not found
    """
    try:
        with get_db_session() as db:
            action = db.query(PendingAction).filter_by(id=action_id).first()

            if not action:
                return None

            return {
                'id': action.id,
                'guild_id': action.guild_id,
                'action_type': action.action_type.value,
                'status': action.status.value,
                'priority': action.priority,
                'created_at': action.created_at,
                'processed_at': action.processed_at,
                'error_message': action.error_message,
            }

    except Exception as e:
        logger.error(f"Failed to get action status for {action_id}: {e}")
        return None


def cancel_action(action_id: int) -> bool:
    """
    Cancel a pending action (if it hasn't been processed yet).

    Args:
        action_id: ID of the action to cancel

    Returns:
        bool: True if cancelled, False if not found or already processed
    """
    try:
        with get_db_session() as db:
            action = db.query(PendingAction).filter_by(id=action_id).first()

            if not action:
                return False

            if action.status not in (ActionStatus.PENDING, ActionStatus.PROCESSING):
                return False  # Already completed/failed/cancelled

            action.status = ActionStatus.CANCELLED
            logger.info(f"Cancelled action {action_id}")

            return True

    except Exception as e:
        logger.error(f"Failed to cancel action {action_id}: {e}")
        return False


# =============================================================================
# XP & TOKENS - Convenience Functions
# =============================================================================

def queue_xp_add(
    guild_id: int,
    user_id: int,
    amount: float,
    triggered_by: Optional[int] = None,
    triggered_by_name: Optional[str] = None
) -> int:
    """
    Queue an action to add XP to a user.

    Args:
        guild_id: Discord guild/server ID
        user_id: Discord user ID
        amount: Amount of XP to add (can be negative to subtract)
        triggered_by: User ID who triggered this action (from website)
        triggered_by_name: Display name of who triggered it

    Returns:
        int: The PendingAction ID
    """
    return queue_action(
        guild_id=guild_id,
        action_type=ActionType.XP_ADD,
        payload={
            'user_id': user_id,
            'amount': amount
        },
        triggered_by=triggered_by,
        triggered_by_name=triggered_by_name,
        source='website',
        priority=5
    )


def queue_xp_set(
    guild_id: int,
    user_id: int,
    amount: float,
    triggered_by: Optional[int] = None,
    triggered_by_name: Optional[str] = None
) -> int:
    """
    Queue an action to set a user's XP to a specific value.

    Args:
        guild_id: Discord guild/server ID
        user_id: Discord user ID
        amount: XP value to set
        triggered_by: User ID who triggered this action (from website)
        triggered_by_name: Display name of who triggered it

    Returns:
        int: The PendingAction ID
    """
    return queue_action(
        guild_id=guild_id,
        action_type=ActionType.XP_SET,
        payload={
            'user_id': user_id,
            'amount': amount
        },
        triggered_by=triggered_by,
        triggered_by_name=triggered_by_name,
        source='website',
        priority=5
    )


def queue_tokens_add(
    guild_id: int,
    user_id: int,
    amount: int,
    triggered_by: Optional[int] = None,
    triggered_by_name: Optional[str] = None
) -> int:
    """
    Queue an action to add Hero Tokens to a user.

    Args:
        guild_id: Discord guild/server ID
        user_id: Discord user ID
        amount: Number of tokens to add (can be negative to subtract)
        triggered_by: User ID who triggered this action (from website)
        triggered_by_name: Display name of who triggered it

    Returns:
        int: The PendingAction ID
    """
    return queue_action(
        guild_id=guild_id,
        action_type=ActionType.TOKENS_ADD,
        payload={
            'user_id': user_id,
            'amount': amount
        },
        triggered_by=triggered_by,
        triggered_by_name=triggered_by_name,
        source='website',
        priority=5
    )


def queue_tokens_set(
    guild_id: int,
    user_id: int,
    amount: int,
    triggered_by: Optional[int] = None,
    triggered_by_name: Optional[str] = None
) -> int:
    """
    Queue an action to set a user's Hero Tokens to a specific value.

    Args:
        guild_id: Discord guild/server ID
        user_id: Discord user ID
        amount: Token value to set
        triggered_by: User ID who triggered this action (from website)
        triggered_by_name: Display name of who triggered it

    Returns:
        int: The PendingAction ID
    """
    return queue_action(
        guild_id=guild_id,
        action_type=ActionType.TOKENS_SET,
        payload={
            'user_id': user_id,
            'amount': amount
        },
        triggered_by=triggered_by,
        triggered_by_name=triggered_by_name,
        source='website',
        priority=5
    )


def queue_clear_featured(
    guild_id: int,
    triggered_by: Optional[int] = None,
    triggered_by_name: Optional[str] = None
) -> int:
    """
    Queue an action to clear the current featured person.

    Args:
        guild_id: Discord guild/server ID
        triggered_by: User ID who triggered this action (from website)
        triggered_by_name: Display name of who triggered it

    Returns:
        int: The PendingAction ID
    """
    return queue_action(
        guild_id=guild_id,
        action_type=ActionType.CLEAR_FEATURED,
        payload={},  # No payload needed
        triggered_by=triggered_by,
        triggered_by_name=triggered_by_name,
        source='website',
        priority=5
    )


def queue_test_channel_embed(
    guild_id: int,
    channel_id: int,
    triggered_by: Optional[int] = None,
    triggered_by_name: Optional[str] = None
) -> int:
    """
    Queue an action to send a test channel embed.

    Args:
        guild_id: Discord guild/server ID
        channel_id: Channel ID to send the test embed to
        triggered_by: User ID who triggered this action (from website)
        triggered_by_name: Display name of who triggered it

    Returns:
        int: The PendingAction ID
    """
    return queue_action(
        guild_id=guild_id,
        action_type=ActionType.TEST_CHANNEL_EMBED,
        payload={'channel_id': channel_id},
        triggered_by=triggered_by,
        triggered_by_name=triggered_by_name,
        source='website',
        priority=5
    )


def queue_test_forum_embed(
    guild_id: int,
    channel_id: int,
    triggered_by: Optional[int] = None,
    triggered_by_name: Optional[str] = None
) -> int:
    """
    Queue an action to send a test forum embed.

    Args:
        guild_id: Discord guild/server ID
        channel_id: Channel ID to send the test embed to
        triggered_by: User ID who triggered this action (from website)
        triggered_by_name: Display name of who triggered it

    Returns:
        int: The PendingAction ID
    """
    return queue_action(
        guild_id=guild_id,
        action_type=ActionType.TEST_FORUM_EMBED,
        payload={'channel_id': channel_id},
        triggered_by=triggered_by,
        triggered_by_name=triggered_by_name,
        source='website',
        priority=5
    )