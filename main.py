import argparse
import ast
import asyncio
import datetime
import json
import logging
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import pandas as pd
import requests
from bs4 import BeautifulSoup
from camoufox import AsyncCamoufox
from dotenv import load_dotenv
from playwright._impl._errors import TargetClosedError
from playwright.async_api import BrowserContext, Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from camoufox_captcha import solve_captcha
from utils.attr_extractor import extract_job_attributes
from utils.logger import Logger

# Load environment variables from .env file
load_dotenv()

# Initialize logger (will be overridden in __main__ block if run directly)
logger_obj = Logger(level="INFO")
logger = logger_obj.get_logger()

UPWORK_MAIN_CATEGORIES = {
    # Main Categories
    "accounting & consulting": "531770282584862721",
    "admin support": "531770282580668416",
    "customer service": "531770282580668417",
    "data science & analytics": "531770282580668420",
    "design & creative": "531770282580668421",
    "engineering & architecture": "531770282584862722",
    "it & networking": "531770282580668419",
    "legal": "531770282584862723",
    "sales & marketing": "531770282580668422",
    "translation": "531770282584862720",
    "web, mobile & software dev": "531770282580668418",
    "writing": "531770282580668423",
}
# Subcategories
UPWORK_SUBCATEGORIES = {
    # accounting & consulting
    "personal & professional coaching": "1534904461833879552",
    "accounting & bookkeeping": "531770282601639943",
    "financial planning": "531770282601639945",
    "recruiting & human resources": "531770282601639946",
    "management consulting & analysis": "531770282601639944",
    "other - accounting & consulting": "531770282601639947",
    # admin support
    "data entry & transcription services": "531770282584862724",
    "virtual assistance": "531770282584862725",
    "project management": "531770282584862728",
    "market research & product reviews": "531770282584862726",
    # customer service
    "community management & tagging": "1484275072572772352",
    "customer service & tech support": "531770282584862730",
    # data science & analytics
    "data analysis & testing": "531770282593251330",
    "data extraction & etl": "531770282593251331",
    "data mining & management": "531770282589057038",
    "ai & machine learning": "531770282593251329",
    # design & creative
    "art & illustration": "531770282593251335",
    "audio & music production": "531770282593251341",
    "branding & logo design": "1044578476142100480",
    "nft, ar/vr & game art": "1356688560628174848",
    "graphic, editorial & presentation design": "531770282593251334",
    "performing arts": "1356688565288046592",
    "photography": "531770282593251340",
    "product design": "531770282601639953",
    "video & animation": "1356688570056970240",
    # engineering & architecture
    "building & landscape architecture": "531770282601639949",
    "chemical engineering": "531770282605834240",
    "civil & structural engineering": "531770282601639950",
    "contract manufacturing": "531770282605834241",
    "electrical & electronic engineering": "531770282601639951",
    "interior & trade show design": "531770282605834242",
    "energy & mechanical engineering": "531770282601639952",
    "physical sciences": "1301900647896092672",
    "3d modeling & cad": "531770282601639948",
    # it & networking
    "database management & administration": "531770282589057033",
    "erp & crm software": "531770282589057034",
    "information security & compliance": "531770282589057036",
    "network & system administration": "531770282589057035",
    "devops & solution architecture": "531770282589057037",
    # legal
    "corporate & contract law": "531770282605834246",
    "international & immigration law": "1484275156546932736",
    "finance & tax law": "531770283696353280",
    "public law": "1484275408410693632",
    # sales & marketing
    "digital marketing": "531770282597445636",
    "lead generation & telemarketing": "531770282597445634",
    "marketing, pr & brand strategy": "531770282593251343",
    # translation
    "language tutoring & interpretation": "1534904461842268160",
    "translation & localization services": "531770282601639939",
    # web, mobile & software dev
    "blockchain, nft & cryptocurrency": "1517518458442309632",
    "ai apps and integration": "1737190722360750082",
    "desktop application development": "531770282589057025",
    "ecommerce development": "531770282589057026",
    "game design & development": "531770282589057027",
    "mobile development": "531770282589057024",
    "other - software development": "531770282589057032",
    "product management": "531770282589057030",
    "qa & testing": "531770282589057031",
    "scripts & utilities": "531770282589057028",
    "web & mobile design": "531770282589057029",
    "web development": "531770282584862733",
    # writing
    "sales & marketing copywriting": "1534904462131675136",
    "content writing": "1301900640421842944",
    "editing & proofreading services": "531770282597445644",
    "professional & business writing": "531770282597445646"
}

def normalize_search_params(params: dict, credentials_provided: bool, buffer: int = 5) -> tuple[dict, int]:
    """
    Normalize search parameters from config or input JSON for Upwork job search URL.

    :param params: Dictionary of search parameters (from config or user input)
    :type params: dict
    :param credentials_provided: Whether Upwork credentials are provided (affects access to some filters)
    :type credentials_provided: bool
    :return: Tuple of (normalized_params dict, limit int)
    """
    result = {}

    # Get and validate the limit (no buffer here)
    try:
        limit = int(params.get('limit', 5)) + buffer
    except (ValueError, TypeError):
        limit = 5
        logger.warning("Invalid limit value in config, using default limit of 5")
    
    # Set per_page parameter to the next allowed Upwork value >= limit
    allowed_per_page = [10, 20, 50]
    per_page = min([v for v in allowed_per_page if v >= limit] or [50])
    result['per_page'] = str(per_page)
    
    # Fixed price categories and custom range
    if 'fixed_price_catagory_num' in params:
        amount_ranges = {
            "1": "0-99",
            "2": "100-499",
            "3": "500-999",
            "4": "1000-4999",
            "5": "5000-"
        }
        ranges = []
        for cat in params['fixed_price_catagory_num']:
            if cat in amount_ranges:
                ranges.append(amount_ranges[cat])
        if params.get('fixed_min') and params.get('fixed_max'):
            ranges.append(f"{params['fixed_min']}-{params['fixed_max']}")
        if ranges:
            result['amount'] = ','.join(ranges)
    
    # Client hires (convert min/max to ranges)
    if 'hires_min' in params or 'hires_max' in params:
        ranges = []
        min_val = int(params.get('hires_min', 0))
        max_val = int(params.get('hires_max', float('inf')))
        if min_val <= 9 and max_val >= 1:
            ranges.append('1-9')
        if max_val >= 10:
            ranges.append('10-')
        if ranges:
            result['client_hires'] = ','.join(ranges)
    
    # Expertise level (contractor tier)
    if 'expertise_level_number' in params:
        result['contractor_tier'] = ','.join(params['expertise_level_number'])
    
    # Duration
    if 'projectDuration' in params:
        result['duration_v3'] = ','.join(params['projectDuration'])
    
    # Hourly rate range
    if 'hourly_min' in params and 'hourly_max' in params:
        result['hourly_rate'] = f"{params['hourly_min']}-{params['hourly_max']}"
    
    # Job type (hourly/fixed)
    job_types = []
    if params.get('hourly'):
        job_types.append('0')
    if params.get('fixed'):
        job_types.append('1')
    if job_types:
        result['t'] = ','.join(job_types)
    
    # Workload mapping
    if 'workload' in params:
        workload_map = {
            'part_time': 'as_needed',
            'full_time': 'full_time'
        }
        result['workload'] = ','.join(workload_map[w] for w in params['workload'] if w in workload_map)
    
    # Sort order
    if 'sort' in params:
        sort_map = {
            'relevance': 'relevance+desc',
            'newest': 'recency',
            'client_total_charge': 'client_total_charge+desc',
            'client_rating': 'client_rating+desc'
        }
        result['sort'] = sort_map.get(params['sort'], params['sort'])
    
    # Query building
    q_parts = []
    
    # Main query
    if params.get('query'):
        q_parts.append(params['query'])
    
    # Any words (OR)
    if params.get('search_any'):
        words = params['search_any'].split()
        q_parts.append(f"({' OR '.join(words)})")
    
    if q_parts:
        result['q'] = ' AND '.join(q_parts)
    
    # Pass through boolean/string params that map directly
    for key in ['contract_to_hire', 'previous_clients']:
        if key in params:
            result[key] = str(params[key]).lower()

    # login required fields
    if not credentials_provided:
        result['proposals'] = ""
        result['payment_verified'] = ""
        result['previous_clients'] = ""
    else:
        # Proposal number (proposals filter) from a direct string input
        if 'proposal_num' in params and params['proposal_num']:
            result['proposals'] = ','.join(params['proposal_num'])
        # payment verified
        if 'payment_verified' in params and params['payment_verified']:
            result['payment_verified'] = '1'
    

    # Categories (main category UID and subcategory UID)
    if 'category' in params and params['category']:
        main_cat_uids = []
        sub_cat_uids = []
        for cat_name in params['category']:
            cat_name_lower = cat_name.lower()
            if cat_name_lower in UPWORK_MAIN_CATEGORIES:
                main_cat_uids.append(UPWORK_MAIN_CATEGORIES[cat_name_lower])
            elif cat_name_lower in UPWORK_SUBCATEGORIES:
                sub_cat_uids.append(UPWORK_SUBCATEGORIES[cat_name_lower])
            else:
                logger.warning(f"Category '{cat_name}' not found in any category map, skipping.")

        if main_cat_uids:
            result['category2_uid'] = ','.join(main_cat_uids)
        if sub_cat_uids:
            result['subcategory2_uid'] = ','.join(sub_cat_uids)
    
    return result, limit

