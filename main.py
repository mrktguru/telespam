"""FastAPI application for Telegram Outreach System"""

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from pathlib import Path
from uuid import uuid4
import shutil
import asyncio

import config
from converter import detect_and_process
from sheets_loader import sheets_manager
from accounts import (
    check_account_status,
    add_account,
    delete_account
)
from sender import send_message, get_dialog_history
from listener import message_listener
from proxy import get_proxy_config

# Create FastAPI app
app = FastAPI(
    title="Telegram Outreach System API",
    description="API for managing Telegram accounts and automated outreach",
    version="1.0.0"
)


# Pydantic models

class ProcessFileRequest(BaseModel):
    file_path: str
    notes: Optional[str] = ""


class SendMessageRequest(BaseModel):
    user_id: int
    type: str
    account_id: Optional[str] = None
    content: Optional[str] = None
    file_url: Optional[str] = None
    file_base64: Optional[str] = None
    file_path: Optional[str] = None
    caption: Optional[str] = None
    filename: Optional[str] = None


class ProxySettings(BaseModel):
    enabled: bool
    default_proxy: Optional[dict] = None


class AccountProxySettings(BaseModel):
    use_proxy: bool
    type: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None


# Startup event

@app.on_event("startup")
async def startup_event():
    """Start message listener on startup"""
    # Start listener in background
    asyncio.create_task(message_listener.start_listening())


@app.on_event("shutdown")
async def shutdown_event():
    """Stop message listener on shutdown"""
    await message_listener.stop_listening()


# Account endpoints

@app.post("/accounts/upload")
async def upload_account(
    file: UploadFile = File(...),
    notes: Optional[str] = Form("")
):
    """
    Upload and process account file (tdata ZIP or session file)

    Args:
        file: ZIP or session file
        notes: Optional notes about the account

    Returns:
        Account information if successful
    """

    try:
        # Save uploaded file
        upload_dir = config.UPLOADS_DIR / f"upload_{uuid4()}"
        upload_dir.mkdir(parents=True, exist_ok=True)

        file_path = upload_dir / file.filename
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Process the file
        result = await detect_and_process(str(file_path), notes)

        # Clean up upload directory
        shutil.rmtree(upload_dir, ignore_errors=True)

        if result['success']:
            # Add account to sheets
            account_result = await add_account(result['account'])

            if account_result['success']:
                return JSONResponse(content=account_result)
            else:
                return JSONResponse(
                    status_code=500,
                    content=account_result
                )
        else:
            return JSONResponse(
                status_code=400,
                content=result
            )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e)
            }
        )


@app.post("/accounts/process")
async def process_account(request: ProcessFileRequest):
    """
    Process account file from incoming directory

    Args:
        request: Request with file path and notes

    Returns:
        Account information if successful
    """

    try:
        # Process the file
        result = await detect_and_process(request.file_path, request.notes)

        if result['success']:
            # Add account to sheets
            account_result = await add_account(result['account'])

            # Send webhook to n8n
            if config.N8N_WEBHOOK_ACCOUNT:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    await session.post(
                        config.N8N_WEBHOOK_ACCOUNT,
                        json=account_result
                    )

            return JSONResponse(content=account_result)
        else:
            # Send error to webhook
            if config.N8N_WEBHOOK_ACCOUNT:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    await session.post(
                        config.N8N_WEBHOOK_ACCOUNT,
                        json=result
                    )

            return JSONResponse(
                status_code=400,
                content=result
            )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e)
            }
        )


@app.get("/accounts")
async def get_accounts():
    """Get list of all accounts"""

    try:
        accounts = sheets_manager.get_all_accounts()
        return {
            "success": True,
            "accounts": accounts
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e)
            }
        )


@app.get("/accounts/{account_id}")
async def get_account(account_id: str):
    """Get specific account by ID"""

    try:
        account = sheets_manager.get_account(account_id)
        if account:
            return {
                "success": True,
                "account": account
            }
        else:
            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "error": "Account not found"
                }
            )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e)
            }
        )


