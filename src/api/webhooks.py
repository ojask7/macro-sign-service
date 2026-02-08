"""
Webhook management API endpoints.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import RBACPermission, get_current_user
from src.config.logging import get_logger
from src.models.database import get_db
from src.models.pydantic_schemas import WebhookCreate, WebhookResponse, WebhookUpdate
from src.models.schemas import User, WebhookConfig

logger = get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post(
    "",
    response_model=WebhookResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Webhook",
    dependencies=[Depends(RBACPermission("manage_webhooks"))],
)
async def create_webhook(
    body: WebhookCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WebhookResponse:
    """Create a new webhook configuration."""
    webhook = WebhookConfig(
        name=body.name,
        url=body.url,
        secret=body.secret,
        events=body.events,
        user_id=current_user.id,
    )
    db.add(webhook)
    await db.flush()

    logger.info("Webhook created", name=body.name, url=body.url)

    return WebhookResponse(
        id=str(webhook.id),
        name=webhook.name,
        url=webhook.url,
        events=webhook.events,
        is_active=webhook.is_active,
        created_at=webhook.created_at,
    )


@router.get(
    "",
    response_model=list[WebhookResponse],
    summary="List Webhooks",
    dependencies=[Depends(RBACPermission("manage_webhooks"))],
)
async def list_webhooks(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[WebhookResponse]:
    """List webhook configurations."""
    result = await db.execute(
        select(WebhookConfig).where(WebhookConfig.user_id == current_user.id)
    )
    webhooks = result.scalars().all()

    return [
        WebhookResponse(
            id=str(w.id),
            name=w.name,
            url=w.url,
            events=w.events,
            is_active=w.is_active,
            created_at=w.created_at,
        )
        for w in webhooks
    ]


@router.patch(
    "/{webhook_id}",
    response_model=WebhookResponse,
    summary="Update Webhook",
    dependencies=[Depends(RBACPermission("manage_webhooks"))],
)
async def update_webhook(
    webhook_id: str,
    body: WebhookUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WebhookResponse:
    """Update a webhook configuration."""
    result = await db.execute(
        select(WebhookConfig).where(
            WebhookConfig.id == uuid.UUID(webhook_id),
            WebhookConfig.user_id == current_user.id,
        )
    )
    webhook = result.scalar_one_or_none()

    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )

    if body.name is not None:
        webhook.name = body.name
    if body.url is not None:
        webhook.url = body.url
    if body.events is not None:
        webhook.events = body.events
    if body.is_active is not None:
        webhook.is_active = body.is_active

    await db.flush()

    return WebhookResponse(
        id=str(webhook.id),
        name=webhook.name,
        url=webhook.url,
        events=webhook.events,
        is_active=webhook.is_active,
        created_at=webhook.created_at,
    )


@router.delete(
    "/{webhook_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Webhook",
    dependencies=[Depends(RBACPermission("manage_webhooks"))],
)
async def delete_webhook(
    webhook_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a webhook configuration."""
    result = await db.execute(
        select(WebhookConfig).where(
            WebhookConfig.id == uuid.UUID(webhook_id),
            WebhookConfig.user_id == current_user.id,
        )
    )
    webhook = result.scalar_one_or_none()

    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )

    await db.delete(webhook)
    logger.info("Webhook deleted", webhook_id=webhook_id)