def build_upwork_search_url(params: dict) -> str:
    """
    Build an Upwork job search URL from the given parameters dict.

    :param params: Dictionary of normalized search parameters
    :type params: dict
    :return: Upwork job search URL as a string
    :rtype: str
    """
    base_url = params.get('base_url', 'https://www.upwork.com/nx/search/jobs/')
    # Advanced search logic for 'q'
    q_parts = []
    if params.get('all_words'):
        q_parts.append(params['all_words'])
    if params.get('any_words'):
        q_parts.append('(' + ' OR '.join(params['any_words'].split()) + ')')
    if params.get('none_words'):
        q_parts.append(' '.join(f'-{w}' for w in params['none_words'].split()))
    if params.get('exact_phrase'):
        q_parts.append(f'"{params["exact_phrase"]}"')
    if params.get('title_search'):
        q_parts.append(' '.join(f'title:{w}' for w in params['title_search'].split()))
    q = ' '.join(q_parts) if q_parts else params.get('q', '')
    # If only 'q' is present, return minimal URL
    minimal_keys = {'q', 'base_url'}
    if set(params.keys()).issubset(minimal_keys) or (q and len(params) == 1):
        from urllib.parse import urlencode
        return f"{base_url}?" + urlencode({'q': q})
    # Otherwise, add filters if present
    url_params = {'q': q}
    filter_keys = [
        'amount', 'client_hires', 'hourly_rate', 'payment_verified', 'per_page',
        'sort', 't', 'contract_to_hire', 'contractor_tier', 'duration_v3',
        'nbs', 'previous_clients', 'proposals', 'workload', 'category2_uid', 'subcategory2_uid'
    ]
    for k in filter_keys:
        if k in params:
            url_params[k] = params[k]
    # Add any extra params present in config/inputJson
    for k in params:
        if k not in url_params and k not in ['base_url', 'all_words', 'any_words', 'none_words', 'exact_phrase', 'title_search', 'q']:
            url_params[k] = params[k]
    from urllib.parse import urlencode
    return f"{base_url}?" + urlencode(url_params)

async def safe_goto(
    page: Page,
    url: str,
    browser_context: BrowserContext,
    max_retries: int = 3,
    timeout: int = 30000,
    wait_untils: list[str] = ["domcontentloaded", "networkidle"]
) -> Page:
    """
    Safely navigate a Playwright page to a URL with retries and error handling.

    :param page: Playwright Page object to navigate
    :type page: Page
    :param url: URL to navigate to
    :type url: str
    :param browser_context: Playwright BrowserContext for creating new pages if needed
    :type browser_context: BrowserContext
    :param max_retries: Maximum number of navigation attempts
    :type max_retries: int
    :param timeout: Timeout for each navigation attempt (ms)
    :type timeout: int
    :param wait_untils: List of waitUntil events for navigation
    :type wait_untils: list[str]
    :return: The navigated Playwright Page object
    :rtype: Page
    """
    last_exc = None

    for attempt in range(1, max_retries + 1):
        for wait_until in wait_untils:
            try:
                logger.debug(f"[Attempt {attempt}] goto({url}) waitUntil={wait_until}")
                response = await page.goto(url, timeout=timeout, wait_until=wait_until)
                logger.debug(f"[Attempt {attempt}] Navigation succeeded (waitUntil={wait_until})")
                # return working page
                return page  
            except TargetClosedError:
                logger.warning("Page or browser crashed. Creating new page...")
                try:
                    page = await browser_context.new_page()
                except Exception as create_exc:
                    logger.exception("Failed to create new page after crash.")
                    raise create_exc
            except Exception as e:
                last_exc = e
                logger.debug(f"[Attempt {attempt}] goto failed: {e}")

    logger.error(f"⚠️ Failed to navigate to {url} after {max_retries} attempts", exc_info=last_exc)
    raise last_exc