@app.post("/accounts/{account_id}/check")
async def check_account(account_id: str):
    """Check account status"""

    try:
        result = await check_account_status(account_id)
        if result['success']:
            return result
        else:
            return JSONResponse(
                status_code=400,
                content=result
            )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e)
            }
        )


@app.delete("/accounts/{account_id}")
async def remove_account(account_id: str):
    """Delete account"""

    try:
        result = await delete_account(account_id)
        if result['success']:
            return result
        else:
            return JSONResponse(
                status_code=400,
                content=result
            )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e)
            }
        )


@app.put("/accounts/{account_id}/proxy")
async def set_account_proxy(account_id: str, settings: AccountProxySettings):
    """Set proxy settings for specific account"""

    try:
        updates = {
            "use_proxy": settings.use_proxy,
            "proxy_type": settings.type or "",
            "proxy_host": settings.host or "",
            "proxy_port": settings.port or "",
            "proxy_user": settings.username or "",
            "proxy_pass": settings.password or ""
        }

        success = sheets_manager.update_account(account_id, updates)

        if success:
            return {
                "success": True,
                "message": f"Proxy settings updated for account {account_id}"
            }
        else:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "Failed to update account"
                }
            )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e)
            }
        )


@app.delete("/accounts/{account_id}/proxy")
async def disable_account_proxy(account_id: str):
    """Disable proxy for specific account"""

    try:
        updates = {
            "use_proxy": False
        }

        success = sheets_manager.update_account(account_id, updates)

        if success:
            return {
                "success": True,
                "message": f"Proxy disabled for account {account_id}"
            }
        else:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "Failed to update account"
                }
            )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e)
            }
        )


# Message endpoints

@app.post("/send")
async def send(request: SendMessageRequest):
    """Send message to user"""

    try:
        result = await send_message(
            user_id=request.user_id,
            message_type=request.type,
            content=request.content,
            file_url=request.file_url,
            file_base64=request.file_base64,
            file_path=request.file_path,
            caption=request.caption,
            filename=request.filename,
            account_id=request.account_id
        )

        if result['success']:
            return result
        else:
            return JSONResponse(
                status_code=400,
                content=result
            )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e)
            }
        )


@app.get("/dialogs/{user_id}")
async def get_dialog(user_id: int, limit: int = 50):
    """Get dialog history with user"""

    try:
        result = await get_dialog_history(user_id, limit)

        if result['success']:
            return result
        else:
            return JSONResponse(
                status_code=400,
                content=result
            )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e)
            }
        )


# Settings endpoints

@app.get("/settings")
async def get_settings():
    """Get all settings"""

    try:
        settings = sheets_manager.get_settings()
        return {
            "success": True,
            "settings": settings
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e)
            }
        )


@app.post("/settings/proxy")
async def set_proxy_settings(settings: ProxySettings):
    """Set global proxy settings"""

    try:
        # Update proxy_enabled
        sheets_manager.update_setting("proxy_enabled", str(settings.enabled))

        # Update default proxy if provided
        if settings.default_proxy:
            sheets_manager.update_setting(
                "default_proxy_type",
                settings.default_proxy.get('type', 'socks5')
            )
            sheets_manager.update_setting(
                "default_proxy_host",
                settings.default_proxy.get('host', '')
            )
            sheets_manager.update_setting(
                "default_proxy_port",
                str(settings.default_proxy.get('port', ''))
            )
            sheets_manager.update_setting(
                "default_proxy_user",
                settings.default_proxy.get('username', '')
            )
            sheets_manager.update_setting(
                "default_proxy_pass",
                settings.default_proxy.get('password', '')
            )

        status = "enabled" if settings.enabled else "disabled"
        return {
            "success": True,
            "message": f"Proxy {status} globally"
        }

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e)
            }
        )


# System endpoints

@app.get("/")
async def root():
    """API root endpoint"""
    return {
        "name": "Telegram Outreach System API",
        "version": "1.0.0",
        "status": "running",
        "listener_active": message_listener.is_running(),
        "listening_accounts": message_listener.get_active_accounts()
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "listener_running": message_listener.is_running()
    }


# Run the application

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=config.HOST,
        port=config.PORT,
        reload=False
    )
