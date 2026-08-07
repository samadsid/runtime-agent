from fastapi import APIRouter, Request
from uuid import uuid4

from app.api.models import (
    ChatRequest,
    ChatResponse,
)

from runtime.contracts import (
    ConversationState,
    Message,
    MessageRole,
)


router = APIRouter()



@router.post(
    "/chat",
    response_model=ChatResponse,
)
async def chat(
    body: ChatRequest,
    request: Request,
) -> ChatResponse:
    
    conversation_id = (
        body.conversation_id
        if body.conversation_id is not None
        else uuid4()
    )

    conversation = ConversationState(
        conversation_id=conversation_id,
    )

    conversation.add_user_message(
        body.message,
    )


    application_container = request.app.state.application_container
    
    conversation = await (
        application_container.runtime.chat(
            conversation
        )
    )

    return ChatResponse(
        conversation_id=conversation.conversation_id,
        reply=conversation.latest_message.content if conversation.latest_message else "",
    )