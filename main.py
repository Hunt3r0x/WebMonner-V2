import argparse
import sys
import json
import re
import ipaddress
from pathlib import Path
from urllib.parse import urlparse, urlunparse
from crawler import run_crawler, CrawlerConfig
from notifier import test_discord_notification
from utils import log

def normalize_url(url: str) -> str:
    """
    Clean and smart URL normalizer.
    - Fixes protocol typos (http//, htps://, etc.)
    - Adds https:// if missing
    - Uses http:// for IPs or localhost
    - Removes fragments (#) and trailing slashes
    """
    if not url:
        return ""

    url = url.strip().replace(' ', '')
    if not url:
        return ""

    # Fix common protocol typos
    url = re.sub(r'^(ht+tps?|ttps?):/*', lambda m: 'https://' if 's' in m.group(0) else 'http://', url, flags=re.I)

    parsed = urlparse(url)

    # If no scheme → detect appropriate one
    if not parsed.scheme:
        host = url.split('/')[0]
        try:
            ipaddress.ip_address(host.split(':')[0])
            scheme = "http"
        except ValueError:
            scheme = "http" if host.startswith("localhost") or host.endswith(".local") else "https"
        url = f"{scheme}://{url}"
        parsed = urlparse(url)

    # Remove fragment + trailing slash
    clean = parsed._replace(fragment="")
    final = urlunparse(clean).rstrip("/")

    return final

def load_config_from_file(config_path: str) -> dict:
    """Loads configuration from a JSON file."""
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        log.error(f"Configuration file not found at: {config_path}")
        sys.exit(1)
    except json.JSONDecodeError:
        log.error(f"Invalid JSON in configuration file: {config_path}")
        sys.exit(1)

