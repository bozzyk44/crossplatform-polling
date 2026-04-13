import secrets
from urllib.parse import urlencode

import httpx
import structlog
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from app.config import settings
from app.core.crypto import encrypt_token
from app.database.engine import async_session
from app.database.models import ConnectedGroup
from app.platforms.vk.client import VK_API_BASE, VK_API_VERSION

logger = structlog.get_logger()
router = APIRouter(prefix="/vk", tags=["vk-oauth"])

# In-memory CSRF state store (use Redis in production with multiple workers)
_pending_states: dict[str, bool] = {}


@router.get("/connect")
async def vk_connect():
    """Step 1: Redirect user to VK OAuth page."""
    state = secrets.token_urlsafe(32)
    _pending_states[state] = True

    params = urlencode({
        "client_id": settings.vk_app_id,
        "redirect_uri": f"{settings.webhook_base_url}/vk/callback",
        "scope": "groups,wall",
        "response_type": "code",
        "state": state,
        "v": VK_API_VERSION,
    })
    return RedirectResponse(f"https://oauth.vk.com/authorize?{params}")


@router.get("/callback")
async def vk_callback(request: Request, code: str = "", state: str = ""):
    """Step 2: Exchange code for user token, list admin groups."""
    if not state or state not in _pending_states:
        raise HTTPException(400, "Invalid or expired state parameter")
    del _pending_states[state]

    if not code:
        raise HTTPException(400, "Authorization denied by user")

    # Exchange code for user token
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://oauth.vk.com/access_token",
            data={
                "client_id": settings.vk_app_id,
                "client_secret": settings.vk_app_secret,
                "redirect_uri": f"{settings.webhook_base_url}/vk/callback",
                "code": code,
            },
        )
        token_data = resp.json()

    if "error" in token_data:
        logger.error("vk_oauth_error", error=token_data)
        raise HTTPException(400, f"VK OAuth error: {token_data.get('error_description', '')}")

    user_token = token_data["access_token"]
    user_id = token_data["user_id"]

    # Get groups where user is admin
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{VK_API_BASE}/groups.get",
            data={
                "access_token": user_token,
                "filter": "admin",
                "extended": "1",
                "v": VK_API_VERSION,
            },
        )
        groups_data = resp.json()

    if "error" in groups_data:
        raise HTTPException(400, "Failed to fetch groups")

    groups = groups_data["response"]["items"]
    if not groups:
        return HTMLResponse("<h3>У вас нет групп, где вы администратор.</h3>")

    # Render group selection page
    new_state = secrets.token_urlsafe(32)
    _pending_states[new_state] = True

    # Temporarily store user token (short-lived, for step 3)
    _pending_tokens[new_state] = {"user_token": user_token, "user_id": user_id}

    options = "".join(
        f'<option value="{g["id"]}">{g["name"]} (id{g["id"]})</option>' for g in groups
    )
    html = f"""
    <html><body>
    <h3>Выберите группу для подключения:</h3>
    <form method="POST" action="/vk/connect-group">
        <input type="hidden" name="state" value="{new_state}">
        <select name="group_id">{options}</select><br><br>
        <button type="submit">Подключить</button>
    </form>
    </body></html>
    """
    return HTMLResponse(html)


# Temp store for user tokens between step 2 and 3
_pending_tokens: dict[str, dict] = {}


@router.post("/connect-group")
async def connect_group(request: Request):
    """Step 3: Get group token and save to DB."""
    form = await request.form()
    state = str(form.get("state", ""))
    group_id = int(form.get("group_id", 0))

    if not state or state not in _pending_states:
        raise HTTPException(400, "Invalid or expired state")
    del _pending_states[state]

    token_info = _pending_tokens.pop(state, None)
    if not token_info:
        raise HTTPException(400, "Session expired, please start over")

    user_token = token_info["user_token"]
    user_id = token_info["user_id"]

    # Use user token to manage the group (user must be admin)
    async with httpx.AsyncClient() as client:
        # Get group info
        resp = await client.post(
            f"{VK_API_BASE}/groups.getById",
            data={
                "access_token": user_token,
                "group_id": str(group_id),
                "v": VK_API_VERSION,
            },
        )
        group_data = resp.json()

    if "error" in group_data:
        raise HTTPException(400, "Failed to get group info")

    groups = group_data["response"].get("groups", group_data["response"])
    group_name = groups[0]["name"] if isinstance(groups, list) else "Unknown"

    # Get callback confirmation string
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{VK_API_BASE}/groups.getCallbackConfirmationCode",
            data={
                "access_token": user_token,
                "group_id": str(group_id),
                "v": VK_API_VERSION,
            },
        )
        confirm_data = resp.json()

    confirmation_string = None
    if "response" in confirm_data:
        confirmation_string = confirm_data["response"].get("code")

    # Save to DB with encrypted token
    encrypted = encrypt_token(user_token)

    async with async_session() as session:
        existing = await session.execute(
            select(ConnectedGroup).where(ConnectedGroup.vk_group_id == group_id)
        )
        group = existing.scalar_one_or_none()

        if group:
            group.encrypted_token = encrypted
            group.vk_group_name = group_name
            group.confirmation_string = confirmation_string
            group.connected_by_vk_user_id = user_id
            group.is_active = True
        else:
            group = ConnectedGroup(
                vk_group_id=group_id,
                vk_group_name=group_name,
                encrypted_token=encrypted,
                confirmation_string=confirmation_string,
                connected_by_vk_user_id=user_id,
            )
            session.add(group)
        await session.commit()

    logger.info("vk_group_connected", group_id=group_id, group_name=group_name)

    # Set up callback server for the group
    webhook_url = f"{settings.webhook_base_url}/webhook/vk/{group_id}"
    async with httpx.AsyncClient() as client:
        # Add callback server
        resp = await client.post(
            f"{VK_API_BASE}/groups.addCallbackServer",
            data={
                "access_token": user_token,
                "group_id": str(group_id),
                "url": webhook_url,
                "title": "PollAggregator",
                "v": VK_API_VERSION,
            },
        )
        server_data = resp.json()

        if "response" in server_data:
            server_id = server_data["response"]["server_id"]
            # Enable poll_vote_new event
            await client.post(
                f"{VK_API_BASE}/groups.setCallbackSettings",
                data={
                    "access_token": user_token,
                    "group_id": str(group_id),
                    "server_id": str(server_id),
                    "poll_vote_new": "1",
                    "v": VK_API_VERSION,
                },
            )
            logger.info("vk_callback_configured", group_id=group_id, server_id=server_id)

    return HTMLResponse(
        f"<h3>Группа «{group_name}» успешно подключена!</h3>"
        f"<p>Webhook: {webhook_url}</p>"
        "<p>Теперь вы можете создавать опросы через Admin API.</p>"
    )


@router.post("/disconnect/{group_id}")
async def disconnect_group(group_id: int):
    """Remove a connected group."""
    async with async_session() as session:
        result = await session.execute(
            select(ConnectedGroup).where(ConnectedGroup.vk_group_id == group_id)
        )
        group = result.scalar_one_or_none()
        if not group:
            raise HTTPException(404, "Group not found")

        group.is_active = False
        group.encrypted_token = ""  # wipe token
        await session.commit()

    logger.info("vk_group_disconnected", group_id=group_id)
    return {"status": "disconnected", "group_id": group_id}