async def login_process(
    login_url: str,
    page: Page,
    context: BrowserContext,
    username: str,
    password: str,
    max_attempts: int = 2
) -> bool:
    """
    Automate the Upwork login process using Playwright, with robust retry logic.
    Tries reloading and creating a new page, but does NOT clear cookies unless all else fails.

    :param login_url: Upwork login URL
    :type login_url: str
    :param page: Playwright Page object
    :type page: Page
    :param context: Playwright BrowserContext
    :type context: BrowserContext
    :param username: Upwork username/email
    :type username: str
    :param password: Upwork password
    :type password: str
    :param max_attempts: Maximum number of login attempts
    :type max_attempts: int
    :return: True if login succeeded, False otherwise
    :rtype: bool
    """
    for attempt in range(1, max_attempts + 1):
        try:
            page = await safe_goto(page, login_url, context, timeout=60000)
            await page.wait_for_selector('#login_username', timeout=10000)
            await page.fill('#login_username', username)
            logger.debug(f"Username entered: {username}")
            await page.press('#login_username', 'Enter')
            await asyncio.sleep(2)
            await page.wait_for_selector('#login_password', timeout=10000)
            await page.fill('#login_password', password)
            logger.debug(f"Password entered.")
            await page.press('#login_password', 'Enter')
            await asyncio.sleep(3)
            
            # Check for 2FA verification code input
            body_text = await page.locator('body').inner_text()
            page_url = page.url
            
            # Common 2FA indicators
            two_factor_indicators = [
                'verification code',
                'enter code',
                'two-factor',
                '2fa',
                'authentication code',
                'security code',
                'enter the code',
                'verif'  # Short for verification
            ]
            
            # Check if 2FA is required
            is_2fa_required = False
            for indicator in two_factor_indicators:
                if indicator.lower() in body_text.lower():
                    is_2fa_required = True
                    break
            
            # Also check for common 2FA input field selectors
            two_factor_selectors = [
                'input[type="text"][name*="code"]',
                'input[type="text"][name*="verification"]',
                'input[type="text"][name*="otp"]',
                'input[type="number"][name*="code"]',
                'input[id*="code"]',
                'input[id*="verification"]',
                'input[id*="otp"]',
                'input[placeholder*="code" i]',
                'input[placeholder*="verification" i]',
            ]
            
            for selector in two_factor_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        is_2fa_required = True
                        break
                except:
                    pass
            
            if is_2fa_required:
                logger.info("🔐 Two-factor authentication (2FA) detected!")
                logger.info("⏳ Waiting for you to enter the verification code in the browser...")
                logger.info("💡 Please enter the code from your SMS/authenticator app and complete the login.")
                
                # Wait for successful login - check for indicators that login completed
                max_wait_time = 300  # 5 minutes max wait
                check_interval = 2  # Check every 2 seconds
                waited_time = 0
                
                login_success_indicators = [
                    '/home',
                    '/find-work',
                    '/nx/find-work',
                    '/dashboard',
                    'upwork.com/nx',
                ]
                
                while waited_time < max_wait_time:
                    await asyncio.sleep(check_interval)
                    waited_time += check_interval
                    
                    try:
                        current_url = page.url
                        current_body = await page.locator('body').inner_text()
                        
                        # Check if we're logged in by URL
                        for indicator in login_success_indicators:
                            if indicator in current_url.lower():
                                logger.info("✅ Login successful! 2FA verification completed.")
                                return True
                        
                        # Check if 2FA field is still present (login not complete)
                        still_has_2fa = False
                        for selector in two_factor_selectors:
                            try:
                                element = await page.query_selector(selector)
                                if element:
                                    still_has_2fa = True
                                    break
                            except:
                                pass
                        
                        # If 2FA field is gone and we're not on login page, assume success
                        if not still_has_2fa and 'login' not in current_url.lower() and 'account-security' not in current_url.lower():
                            # Check for login success indicators in body
                            if 'log out' in current_body.lower() or 'sign out' in current_body.lower() or 'dashboard' in current_body.lower():
                                logger.info("✅ Login successful! 2FA verification completed.")
                                return True
                        
                        # Show progress every 30 seconds
                        if waited_time % 30 == 0:
                            logger.info(f"⏳ Still waiting for 2FA code... ({waited_time}s / {max_wait_time}s)")
                    
                    except Exception as e:
                        logger.debug(f"Error checking login status: {e}")
                        continue
                
                logger.warning("⚠️ Timeout waiting for 2FA verification. Please check if login was successful.")
                # Final check
                try:
                    current_url = page.url
                    for indicator in login_success_indicators:
                        if indicator in current_url.lower():
                            logger.info("✅ Login successful!")
                            return True
                except:
                    pass
                
                return False
            
            body_text_lower = body_text.lower()

            # Check for explicit login error messages across full page text
            login_error_indicators = [
                'username or password is incorrect',
                'verification failed. please try again.',
                'please fix the errors below',
                'unable to process your request',
                'invalid username or password',
            ]
            if any(indicator in body_text_lower for indicator in login_error_indicators):
                logger.debug(f"Verification on login failed. Attempt {attempt}/{max_attempts}")
                # Try reloading or creating a new page, but do NOT clear cookies yet
                if attempt == max_attempts // 2:
                    logger.debug("Creating a new page due to repeated login failures.")
                    page = await context.new_page()
                continue

            # Success heuristics: after submit we must leave login pages or see signed-in cues
            page_url_lower = page_url.lower()
            if (
                ('account-security/login' in page_url_lower or '/login' in page_url_lower)
                and 'dashboard' not in body_text_lower
                and 'log out' not in body_text_lower
                and 'sign out' not in body_text_lower
            ):
                logger.debug("Still on login page after submit; treating as unsuccessful login attempt.")
                continue

            logger.debug("Login process complete.")
            logger.debug(f"Body text: {body_text[:160]}")
            return True
        except Exception as e:
            logger.debug(f"Login attempt {attempt} failed: {e}")
            await asyncio.sleep(3)
    logger.error("⚠️ All login attempts failed.")
    return False

async def login_and_solve(
    page: Page,
    context: BrowserContext,
    username: str,
    password: str,
    search_url: str,
    login_url: str,
    credentials_provided: bool,
    cookies_file_path: str = None
) -> tuple[Page, BrowserContext]:
    """
    Navigate to Upwork, solve captcha if present, and log in if credentials are provided.
    If a new context or cookies are cleared, re-solve captcha before login.
    Tries to load saved cookies first, and saves cookies after successful login.

    :param page: Playwright Page object to use for navigation and interaction
    :type page: Page
    :param context: Playwright BrowserContext object
    :type context: BrowserContext
    :param username: Upwork username/email
    :type username: str
    :param password: Upwork password
    :type password: str
    :param search_url: Upwork job search URL to visit initially
    :type search_url: str
    :param login_url: Upwork login URL
    :type login_url: str
    :param credentials_provided: Whether Upwork credentials are provided (affects login behavior)
    :type credentials_provided: bool
    :param cookies_file_path: Path to cookies file for saving/loading
    :type cookies_file_path: str, optional
    :return: Tuple of (page, context) after login/captcha (or attempted login)
    :rtype: tuple[Page, BrowserContext]
    """
    # Try to load saved cookies first if credentials are provided
    if credentials_provided and cookies_file_path:
        cookies_loaded = await load_cookies_from_file(context, cookies_file_path)
        if cookies_loaded:
            # Verify cookies are still valid
            logger.info("🔍 Verifying saved cookies...")
            await safe_goto(page, search_url, context)
            # Solve captcha if needed
            captcha_solved = await solve_captcha(queryable=page, browser_context=context, captcha_type='cloudflare', challenge_type='interstitial', solve_attempts = 5, solve_click_delay = 6, wait_checkbox_attempts = 5, wait_checkbox_delay = 5, checkbox_click_attempts = 3, attempt_delay = 5)
            if captcha_solved:
                logger.debug(f"Successfully solved captcha challenge!")
            
            cookies_valid = await verify_cookies_validity(page, context)
            if cookies_valid:
                logger.info("✅ Using saved cookies - login not required!")
                return page, context
            else:
                logger.info("⚠️ Saved cookies are invalid or expired. Proceeding with login...")
                await context.clear_cookies()
    
    # go to search url
    await safe_goto(page, search_url, context)
    # bypass captcha
    logger.debug(f"Checking for captcha challenge...")
    captcha_solved = await solve_captcha(queryable=page, browser_context=context, captcha_type='cloudflare', challenge_type='interstitial', solve_attempts = 5, solve_click_delay = 6, wait_checkbox_attempts = 5, wait_checkbox_delay = 5, checkbox_click_attempts = 3, attempt_delay = 5)
    if captcha_solved:
        logger.debug(f"Successfully solved captcha challenge!")
    else:
        logger.warning(f"⚠️ No captcha challenge detected or failed to solve captcha.")
    # if credentials are provided, login
    if credentials_provided:
        logger.info("🔐 Credentials provided - attempting login...")
        logger.debug(f"Logging in...")
        login_success = await login_process(login_url, page, context, username, password)
        # if login fails, try clearing cookies and re-solving captcha
        if not login_success:
            logger.error("⚠️ Login failed after all attempts.")
            logger.info("🔴 Attempting last resort: clear cookies, re-solve captcha, and retry login...")
            try:
                await context.clear_cookies()
                page = await context.new_page()
                await safe_goto(page, search_url, context)
                # Re-solve captcha
                captcha_solved = await solve_captcha(queryable=page, browser_context=context, captcha_type='cloudflare', challenge_type='interstitial', solve_attempts = 5, solve_click_delay = 6, wait_checkbox_attempts = 5, wait_checkbox_delay = 5, checkbox_click_attempts = 3, attempt_delay = 5)
                if captcha_solved:
                    logger.info("✅ Captcha solved after clearing cookies. Retrying login...")
                else:
                    logger.warning("⚠️ Captcha could not be solved after clearing cookies.")
                # Retry login
                login_success = await login_process(login_url, page, context, username, password)
                if not login_success:
                    logger.error("⚠️Login still failed after last resort attempt (clear cookies, re-solve captcha, retry login). Aborting.")
                    # print body text
                    body_text = await page.locator('body').inner_text()
                    logger.debug(f"Body text: {body_text}")
                else:
                    logger.info("✅ Login succeeded after last resort attempt.")
                    # Save cookies after successful login
                    if cookies_file_path:
                        await save_cookies_to_file(context, cookies_file_path)
                    # return page and context so that new context is used for scraping
                    return page, context
            except Exception as e:
                logger.error(f"⚠️ Exception during last resort login attempt: {e}")
        else:
            # Login succeeded on first attempt - save cookies
            if cookies_file_path:
                await save_cookies_to_file(context, cookies_file_path)
    else:
        logger.info("ℹ️ No credentials provided - skipping login, proceeding with search only")
    return page, context