def main():
    """
    Parses command-line arguments and orchestrates the WebMonner tool.
    This is the main entry point of the application.
    """
    parser = argparse.ArgumentParser(
        description="WebMonner - A Python tool for monitoring changes in JavaScript files and extracting API endpoints.",
        formatter_class=argparse.RawTextHelpFormatter
    )

    # --- Core Options ---
    group_target = parser.add_argument_group('Target Specification')
    group_target.add_argument('-u', '--url', help='A single URL to scan. Overrides config file.')
    group_target.add_argument('-f', '--urls-file', help='Path to a file with URLs. Overrides config file.')
    group_target.add_argument('-c', '--config', help='Path to a config.json file.')

    # --- Feature Modules ---
    group_features = parser.add_argument_group('Feature Modules')
    group_features.add_argument('--extract-endpoints', action=argparse.BooleanOptionalAction, help='Enable API endpoint extraction.')
    group_features.add_argument('--analyze-similarity', action=argparse.BooleanOptionalAction, help='Enable similarity analysis.')
    group_features.add_argument('--endpoint-regex', action='append', help='Add custom regex pattern for endpoint extraction. Can be used multiple times.')
    group_features.add_argument('--force-reextract', action=argparse.BooleanOptionalAction, help='Always extract endpoints on every run, even from unchanged files.')
    group_features.add_argument('--display-endpoints', action=argparse.BooleanOptionalAction, help='Display new endpoints on screen (console output).')

    # --- Filtering ---
    group_filter = parser.add_argument_group('Filtering Options')
    group_filter.add_argument('--include-domain', action='append', help='Domain to include. Appends to config file list.')
    group_filter.add_argument('--exclude-domain', action='append', help='Domain to exclude. Appends to config file list.')
    group_filter.add_argument('--include-url', action='append', help='URL pattern (regex) to include. Appends to config file list.')
    group_filter.add_argument('--exclude-url', action='append', help='URL pattern (regex) to exclude. Appends to config file list.')

    # --- Behavior ---
    group_behavior = parser.add_argument_group('Behavior Configuration')
    group_behavior.add_argument('--live', action=argparse.BooleanOptionalAction, help='Enable live mode.')
    group_behavior.add_argument('--interval', type=int, help='Interval in seconds for live mode.')
    group_behavior.add_argument('--headless', action=argparse.BooleanOptionalAction, default=True, help='Run browser in headless mode.')
    group_behavior.add_argument('-v', '--verbose', action=argparse.BooleanOptionalAction, help='Enable verbose logging.')

    # --- Notifications ---
    group_notify = parser.add_argument_group('Notification Options')
    group_notify.add_argument('--discord-webhook', help='Discord webhook URL.')
    group_notify.add_argument('--no-notifications', action='store_true', help='Disable all Discord notifications.')

    # --- Special Commands ---
    group_special = parser.add_argument_group('Special Commands (run exclusively)')
    group_special.add_argument('--test-discord', action='store_true', help='Send a test message to the Discord webhook and exit.')
    
    args = parser.parse_args()

    # --- Load Config from File ---
    file_config = {}
    if args.config:
        file_config = load_config_from_file(args.config)
    
    # CLI arguments override file configuration
    discord_webhook = args.discord_webhook or file_config.get('discord_webhook')

    # --- Handle Special Commands ---
    if args.test_discord:
        if not discord_webhook:
            log.error("The --discord-webhook argument (or config file entry) is required to test notifications.")
            sys.exit(1)
        log.info("Sending test notification to Discord...")
        test_discord_notification(discord_webhook)
        sys.exit(0)

    # --- Consolidate URLs ---
    urls = []
    if args.url:
        urls.append(normalize_url(args.url))
    elif args.urls_file:
        try:
            with open(args.urls_file, 'r') as f:
                urls.extend([normalize_url(line.strip()) for line in f if line.strip()])
        except FileNotFoundError:
            log.error(f"The file specified by --urls-file was not found: {args.urls_file}")
            sys.exit(1)
    elif file_config.get('urls'):
        urls.extend([normalize_url(url) for url in file_config['urls']])

    if not urls:
        log.error("You must provide a target via --url, --urls-file, or a 'urls' key in your config file.")
        parser.print_help()
        sys.exit(1)

    # --- Build Final Configuration ---
    # Helper to decide value: CLI > File > Default
    def get_config_value(arg_val, file_key, default_val):
        if arg_val is not None:
            return arg_val
        return file_config.get(file_key, default_val)

    # --- Build Endpoint Patterns ---
    endpoint_patterns = file_config.get('endpoint_patterns', {})
    
    # Add CLI custom patterns to the 'custom_patterns' category
    if args.endpoint_regex:
        if 'custom_patterns' not in endpoint_patterns:
            endpoint_patterns['custom_patterns'] = []
        endpoint_patterns['custom_patterns'].extend(args.endpoint_regex)
    
    # Only pass patterns if endpoint extraction is enabled and patterns exist
    final_patterns = endpoint_patterns if endpoint_patterns else None

    config = CrawlerConfig(
        urls=list(dict.fromkeys(urls)),  # Remove duplicates
        extract_endpoints=get_config_value(args.extract_endpoints, 'extract_endpoints', False),
        analyze_similarity=get_config_value(args.analyze_similarity, 'analyze_similarity', False),
        filters={
            "include_domain": (file_config.get('filters', {}).get('include_domain', [])) + (args.include_domain or []),
            "exclude_domain": (file_config.get('filters', {}).get('exclude_domain', [])) + (args.exclude_domain or []),
            "include_url": (file_config.get('filters', {}).get('include_url', [])) + (args.include_url or []),
            "exclude_url": (file_config.get('filters', {}).get('exclude_url', [])) + (args.exclude_url or []),
        },
        endpoint_patterns=final_patterns,
        force_reextract=get_config_value(args.force_reextract, 'force_reextract', False),
        live_mode=get_config_value(args.live, 'live_mode', False),
        interval=get_config_value(args.interval, 'interval', 300),
        headless=get_config_value(args.headless, 'headless', True),
        verbose=get_config_value(args.verbose, 'verbose', False),
        discord_webhook=None if args.no_notifications else discord_webhook,
        display_endpoints=get_config_value(args.display_endpoints, 'display_endpoints', True),
    )
    
    # --- Final Validation ---
    if config.live_mode and not config.discord_webhook:
        log.warning("Live mode is enabled, but no Discord webhook is configured. You will not receive notifications.")

    # --- Run Main Process ---
    try:
        run_crawler(config)
    except Exception as e:
        log.error(f"An unhandled error occurred: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()

