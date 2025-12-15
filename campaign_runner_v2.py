"""
Campaign Runner V2 - Uses CampaignCoordinator for parallel account sending

This module provides an enhanced campaign runner that uses the worker pool architecture
from campaign_worker.py to send messages in parallel from multiple accounts.
"""

import asyncio
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path

from database import db
from campaign_worker import CampaignCoordinator


def normalize_phone(phone):
    """Normalize phone number for comparison"""
    if not phone:
        return ''
    return str(phone).replace('+', '').replace(' ', '').replace('-', '').strip()


async def run_campaign_with_worker_pool(
    campaign_id: int,
    campaign_stop_flags: dict,
    get_all_accounts_func,
    update_account_func
) -> None:
    """
    Run campaign using worker pool architecture
    
    Args:
        campaign_id: Campaign ID to run
        campaign_stop_flags: Dict to check for stop requests {campaign_id: bool}
        get_all_accounts_func: Function to get all accounts
        update_account_func: Function to update account
    """
    try:
        # Initialize stop flag
        campaign_stop_flags[campaign_id] = False
        
        campaign = db.get_campaign(campaign_id)
        if not campaign:
            return

        settings = campaign.get('settings', {})
        message_text = settings.get('message', '')
        media_path = settings.get('media_path')
        media_type = settings.get('media_type')
        account_phones = settings.get('accounts', [])
        campaign_proxies = settings.get('proxies', [])
        
        # Get worker pool settings from campaign or use defaults
        messages_per_account = settings.get('messages_per_account', 50)  # Default: 50 messages per account
        delay_min = settings.get('delay_min', 30)  # Default: 30 seconds
        delay_max = settings.get('delay_max', 90)  # Default: 90 seconds

        normalized_saved_phones = [normalize_phone(p) for p in account_phones]
        
        # Get accounts
        all_accounts = get_all_accounts_func()
        print(f"DEBUG Campaign {campaign_id}: Found {len(all_accounts)} total accounts in memory")
        
        accounts = []
        for acc in all_accounts:
            acc_phone = normalize_phone(acc.get('phone'))
            
            # Skip unauthorized accounts
            if acc.get('status') == 'unauthorized':
                db.add_campaign_log(
                    campaign_id,
                    f'Account {acc_phone} is unauthorized (session expired), skipping',
                    level='warning'
                )
                continue
            
            # Check if limited account can be restored (after 24 hours)
            if acc.get('status') == 'limited':
                last_used = acc.get('last_used_at')
                if last_used:
                    try:
                        last_used_time = datetime.fromisoformat(last_used)
                        hours_since_limit = (datetime.now() - last_used_time).total_seconds() / 3600
                        if hours_since_limit >= 24:
                            db.add_campaign_log(
                                campaign_id,
                                f'Account {acc_phone} limited status cleared after {hours_since_limit:.1f} hours',
                                level='info'
                            )
                            update_account_func(acc.get('id'), {
                                'status': 'active',
                                'last_used_at': datetime.now().isoformat()
                            })
                            acc['status'] = 'active'
                        else:
                            continue
                    except:
                        continue
                else:
                    continue
            
            if acc_phone and acc_phone in normalized_saved_phones:
                accounts.append(acc)

        if not accounts:
            db.add_campaign_log(
                campaign_id,
                f'No accounts available. Saved phones: {account_phones}',
                level='error'
            )
            db.update_campaign(campaign_id, status='failed')
            return

        # Get campaign users
        campaign_users = db.get_campaign_users(campaign_id)
        
        # Filter only 'new' status users (Continue logic)
        users = [cu for cu in campaign_users if cu.get('status') == 'new']

        if not users:
            db.add_campaign_log(campaign_id, 'No users to contact', level='info')
            db.update_campaign(campaign_id, status='completed')
            return

        db.add_campaign_log(
            campaign_id,
            f'Starting campaign with worker pool: {len(accounts)} accounts, {len(users)} users',
            level='info'
        )

        # Create CampaignCoordinator
        coordinator = CampaignCoordinator(
            campaign_id=campaign_id,
            accounts=accounts,
            proxies=campaign_proxies,
            message_text=message_text,
            media_path=media_path,
            media_type=media_type,
            messages_per_account=messages_per_account,
            delay_min=delay_min,
            delay_max=delay_max,
            db=db
        )

        # Define stop check callback
        def should_stop():
            return campaign_stop_flags.get(campaign_id, False)

        # Run campaign
        results = await coordinator.run_campaign(
            users=users,
            stop_check_callback=should_stop
        )

        # Update campaign with final counts
        sent_count = results['sent']
        failed_count = results['failed']
        
        # Check if stopped
        if campaign_stop_flags.get(campaign_id, False):
            db.add_campaign_log(
                campaign_id,
                f'Campaign stopped: {sent_count} sent, {failed_count} failed',
                level='warning'
            )
            db.update_campaign(campaign_id, status='stopped', sent_count=sent_count, failed_count=failed_count)
        else:
            db.update_campaign(campaign_id, status='completed', sent_count=sent_count, failed_count=failed_count)
            db.add_campaign_log(
                campaign_id,
                f'Campaign completed: {sent_count} sent, {failed_count} failed',
                level='info'
            )

    except Exception as e:
        db.add_campaign_log(campaign_id, f'Campaign error: {str(e)}', level='error')
        db.update_campaign(campaign_id, status='failed')
        import traceback
        traceback.print_exc()
    finally:
        # Clean up stop flag
        campaign_stop_flags.pop(campaign_id, None)


def run_campaign_task_v2(
    campaign_id: int,
    campaign_stop_flags: dict,
    get_all_accounts_func,
    update_account_func
) -> None:
    """
    Wrapper to run async campaign runner in sync context (for threading)
    
    Args:
        campaign_id: Campaign ID
        campaign_stop_flags: Dict for stop flags
        get_all_accounts_func: Function to get accounts
        update_account_func: Function to update accounts
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(
            run_campaign_with_worker_pool(
                campaign_id,
                campaign_stop_flags,
                get_all_accounts_func,
                update_account_func
            )
        )
    finally:
        loop.close()