async def save_cookies_to_file(context: BrowserContext, cookies_file_path: str):
    """
    Save cookies from Playwright context to a JSON file.

    :param context: Playwright BrowserContext object
    :type context: BrowserContext
    :param cookies_file_path: Path to the cookies file
    :type cookies_file_path: str
    """
    try:
        cookies = await context.cookies()
        # Ensure directory exists
        os.makedirs(os.path.dirname(cookies_file_path), exist_ok=True)
        with open(cookies_file_path, 'w') as f:
            json.dump(cookies, f, indent=2)
        logger.info(f"💾 Cookies saved to {cookies_file_path}")
    except Exception as e:
        logger.warning(f"⚠️ Failed to save cookies: {e}")

async def load_cookies_from_file(context: BrowserContext, cookies_file_path: str) -> bool:
    """
    Load cookies from a JSON file into Playwright context.

    :param context: Playwright BrowserContext object
    :type context: BrowserContext
    :param cookies_file_path: Path to the cookies file
    :type cookies_file_path: str
    :return: True if cookies were loaded successfully, False otherwise
    :rtype: bool
    """
    try:
        if not os.path.exists(cookies_file_path):
            logger.debug(f"Cookies file not found: {cookies_file_path}")
            return False
        
        with open(cookies_file_path, 'r') as f:
            cookies = json.load(f)
        
        if not cookies:
            logger.debug("Cookies file is empty")
            return False
        
        await context.add_cookies(cookies)
        logger.info(f"📂 Cookies loaded from {cookies_file_path}")
        return True
    except Exception as e:
        logger.warning(f"⚠️ Failed to load cookies: {e}")
        return False

async def verify_cookies_validity(page: Page, context: BrowserContext) -> bool:
    """
    Verify if loaded cookies are still valid by checking if we're logged in.

    :param page: Playwright Page object
    :type page: Page
    :param context: Playwright BrowserContext object
    :type context: BrowserContext
    :return: True if cookies are valid (user is logged in), False otherwise
    :rtype: bool
    """
    try:
        # Try to navigate to a page that requires authentication
        await page.goto('https://www.upwork.com/nx/find-work/', timeout=30000, wait_until='domcontentloaded')
        await asyncio.sleep(2)
        
        body_text = await page.locator('body').inner_text()
        current_url = page.url
        
        # Check if we're logged in
        login_indicators = ['log in', 'sign up', 'account-security/login']
        logged_in_indicators = ['find work', 'dashboard', 'log out', 'sign out', '/nx/find-work']
        
        # If we see login indicators, cookies are invalid
        for indicator in login_indicators:
            if indicator.lower() in body_text.lower() or indicator in current_url.lower():
                logger.debug("Cookies appear to be invalid (login page detected)")
                return False
        
        # If we see logged in indicators, cookies are valid
        for indicator in logged_in_indicators:
            if indicator.lower() in body_text.lower() or indicator in current_url.lower():
                logger.info("✅ Cookies are valid - user is logged in")
                return True
        
        # If URL contains /nx/ and not login, assume valid
        if '/nx/' in current_url and 'login' not in current_url:
            logger.info("✅ Cookies appear to be valid")
            return True
        
        return False
    except Exception as e:
        logger.debug(f"Error verifying cookies: {e}")
        return False

def playwright_cookies_to_requests(cookies):
    """
    Convert Playwright cookies to a RequestsCookieJar.

    :param cookies: List of cookies from Playwright context
    :type cookies: list[dict]
    :return: RequestsCookieJar containing the cookies
    :rtype: requests.cookies.RequestsCookieJar
    """
    jar = requests.cookies.RequestsCookieJar()
    for cookie in cookies:
        jar.set(cookie['name'], cookie['value'], domain=cookie['domain'], path=cookie['path'])
    return jar

def _build_proxy_url_from_details(proxy_details: dict | None) -> str | None:
    """
    Build a proxy URL suitable for requests from a `proxy_details` dict.

    Expected keys:
    - server: base proxy URL (may already include scheme and credentials)
    - username: optional username
    - password: optional password

    Returns a URL string like: http://user:pass@host:port or None if unavailable.
    """
    if not proxy_details:
        return None
    server = proxy_details.get('server')
    if not server:
        return None
    # Ensure scheme present for parsing
    if not server.startswith(('http://', 'https://')):
        server = f"http://{server}"
    parsed = urlparse(server)
    # If credentials already embedded, keep as-is
    if parsed.username or '@' in server:
        return urlunparse(parsed)
    username = proxy_details.get('username')
    password = proxy_details.get('password')
    if not (username and password):
        return urlunparse(parsed)
    # Inject credentials
    netloc = parsed.netloc
    # If netloc contains host:port, prepend credentials
    netloc_with_auth = f"{username}:{password}@{netloc}"
    parsed_with_auth = parsed._replace(netloc=netloc_with_auth)
    return urlunparse(parsed_with_auth)


async def get_requests_session_from_playwright(context, page, max_retries=3, retry_delay=1, proxy_details: dict | None = None):
    """
    Extract cookies and user-agent from Playwright context and page, and build a requests.Session.
    Retries user-agent extraction if the execution context is destroyed.

    :param context: Playwright BrowserContext object
    :type context: BrowserContext
    :param page: Playwright Page object
    :type page: Page
    :param max_retries: Maximum number of retries for user-agent extraction if execution context is destroyed (default: 3)
    :type max_retries: int
    :param retry_delay: Delay in seconds between retries (default: 1)
    :type retry_delay: int
    :return: requests.Session object with cookies and user-agent set
    :rtype: requests.Session
    """
    cookies = await context.cookies()
    user_agent = None
    for attempt in range(1, max_retries + 1):
        try:
            user_agent = await page.evaluate("() => navigator.userAgent")
            break
        except Exception as e:
            if "Execution context was destroyed" in str(e):
                logger.warning(f"Attempt {attempt}: Execution context destroyed while getting user-agent. Retrying...")
                await asyncio.sleep(retry_delay)
                if attempt == max_retries:
                    logger.error("Failed to get user-agent after multiple retries due to navigation/context loss. Using fallback user-agent.")
                    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
            else:
                logger.error(f"Unexpected error while getting user-agent: {e}. Using fallback user-agent.")
                user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
                break
    if not user_agent:
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
    session = requests.Session()
    session.cookies = playwright_cookies_to_requests(cookies)
    session.headers.update({'User-Agent': user_agent})
    # Apply proxy to requests session if provided
    proxy_url = _build_proxy_url_from_details(proxy_details)
    if proxy_url:
        session.proxies.update({
            'http': proxy_url,
            'https': proxy_url,
        })
        logger.debug(f"session.proxies updated to: {proxy_url}")
    return session


