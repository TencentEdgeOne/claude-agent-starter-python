"""
Stop handler — EdgeOne Makers

Route: POST /stop
Aborts an active agent run by conversation ID.
"""

from .._logger import create_logger

logger = create_logger("stop")


async def handler(context):
    """Abort the active agent run."""
    body = context.request.body or {}
    conversation_id = body.get('conversation_id')

    if not conversation_id:
        return {
            'status_code': 400,
            'body': {
                'status': 'error',
                'message': 'conversation_id is required',
            }
        }

    result = context.utils.abort_active_run(conversation_id)

    return {
        "status": "aborting" if result.aborted else "idle",
        "conversationId": result.conversation_id or conversation_id,
        "runId": result.run_id,
        "aborted": result.aborted,
    }
