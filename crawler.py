import time
import re
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, Error as PlaywrightError
from typing import Set, Dict, List, Any, NamedTuple
import requests
import hashlib

from utils import log, format_filesize
from file_manager import FileManager
from endpoint_extractor import EndpointExtractor
from similarity_analyzer import SimilarityAnalyzer
from notifier import Notifier, ScanResult

class CrawlerConfig(NamedTuple):
    """Configuration object for the crawler."""
    urls: List[str]
    extract_endpoints: bool
    analyze_similarity: bool
    filters: Dict[str, List[str]]
    endpoint_patterns: Dict[str, List[str]] | None
    force_reextract: bool
    live_mode: bool
    interval: int
    headless: bool
    verbose: bool
    discord_webhook: str | None


def should_process_js_file(url: str, filters: Dict[str, List[str]]) -> bool:
    """Applies include/exclude filters to a given JS file URL."""
    try:
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
    except Exception:
        return False # Invalid URL

    # Domain filters
    if filters.get('include_domain') and not any(d in domain for d in filters['include_domain']):
        return False
    if filters.get('exclude_domain') and any(d in domain for d in filters['exclude_domain']):
        return False

    # URL regex filters
    if filters.get('include_url') and not any(re.search(p, url) for p in filters['include_url']):
        return False
    if filters.get('exclude_url') and any(re.search(p, url) for p in filters['exclude_url']):
        return False
        
    return True