def get_job_urls_requests(session, search_querys, search_urls, limit=50):
    """
    For each search query and URL, use requests to fetch the page and extract job URLs.

    :param session: requests.Session object with cookies and headers set
    :type session: requests.Session
    :param search_querys: List of search query strings
    :type search_querys: list[str]
    :param search_urls: List of Upwork search URLs corresponding to the queries
    :type search_urls: list[str]
    :param limit: Maximum number of job URLs to extract per query
    :type limit: int, optional
    :return: Dictionary mapping each query to a list of job URLs
    :rtype: dict[str, list[str]]
    """
    search_results = {}
    for query, base_url in zip(search_querys, search_urls):
        all_hrefs = []
        pages_needed = (limit + 49) // 50
        jobs_from_last_page = limit % 50 or 50
        for page_num in range(1, pages_needed + 1):
            url = f"{base_url}&page={page_num}" if page_num > 1 else base_url
            logger.debug(f"[requests] Fetching URL: {url}")
            try:
                resp = session.get(url, timeout=30)
                resp.raise_for_status()
                html = resp.text
                
                # Check for "log in" string in the first iteration of the first query to detect login issues
                if page_num == 1 and query == search_querys[0]:
                    if "log in" in html.lower():
                        logger.warning("⚠️ 'log in' string detected in HTML response. This indicates the session may not be properly authenticated.")
                        logger.warning(f"HTML snippet containing 'log in': {html[html.lower().find('log in'):html.lower().find('log in')+200]}")
                
                soup = BeautifulSoup(html, 'html.parser')
                articles = soup.find_all('article')
                page_hrefs = []
                for i, article in enumerate(articles):
                    a_tag = article.find('a', attrs={'data-test': 'job-tile-title-link UpLink'})
                    if not a_tag:
                        for a in article.find_all('a', href=True):
                            if '/jobs/' in a['href'] and '~' in a['href']:
                                a_tag = a
                                break
                    if a_tag and a_tag.has_attr('href'):
                        href = a_tag['href']
                        match = re.search(r'~([0-9a-zA-Z]+)', href)
                        if match:
                            job_id = match.group(0)
                            job_url = f"https://www.upwork.com/jobs/{job_id}"
                            page_hrefs.append(job_url)
                logger.debug(f"Found {len(page_hrefs)} jobs on page {page_num} for query '{query}'")
                if page_num == pages_needed:
                    page_hrefs = page_hrefs[:jobs_from_last_page]
                all_hrefs.extend(page_hrefs)
                if len(all_hrefs) >= limit:
                    all_hrefs = all_hrefs[:limit]
                    break
            except Exception as e:
                logger.exception(f"[requests] Skipping page {page_num} due to navigation failures: {e}")
                continue
        search_results[query] = all_hrefs
    logger.debug(f"[requests] Search results: {search_results}\n")
    return search_results


def fetch_job_detail(session, url, credentials_provided):
    """
    Fetch job detail page and extract job attributes.

    :param session: requests.Session object with cookies and headers set
    :type session: requests.Session
    :param url: URL of the job detail page
    :type url: str
    :param credentials_provided: Whether Upwork credentials are provided (affects restricted fields)
    :type credentials_provided: bool
    :return: Dictionary of job attributes, or None if failed
    :rtype: dict or None
    """
    try:
        logger.debug(f"[requests] Processing URL: {url}")
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        html = resp.text
        job_id_match = re.search(r'~([0-9a-zA-Z]+)', url)
        job_id = job_id_match.group(1) if job_id_match else "0"
        attrs = extract_job_attributes(html)
        attrs['url'] = url
        attrs['job_id'] = job_id
        logger.debug(f"[requests] Job ID: {job_id}")
        return attrs
    except Exception as e:
        logger.debug(f"[requests] Failed to process {url}")
        logger.debug(f"[requests] Error: {e}")
        return None

def browser_worker_requests(session, job_urls, credentials_provided, max_workers=20):
    """
    Fetch job details sequentially with delay to avoid rate limiting.

    :param session: requests.Session object with cookies and headers set
    :type session: requests.Session
    :param job_urls: List of job detail page URLs to fetch
    :type job_urls: list[str]
    :param credentials_provided: Whether Upwork credentials are provided (affects restricted fields)
    :type credentials_provided: bool
    :param max_workers: Maximum number of worker threads to use (not used, kept for compatibility)
    :type max_workers: int, optional
    :return: List of job attribute dictionaries
    :rtype: list[dict]
    """
    job_attributes = []
    request_delay = 1  # Delay in seconds between requests
    
    for i, url in enumerate(job_urls):
        result = fetch_job_detail(session, url, credentials_provided)
        if result:
            job_attributes.append(result)
        
        # Add delay between requests (except for the last one)
        if i < len(job_urls) - 1:
            time.sleep(request_delay)
    
    return job_attributes


def resolve_credentials(json_input: dict) -> tuple[str | None, str | None]:
    """Resolve credentials from json input with .env fallback."""
    credentials_json = json_input.get("credentials", json_input)
    username = credentials_json.get("username") or os.getenv("UPWORK_USERNAME")
    password = credentials_json.get("password") or os.getenv("UPWORK_PASSWORD")
    return username, password


def build_cookies_file_path(username: str | None) -> str | None:
    """Build per-user cookies file path based on username."""
    if not username:
        return None
    safe_username = re.sub(r"[^\w\-_.]", "_", username)
    project_dir = Path(__file__).resolve().parent
    cookies_dir = project_dir / "cookies"
    os.makedirs(cookies_dir, exist_ok=True)
    return str(cookies_dir / f"{safe_username}_cookies.json")


def parse_and_validate_limit(search_params: dict, *, required: bool) -> int:
    """Validate limit from search params and return int."""
    raw_limit = search_params.get("limit", None)
    if raw_limit is None:
        if required:
            raise RuntimeError("search.limit is required and must be an integer from 1 to 100.")
        return 20
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        raise RuntimeError("search.limit must be an integer from 1 to 100.")
    if limit < 1 or limit > 100:
        raise RuntimeError("search.limit must be in range 1..100.")
    return limit


def extract_job_id_from_url(url: str) -> str | None:
    match = re.search(r"~([0-9a-zA-Z]+)", url)
    return match.group(1) if match else None


def get_db_path() -> str:
    project_dir = Path(__file__).resolve().parent
    return str(project_dir / "data" / "upwork_jobs.db")


DETAIL_COLUMNS = [
    "title",
    "description",
    "url",
    "job_id",
    "type",
    "level",
    "duration",
    "category",
    "category_name",
    "category_urlSlug",
    "categoryGroup_name",
    "categoryGroup_urlSlug",
    "hourly_min",
    "hourly_max",
    "fixed_budget_amount",
    "currency",
    "connects_required",
    "client_country",
    "client_company_size",
    "client_industry",
    "client_hires",
    "client_rating",
    "client_reviews",
    "client_total_spent",
    "buyer_hire_rate_pct",
    "buyer_avgHourlyJobsRate_amount",
    "buyer_jobs_openCount",
    "buyer_jobs_postedCount",
    "buyer_stats_hoursCount",
    "buyer_stats_totalJobsWithHires",
    "buyer_stats_activeAssignmentsCount",
    "buyer_company_contractDate",
    "buyer_location_city",
    "buyer_location_countryTimezone",
    "buyer_location_localTime",
    "buyer_location_offsetFromUtcMillis",
    "clientActivity_invitationsSent",
    "clientActivity_totalHired",
    "clientActivity_totalInvitedToInterview",
    "clientActivity_unansweredInvites",
    "lastBuyerActivity",
    "applicants",
    "numberOfPositionsToHire",
    "skills",
    "qualifications",
    "questions",
    "contractorTier",
    "payment_verified",
    "phone_verified",
    "premium",
    "enterpriseJob",
    "isContractToHire",
    "ts_create",
    "ts_publish",
]


def to_db_text(value):
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def upsert_parsed_job(
    conn: sqlite3.Connection,
    target_table: str,
    fk_column: str,
    fk_id: int,
    details: dict,
) -> None:
    data = {col: to_db_text(details.get(col)) for col in DETAIL_COLUMNS}
    data["payload_json"] = json.dumps(details, ensure_ascii=False)

    columns = [fk_column, "fetched_at"] + DETAIL_COLUMNS + ["payload_json"]
    placeholders = ", ".join(["?"] * len(columns))
    update_cols = ["fetched_at"] + DETAIL_COLUMNS + ["payload_json"]
    update_sql = ", ".join([f"{col}=excluded.{col}" for col in update_cols])

    values = [fk_id, datetime.datetime.utcnow().isoformat()] + [data[col] for col in DETAIL_COLUMNS] + [data["payload_json"]]

    conn.execute(
        f"""
        INSERT INTO {target_table} ({", ".join(columns)})
        VALUES ({placeholders})
        ON CONFLICT({fk_column}) DO UPDATE SET
        {update_sql}
        """,
        values,
    )


