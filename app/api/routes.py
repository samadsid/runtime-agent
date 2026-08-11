from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Request

from app.api.models import (
    ChatRequest,
    ChatResponse,
)
from commerce.models import ChannelName
from runtime.contracts import (
    ConversationState,
    CustomerChannelContext,
)

router = APIRouter()


@router.post(
    "/chat",
    response_model=ChatResponse,
)
async def chat(
    body: ChatRequest,
    request: Request,
    development_customer_id: str | None = Header(
        default=None, alias="X-Development-Customer-Id"
    ),
) -> ChatResponse:

    conversation_id = (
        body.conversation_id if body.conversation_id is not None else uuid4()
    )

    conversation = ConversationState(
        conversation_id=conversation_id,
    )

    conversation.add_user_message(
        body.message,
    )

    application_container = request.app.state.application_container
    if (
        development_customer_id is not None
        and not application_container.settings.ALLOW_DEVELOPMENT_CUSTOMER_ID_HEADER
    ):
        raise HTTPException(
            status_code=400,
            detail="Development customer identity is disabled.",
        )
    normalized_customer_id = (
        development_customer_id.strip() if development_customer_id is not None else None
    )
    if normalized_customer_id == "":
        normalized_customer_id = None
    customer_context = CustomerChannelContext(
        tenant_id=application_container.settings.DEFAULT_TENANT_ID,
        conversation_id=conversation_id,
        channel=ChannelName.DEVELOPMENT_HTTP,
        channel_customer_id=normalized_customer_id,
    )

    conversation = await application_container.runtime.chat(
        conversation, customer_context
    )

    return ChatResponse(
        conversation_id=conversation.conversation_id,
        reply=conversation.latest_message.content
        if conversation.latest_message
        else "",
    )