def run_crawler(config: CrawlerConfig):
    """Main crawler loop."""
    log.header("Starting WebMonner Scan")
    log.info(f"Targets: {len(config.urls)} URLs")
    log.info(f"Endpoint Extraction: {'Enabled' if config.extract_endpoints else 'Disabled'}")
    log.info(f"Similarity Analysis: {'Enabled' if config.analyze_similarity else 'Disabled'}")
    
    file_manager = FileManager()
    endpoint_extractor = EndpointExtractor(config.endpoint_patterns) if config.extract_endpoints else None
    similarity_analyzer = SimilarityAnalyzer(file_manager) if config.analyze_similarity else None
    notifier = Notifier(config.discord_webhook) if config.discord_webhook else None

    while True:
        start_time = time.time()
        log.separator()
        log.info(f"Scan started at {time.strftime('%Y-%m-%d %H:%M:%S')}")

        all_scan_results: Dict[str, ScanResult] = {}

        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=config.headless)
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 WebMonner/1.0",
                    ignore_https_errors=True
                )
                page = context.new_page()

                for target_url in config.urls:
                    log.info(f"Crawling target: {target_url}")
                    discovered_js_files: Set[str] = set()

                    # --- JS File Discovery ---
                    def handle_request(request):
                        if request.resource_type == 'script':
                            if request.url.startswith(('http://', 'https://')):
                                discovered_js_files.add(request.url)

                    page.on('request', handle_request)
                    
                    try:
                        # Try with a longer timeout and more lenient wait condition
                        if config.verbose:
                            log.info(f"Loading page (timeout: 60s)...")
                        
                        # First try: wait for load event (faster than networkidle)
                        try:
                            page.goto(target_url, wait_until='load', timeout=60000)
                            # Give it a bit more time for async scripts
                            page.wait_for_timeout(2000)
                        except PlaywrightError:
                            # Fallback: try with domcontentloaded (even faster)
                            if config.verbose:
                                log.info("Retrying with faster load strategy...")
                            page.goto(target_url, wait_until='domcontentloaded', timeout=60000)
                            page.wait_for_timeout(3000)
                        
                        # Also find script tags as a fallback
                        script_tags = page.eval_on_selector_all('script[src]', 'elements => elements.map(e => e.src)')
                        for src in script_tags:
                             if src.startswith(('http://', 'https://')):
                                discovered_js_files.add(src)

                    except PlaywrightError as e:
                        log.warning(f"Could not navigate to {target_url}: {str(e).splitlines()[0]}")
                        log.info("Tip: The site might be slow or blocking automation. Check if it loads in a regular browser.")
                        continue
                    finally:
                        page.remove_listener('request', handle_request)
                    
                    log.success(f"Discovered {len(discovered_js_files)} potential JS files.")

                    # Track extracted endpoints per domain (before comparison)
                    domain_endpoints = {}  # domain -> set of all extracted endpoints
                    
                    # --- Process each discovered file ---
                    for js_url in discovered_js_files:
                        domain = urlparse(js_url).netloc
                        if domain not in all_scan_results:
                            all_scan_results[domain] = ScanResult(domain)
                        if domain not in domain_endpoints:
                            domain_endpoints[domain] = set()

                        current_result = all_scan_results[domain]

                        if not should_process_js_file(js_url, config.filters):
                            if config.verbose:
                                log.muted(f"Filtered out: {js_url}")
                            current_result.counts['filtered'] += 1
                            continue
                        
                        current_result.counts['processed'] += 1
                        
                        try:
                            # --- Download & Hashing ---
                            # Try to download using Playwright first (bypasses bot protection)
                            try:
                                response_playwright = page.request.get(js_url, timeout=15000)
                                if response_playwright.ok:
                                    content = response_playwright.body()
                                else:
                                    raise Exception(f"Playwright request failed with status {response_playwright.status}")
                            except Exception as e:
                                # Fallback to requests library
                                if config.verbose:
                                    log.muted(f"Playwright download failed, trying requests: {str(e).splitlines()[0]}")
                                response = requests.get(js_url, timeout=15)
                                response.raise_for_status()
                                content = response.content
                            
                            content_hash = hashlib.sha256(content).hexdigest()

                            # --- File Management & Diffing ---
                            status, file_info = file_manager.process_js_file(js_url, content, content_hash)
                            
                            # Decide whether to process this file
                            should_extract = False
                            if status == "UNCHANGED":
                                if config.force_reextract:
                                    # Force re-extraction even on unchanged files
                                    should_extract = True
                                    if config.verbose:
                                        log.muted(f"Unchanged (force re-extract): {js_url}")
                                else:
                                    if config.verbose:
                                        log.muted(f"Unchanged: {js_url}")
                            else:
                                # File changed
                                should_extract = True
                                log.success(f"{status.capitalize()}: {js_url} ({format_filesize(file_info.get('size', 0))})")
                                current_result.add_change(status, js_url, file_info)

                            # --- Endpoint Extraction ---
                            # Extract endpoints from this file (but don't compare/save yet)
                            if endpoint_extractor and should_extract:
                                file_endpoints = endpoint_extractor.extract(file_info['beautified_path'], domain, config.filters)
                                domain_endpoints[domain].update(file_endpoints)

                            # --- Similarity Analysis ---
                            if similarity_analyzer and status == "NEW":
                                renames = similarity_analyzer.find_potential_renames(js_url, domain)
                                if renames:
                                    log.info(f"  > Found {len(renames)} similar files (potential renames).")
                                    # TODO: Add rename info to results for notification
                        
                        except requests.RequestException as e:
                            log.warning(f"Failed to download {js_url}: {e}")
                            current_result.errors.append(f"Download failed for {js_url}")
                        except Exception as e:
                            log.error(f"Error processing {js_url}: {e}", exc_info=config.verbose)
                            current_result.errors.append(f"Processing error for {js_url}")
                    
                    # --- Compare and save endpoints per domain (once per domain) ---
                    if endpoint_extractor:
                        for domain, endpoints_set in domain_endpoints.items():
                            if endpoints_set:
                                new_endpoints = endpoint_extractor.save_and_compare(domain, endpoints_set)
                                if new_endpoints:
                                    log.info(f"Found {len(new_endpoints)} NEW unique endpoints for {domain}")
                                    all_scan_results[domain].add_endpoints(new_endpoints)

                browser.close()

            except PlaywrightError as e:
                log.error(f"A browser error occurred: {e}")
            except Exception as e:
                log.error(f"A critical error occurred during the scan: {e}", exc_info=config.verbose)


        # --- Post-Processing and Notifications ---
        end_time = time.time()
        duration = end_time - start_time
        log.separator()
        log.header(f"Scan Finished in {duration:.2f} seconds.")

        total_changes = sum(len(res.changes) for res in all_scan_results.values())
        total_endpoints = sum(len(res.endpoints) for res in all_scan_results.values())
        
        log.info(f"Total changes detected: {total_changes}")
        log.info(f"Total new endpoints found: {total_endpoints}")
        
        if notifier and (total_changes > 0 or total_endpoints > 0):
            log.info("Sending batched summary to Discord...")
            notifier.send_batched_summary(list(all_scan_results.values()), duration)

        if not config.live_mode:
            break
        else:
            log.info(f"Live mode enabled. Waiting for {config.interval} seconds until next scan...")
            time.sleep(config.interval)