def fetch_unchecked_jobs(table_name: str, limit: int) -> list[dict]:
    """Fetch unchecked jobs from DB and mark them as checked."""
    if table_name not in ("jobs", "job_bestmach"):
        raise RuntimeError(f"Unsupported jobs table: {table_name}")
    if limit < 1 or limit > 1000:
        raise RuntimeError("limit must be in range 1..1000.")

    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        rows = conn.execute(
            f"""
            SELECT *
            FROM {table_name}
            WHERE is_checked = 0
            ORDER BY fetched_at ASC, id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        if not rows:
            return []

        ids = [row["id"] for row in rows]
        placeholders = ",".join(["?"] * len(ids))
        conn.execute(
            f"UPDATE {table_name} SET is_checked = 1 WHERE id IN ({placeholders})",
            ids,
        )
        conn.commit()

        result = []
        for row in rows:
            item = dict(row)
            payload_raw = item.get("payload_json")
            if payload_raw:
                try:
                    item["payload_json"] = json.loads(payload_raw)
                except json.JSONDecodeError:
                    pass
            result.append(item)
        return result
    finally:
        conn.close()


def parse_limit_from_input(json_input: dict) -> int:
    limit_value = json_input.get("limit")
    if limit_value is None and isinstance(json_input.get("search"), dict):
        limit_value = json_input["search"].get("limit")
    if limit_value is None:
        raise RuntimeError("limit is required and must be an integer from 1 to 1000.")
    try:
        limit = int(limit_value)
    except (TypeError, ValueError):
        raise RuntimeError("limit must be an integer from 1 to 1000.")
    if limit < 1 or limit > 1000:
        raise RuntimeError("limit must be in range 1..1000.")
    return limit


def cli_pull_unchecked_jobs(json_input: dict, table_name: str) -> list[dict]:
    limit = parse_limit_from_input(json_input)
    jobs = fetch_unchecked_jobs(table_name, limit)
    print(json.dumps(jobs, ensure_ascii=False))
    logger.info(f"✅ Pulled from {table_name}: {len(jobs)}")
    return jobs


async def cli_parse_urls_to_jobs(json_input: dict, source_table: str) -> dict:
    """
    Parse only unprocessed URLs (is_parse=0) from source table and store details.
    """
    if source_table == "job_urls":
        target_table = "jobs"
        fk_column = "job_url_id"
    elif source_table == "job_urls_bestmatch":
        target_table = "job_bestmach"
        fk_column = "job_url_bestmatch_id"
    else:
        raise RuntimeError(f"Unsupported source table: {source_table}")

    username, _ = resolve_credentials(json_input)
    if not username:
        raise RuntimeError("UPWORK_USERNAME is required to locate cookies. Set it in .env or pass credentials.username.")
    cookies_file_path = build_cookies_file_path(username)
    if not cookies_file_path or not os.path.exists(cookies_file_path):
        raise RuntimeError("Cookies not found. Run login command first.")

    proxy_details = json_input.get("proxy_details", None)
    session = await build_authenticated_requests_session(
        "https://www.upwork.com/nx/find-work/",
        cookies_file_path,
        proxy_details,
    )

    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    parsed_count = 0
    failed_count = 0
    skipped_count = 0
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        rows = conn.execute(
            f"SELECT id, url FROM {source_table} WHERE is_parse = 0 ORDER BY id ASC"
        ).fetchall()

        if not rows:
            logger.info(f"ℹ️ No unparsed URLs in {source_table}.")
            return {"parsed": 0, "failed": 0, "skipped": 0}

        for row_id, url in rows:
            details = fetch_job_detail(session, url, credentials_provided=True)
            if not details:
                failed_count += 1
                continue
            try:
                upsert_parsed_job(conn, target_table, fk_column, row_id, details)
                conn.execute(
                    f"UPDATE {source_table} SET is_parse = 1, last_seen_at = datetime('now') WHERE id = ?",
                    (row_id,),
                )
                parsed_count += 1
            except Exception as db_err:
                logger.debug(f"Failed DB upsert for {url}: {db_err}")
                skipped_count += 1

        conn.commit()
    finally:
        conn.close()

    logger.info(
        f"✅ Parsed from {source_table}: parsed={parsed_count}, failed={failed_count}, skipped={skipped_count}"
    )
    return {"parsed": parsed_count, "failed": failed_count, "skipped": skipped_count}


def save_job_urls_to_db(urls: list[str], query: str, table_name: str) -> int:
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    inserted_or_updated = 0
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        for url in urls:
            job_id = extract_job_id_from_url(url)
            if table_name == "job_urls":
                conn.execute(
                    """
                    INSERT INTO job_urls (url, job_id, query)
                    VALUES (?, ?, ?)
                    ON CONFLICT(url) DO UPDATE SET
                        job_id=excluded.job_id,
                        query=excluded.query,
                        last_seen_at=datetime('now')
                    """,
                    (url, job_id, query),
                )
            elif table_name == "job_urls_bestmatch":
                conn.execute(
                    """
                    INSERT INTO job_urls_bestmatch (url, job_id)
                    VALUES (?, ?)
                    ON CONFLICT(url) DO UPDATE SET
                        job_id=excluded.job_id,
                        last_seen_at=datetime('now')
                    """,
                    (url, job_id),
                )
            else:
                raise RuntimeError(f"Unsupported URL table: {table_name}")
            inserted_or_updated += 1
        conn.commit()
    finally:
        conn.close()
    return inserted_or_updated


async def build_authenticated_requests_session(search_url: str, cookies_file_path: str, proxy_details: dict | None):
    async with AsyncCamoufox(headless=True, geoip=True, humanize=True, i_know_what_im_doing=True, config={'forceScopeAccess': True}, disable_coop=True, proxy=proxy_details) as browser:
        context = await browser.new_context()
        page = await context.new_page()

        cookies_loaded = await load_cookies_from_file(context, cookies_file_path)
        if not cookies_loaded:
            raise RuntimeError("Failed to load cookies. Run login command again.")

        await safe_goto(page, search_url, context)
        await solve_captcha(
            queryable=page,
            browser_context=context,
            captcha_type='cloudflare',
            challenge_type='interstitial',
            solve_attempts=5,
            solve_click_delay=6,
            wait_checkbox_attempts=5,
            wait_checkbox_delay=5,
            checkbox_click_attempts=3,
            attempt_delay=5,
        )

        cookies_valid = await verify_cookies_validity(page, context)
        if not cookies_valid:
            raise RuntimeError("Cookies are expired or invalid. Run login command again.")

        return await get_requests_session_from_playwright(context, page, proxy_details=proxy_details)


async def cli_collect_urls(json_input: dict) -> int:
    """Collect job URLs by query/limit and store into job_urls table."""
    search_params = json_input.get("search", {}) or {}
    if not isinstance(search_params, dict):
        raise RuntimeError("search must be a JSON object.")

    query_value = (search_params.get("query") or "").strip()
    if not query_value:
        raise RuntimeError("search.query is required for collect-urls command.")
    parse_and_validate_limit(search_params, required=True)

    username, _ = resolve_credentials(json_input)
    if not username:
        raise RuntimeError("UPWORK_USERNAME is required to locate cookies. Set it in .env or pass credentials.username.")
    cookies_file_path = build_cookies_file_path(username)
    if not cookies_file_path or not os.path.exists(cookies_file_path):
        raise RuntimeError("Cookies not found. Run login command first.")

    normalized_search_params, limit = normalize_search_params(search_params, True, 0)
    search_url = build_upwork_search_url(normalized_search_params)
    proxy_details = json_input.get("proxy_details", None)
    session = await build_authenticated_requests_session(search_url, cookies_file_path, proxy_details)
    urls = get_job_urls_requests(session, [query_value], [search_url], limit=limit).get(query_value, [])
    saved_count = save_job_urls_to_db(urls, query_value, "job_urls")
    logger.info(f"✅ URLs saved to job_urls: {saved_count}")
    return saved_count


async def cli_collect_bestmatch_urls(json_input: dict) -> int:
    """Collect best match URLs by limit and store into job_urls_bestmatch table."""
    search_params = json_input.get("search", {}) or {}
    if not isinstance(search_params, dict):
        raise RuntimeError("search must be a JSON object.")
    parse_and_validate_limit(search_params, required=True)

    username, _ = resolve_credentials(json_input)
    if not username:
        raise RuntimeError("UPWORK_USERNAME is required to locate cookies. Set it in .env or pass credentials.username.")
    cookies_file_path = build_cookies_file_path(username)
    if not cookies_file_path or not os.path.exists(cookies_file_path):
        raise RuntimeError("Cookies not found. Run login command first.")

    bestmatch_search = dict(search_params)
    bestmatch_search["sort"] = "relevance"
    for key in ("query", "search_any", "search_exact", "search_none", "search_title"):
        bestmatch_search.pop(key, None)

    normalized_search_params, limit = normalize_search_params(bestmatch_search, True, 0)
    search_url = build_upwork_search_url(normalized_search_params)
    proxy_details = json_input.get("proxy_details", None)
    session = await build_authenticated_requests_session(search_url, cookies_file_path, proxy_details)
    urls = get_job_urls_requests(session, ["bestmatch"], [search_url], limit=limit).get("bestmatch", [])
    saved_count = save_job_urls_to_db(urls, "bestmatch", "job_urls_bestmatch")
    logger.info(f"✅ URLs saved to job_urls_bestmatch: {saved_count}")
    return saved_count


async def cli_login(json_input: dict) -> str:
    """
    Login-only command: authenticate on Upwork and save cookies.
    """
    username, password = resolve_credentials(json_input)
    if (username and not password) or (password and not username):
        raise RuntimeError("Both credentials are required for login: set UPWORK_USERNAME and UPWORK_PASSWORD in .env.")
    if not username or not password:
        raise RuntimeError("UPWORK credentials are required for login. Set UPWORK_USERNAME and UPWORK_PASSWORD in .env")

    cookies_file_path = build_cookies_file_path(username)
    proxy_details = json_input.get("proxy_details", None)
    search_url = "https://www.upwork.com/nx/find-work/"
    login_url = "https://www.upwork.com/ab/account-security/login"

    async with AsyncCamoufox(headless=True, geoip=True, humanize=True, i_know_what_im_doing=True, config={'forceScopeAccess': True}, disable_coop=True, proxy=proxy_details) as browser:
        context = await browser.new_context()
        page = await context.new_page()
        page, context = await login_and_solve(
            page, context, username, password, search_url, login_url, True, cookies_file_path
        )

        cookies_valid = await verify_cookies_validity(page, context)
        if not cookies_valid:
            raise RuntimeError("Login failed: could not establish a valid authenticated session")

        await save_cookies_to_file(context, cookies_file_path)
        return cookies_file_path


async def cli_search_with_cookies(json_input: dict, *, require_query: bool = True) -> list[dict]:
    """
    Search-only command: use existing cookies; fail if missing or expired.
    """
    logger.info("🏁 Starting cookie-based search...")
    start_time = time.time()

    search_params = json_input.get("search", {}) or {}
    if not isinstance(search_params, dict):
        raise RuntimeError("search must be a JSON object.")

    if require_query:
        query_value = (search_params.get("query") or "").strip()
        if not query_value:
            raise RuntimeError("search.query is required for search command.")
    parse_and_validate_limit(search_params, required=True)

    username, _ = resolve_credentials(json_input)
    if not username:
        raise RuntimeError("UPWORK_USERNAME is required to locate cookies. Set it in .env or pass credentials.username.")
    cookies_file_path = build_cookies_file_path(username)
    if not cookies_file_path or not os.path.exists(cookies_file_path):
        raise RuntimeError("Cookies not found. Run login command first.")

    general_params = json_input.get("general", {})
    save_csv = general_params.get("save_csv", False)
    proxy_details = json_input.get("proxy_details", None)

    buffer = 20
    normalized_search_params, limit = normalize_search_params(search_params, True, buffer)
    search_url = build_upwork_search_url(normalized_search_params)
    search_queries = [search_params.get("query", search_params.get("search_any", "search"))]
    search_urls = [search_url]

    session = await build_authenticated_requests_session(search_url, cookies_file_path, proxy_details)

    logger.info("💼 Getting Related Jobs...")
    job_urls_dict = get_job_urls_requests(session, search_queries, search_urls, limit=limit)
    job_urls = list(job_urls_dict.values())[0]
    logger.debug(f"Got {len(job_urls)} job URLs.")

    logger.info("🏢 Getting Job Attributes with requests...")
    job_attributes = browser_worker_requests(session, job_urls, True, max_workers=25)
    job_attributes = job_attributes[:limit - buffer]

    if save_csv:
        df = pd.DataFrame(job_attributes)
        df = df.sort_index(axis=1)
        df.to_csv(f'data/jobs/csv/job_results_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.csv', index=False)

    elapsed = time.time() - start_time
    logger.info(f"🏁 Cookie-based search complete. Results: {len(job_attributes)}; time: {elapsed:.2f}s")
    return job_attributes


async def main(jsonInput: dict) -> list[dict]:
    """
    Main entry point for the Upwork Job Scraper. Orchestrates browser setup, login, job search, and extraction.

    :param jsonInput: Input dictionary containing credentials, search, and general parameters
    :type jsonInput: dict
    :return: List of job attribute dictionaries
    :rtype: list[dict]
    """
    logger.info("🏁 Starting Upwork Job Scraper...")
    # log the current time
    start_time = time.time()

    # Extract credentials
    if "credentials" in jsonInput:
        credentials_json = jsonInput["credentials"]
    else:
        credentials_json = jsonInput
    # set username and password
    # Fallback to .env values so CLI can run without passing secrets in terminal
    username = credentials_json.get('username') or os.getenv('UPWORK_USERNAME')
    password = credentials_json.get('password') or os.getenv('UPWORK_PASSWORD')
    if (username and not password) or (password and not username):
        logger.warning("Both username and password must be provided for authentication. One is missing.")
    credentials_provided = username and password
    # Extract search params
    search_params = jsonInput.get('search', {})
    
    # If still not present, fallback to defaults
    if not search_params:
        search_params = {}
    # Extract general params
    general_params = jsonInput.get('general', {})
    save_csv = general_params.get('save_csv', False)

    # Normalize search params and get limit
    buffer = 20
    normalized_search_params, limit = normalize_search_params(search_params, credentials_provided, buffer)

    # Build search URL using the function
    logger.info("🏗️  Building search URL...")
    search_url = build_upwork_search_url(normalized_search_params)
    logger.debug(f"Search URL: {search_url}")

    # Visit Upwork login page
    login_url = "https://www.upwork.com/ab/account-security/login"

    NUM_DETAIL_WORKERS = 25

    search_queries = [search_params.get('query', search_params.get('search_any', 'search'))]
    search_urls = [search_url]
    
    # proxy
    proxy_details = jsonInput.get('proxy_details', None)
    
    logger.debug(f"proxy_details: {proxy_details}")
    
    # Prepare cookies file path based on username
    cookies_file_path = None
    if credentials_provided and username:
        # Create safe filename from username
        safe_username = re.sub(r'[^\w\-_.]', '_', username)
        cookies_dir = os.path.join('cookies')
        os.makedirs(cookies_dir, exist_ok=True)
        cookies_file_path = os.path.join(cookies_dir, f'{safe_username}_cookies.json')
        logger.debug(f"Cookies file path: {cookies_file_path}")
    
    # Only one browser for login/captcha
    async with AsyncCamoufox(headless=True, geoip=True, humanize=True, i_know_what_im_doing=True, config={'forceScopeAccess': True}, disable_coop=True, proxy=proxy_details) as browser:
        logger.info("🌐 Creating browser/context/page for login...")
        try:
            context = await browser.new_context()
            page = await context.new_page()
        except Exception as e:
            logger.error(f"⚠️ Error creating browser: {e}")
            raise RuntimeError(f"Error creating browser: {e}") from e
        try:
            if credentials_provided:
                logger.info("🔒 Solving Captcha and Logging in...")
            else:
                logger.info("🔒 Solving Captcha (no login - credentials not provided)...")
            page, context = await login_and_solve(page, context, username, password, search_url, login_url, credentials_provided, cookies_file_path)
        except Exception as e:
            logger.error(f"⚠️ Error logging in: {e}")
            raise RuntimeError(f"Error logging in: {e}") from e
        # Extract cookies and user-agent, build requests session
        session = await get_requests_session_from_playwright(context, page, proxy_details=proxy_details)
    # Use requests for all scraping
    try:
        logger.info("💼 Getting Related Jobs...")
        job_urls_dict = get_job_urls_requests(session, search_queries, search_urls, limit=limit)
        job_urls = list(job_urls_dict.values())[0]
        logger.debug(f"Got {len(job_urls)} job URLs.")
    except Exception as e:
        logger.error(f"⚠️ Error getting jobs: {e}")
        raise RuntimeError(f"Error getting jobs: {e}") from e
    # Process jobs with requests
    try:
        logger.info("🏢 Getting Job Attributes with requests...")
        job_attributes = browser_worker_requests(session, job_urls, credentials_provided, max_workers=NUM_DETAIL_WORKERS)
    except Exception as e:
        logger.error(f"⚠️ Error getting job attributes: {e}")
        raise RuntimeError(f"Error getting job attributes: {e}") from e
    # Filter out jobs where Nuxt data was missing (i.e., job is None)
    # job_attributes = [job for job in job_attributes if job is not None and all(v is not None for v in job.values())]
    logger.debug(f"job_attributes after filter: {len(job_attributes)}")
    # Trim to the original limit
    logger.debug(f"limit: {limit-buffer}")
    job_attributes = job_attributes[:limit-buffer]
    # Push to Apify dataset if running on Apify
    if os.environ.get("ACTOR_INPUT_KEY"):
        from apify import Actor
        for item in job_attributes:
            await Actor.push_data(item)
    if save_csv:
        df = pd.DataFrame(job_attributes)
        df = df.sort_index(axis=1)
        df.to_csv(f'data/jobs/csv/job_results_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.csv', index=False)
    end_time = time.time()
    elapsed = end_time - start_time
    logger.info("🏁 Job Fetch Complete!")
    logger.info(f"🎯 Number of results: {len(job_attributes)}")
    # Log number of unique columns across all job records
    num_columns = len(set().union(*(job.keys() for job in job_attributes))) if job_attributes else 0
    logger.info(f"🧩 Number of columns: {num_columns}")
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)
    logger.info(f"🕒 Total run time: {minutes}m {seconds}s ({elapsed:.2f} seconds)")
    return job_attributes


if __name__ == "__main__":
    # set argparse
    parser = argparse.ArgumentParser(description="Upwork Job Scraper")
    parser.add_argument('--command', type=str, choices=['login', 'search', 'best-match', 'collect-urls', 'collect-bestmatch-urls', 'parse-job-urls', 'parse-bestmatch-urls', 'pull-jobs', 'pull-bestmatch-jobs'], default='search', help='CLI command: login, search, best-match, collect-urls, collect-bestmatch-urls, parse-job-urls, parse-bestmatch-urls, pull-jobs, pull-bestmatch-jobs')
    parser.add_argument('--jsonInput', type=str, help='JSON string or path to JSON file with credentials and other info')
    args = parser.parse_args()

    # set logger
    logger_obj = Logger(level="DEBUG")
    logger = logger_obj.get_logger()

    # Load credentials/input data from environment variable or argument
    if os.environ.get("jsonInput"):
        json_input_str = os.environ.get("jsonInput")
        try:
            input_data = json.loads(json_input_str)
        except json.JSONDecodeError:
            try:
                # It might be a dict string, so we can use ast.literal_eval
                input_data = ast.literal_eval(json_input_str)
            except (ValueError, SyntaxError) as e:
                logger.error(f"⚠️ Failed to parse jsonInput from environment variable: {e}")
                sys.exit(1)
    # load from argument
    elif args.jsonInput:
        try:
            input_data = json.loads(args.jsonInput)
        except json.JSONDecodeError as e:
            if os.path.exists(args.jsonInput):
                try:
                    with open(args.jsonInput, "r", encoding="utf-8") as f:
                        input_data = json.load(f)
                except Exception as file_error:
                    logger.error(f"⚠️ Failed to parse JSON file `{args.jsonInput}`: {file_error}")
                    sys.exit(1)
            else:
                logger.error(f"⚠️ Failed to parse input JSON string: {e}")
                sys.exit(1)
    # load from apify
    elif os.environ.get("ACTOR_INPUT_KEY"):
        from apify import Actor

        async def run_actor():
            # Initialize the Actor (fetches env, sets up storage, etc.)
            await Actor.init()
            # Pull input.json from the default KVS and parse it
            run_data = await Actor.get_input()
            # convert to expected json
            search_data = run_data.copy()
            input_data = {
                'credentials': {
                    'username': search_data.pop('username', None),
                    'password': search_data.pop('password', None)
                },
                'search': search_data,
                'general': {}
            }
            
            proxy_configuration = await Actor.create_proxy_configuration(
                groups=['RESIDENTIAL'],
                country_code='US',
                )

            if not proxy_configuration:
                raise RuntimeError('No proxy configuration available.')

            proxy_url = await proxy_configuration.new_url(session_id='a')
            Actor.log.info(f'Proxy URL: {proxy_url}')
            # Parse Apify proxy URL into server/username/password for Playwright/Camoufox
            from urllib.parse import urlparse
            _p = urlparse(proxy_url)
            _server = f"{_p.scheme}://{_p.hostname}:{_p.port}"
            proxy_details = {'server': _server}
            if _p.username and _p.password:
                proxy_details['username'] = _p.username
                proxy_details['password'] = _p.password
            input_data['proxy_details'] = proxy_details
            
            # set logger
            log_level = search_data.pop('log_level', None)
            if log_level:
                logger_obj = Logger(level=log_level)
                logger = logger_obj.get_logger()
            # Run your existing scraper logic
            logger.debug(f"input_data: {input_data}")
            result = await main(input_data)
            # exit
            await Actor.exit()
        # start
        asyncio.run(run_actor())
        sys.exit(0)
    # load from config.toml or .env
    else:
        from utils.settings import config
        
        # Try to get credentials from .env first, fallback to config.toml
        username = os.getenv('UPWORK_USERNAME') or (config.get('Credentials', {}).get('username') if isinstance(config, dict) else None)
        password = os.getenv('UPWORK_PASSWORD') or (config.get('Credentials', {}).get('password') if isinstance(config, dict) else None)
        
        input_data = {
            'credentials': {
                'username': username,
                'password': password
            },
            'search': config.get('Search', {}) if isinstance(config, dict) else {},
            'general': config.get('General', {}) if isinstance(config, dict) else {}
        }

    logger.debug(f"input_data: {input_data}")
    try:
        if args.command == 'login':
            cookies_path = asyncio.run(cli_login(input_data))
            logger.info(f"✅ Login successful. Cookies saved to: {cookies_path}")
        elif args.command == 'search':
            asyncio.run(cli_search_with_cookies(input_data, require_query=True))
        elif args.command == 'best-match':
            search_payload = dict(input_data)
            search_payload["search"] = dict(input_data.get("search", {}))
            # Best Match mode should not send query terms.
            for key in ("query", "search_any", "search_exact", "search_none", "search_title"):
                search_payload["search"].pop(key, None)
            search_payload["search"]["sort"] = "relevance"
            asyncio.run(cli_search_with_cookies(search_payload, require_query=False))
        elif args.command == 'collect-urls':
            asyncio.run(cli_collect_urls(input_data))
        elif args.command == 'collect-bestmatch-urls':
            asyncio.run(cli_collect_bestmatch_urls(input_data))
        elif args.command == 'parse-job-urls':
            asyncio.run(cli_parse_urls_to_jobs(input_data, "job_urls"))
        elif args.command == 'parse-bestmatch-urls':
            asyncio.run(cli_parse_urls_to_jobs(input_data, "job_urls_bestmatch"))
        elif args.command == 'pull-jobs':
            cli_pull_unchecked_jobs(input_data, "jobs")
        elif args.command == 'pull-bestmatch-jobs':
            cli_pull_unchecked_jobs(input_data, "job_bestmach")
        else:
            raise RuntimeError(f"Unsupported command: {args.command}")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Command failed: {e}")
        sys.exit(1)