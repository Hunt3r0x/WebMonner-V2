import requests
import json
from typing import List, Dict, Any

from utils import log

class ScanResult:
    """A data class to hold scan results for a single domain."""
    def __init__(self, domain: str):
        self.domain = domain
        self.changes: List[Dict[str, Any]] = []
        self.endpoints: List[str] = []
        self.endpoints_file: str | None = None  # Path to the new endpoints file
        self.errors: List[str] = []
        self.counts = {"processed": 0, "filtered": 0}

    def add_change(self, status: str, url: str, file_info: Dict[str, Any]):
        self.changes.append({"status": status, "url": url, **file_info})

    def add_endpoints(self, endpoints: List[str], file_path: str | None = None):
        self.endpoints.extend(endpoints)
        if file_path:
            self.endpoints_file = file_path

class Notifier:
    """Handles formatting and sending notifications to Discord."""

    def __init__(self, webhook_url: str | None):
        self.webhook_url = webhook_url

    def _send(self, payload: Dict[str, Any]):
        """Sends a JSON payload to the Discord webhook."""
        if not self.webhook_url:
            return
        try:
            response = requests.post(
                self.webhook_url,
                data=json.dumps(payload),
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            response.raise_for_status()
        except requests.RequestException as e:
            log.error(f"Failed to send Discord notification: {e}")

    def send_batched_summary(self, results: List[ScanResult], duration: float):
        """Creates and sends a comprehensive scan summary."""
        total_changes = sum(len(res.changes) for res in results)
        total_endpoints = sum(len(res.endpoints) for res in results)
        total_domains = len(results)

        embed = {
            "title": f"📊 WebMonner Scan Summary",
            "description": f"Detected **{total_changes}** changes and **{total_endpoints}** new endpoints across **{total_domains}** domain(s).",
            "color": 0x3498db,  # Blue
            "fields": [],
            "footer": {
                "text": f"Scan completed in {duration:.2f} seconds at {log.get_timestamp()}"
            }
        }
        
        # Add a field for each domain with changes
        for res in results:
            if not res.changes and not res.endpoints:
                continue

            field_value = ""
            if res.changes:
                field_value += f"**📄 Changes ({len(res.changes)}):**\n"
                for change in res.changes[:5]: # Limit to 5 changes per domain to avoid clutter
                    status_emoji = "✨" if change['status'] == 'NEW' else "📝"
                    line_changes = ""
                    if change['status'] == 'MODIFIED':
                        line_changes = f" (+{change.get('added', 0)} / -{change.get('removed', 0)})"
                    
                    # Make URL less verbose
                    url_path = change['url'].split(res.domain)[-1]
                    field_value += f"{status_emoji} `{change['status'].upper()}`: `{url_path}{line_changes}`\n"
                if len(res.changes) > 5:
                    field_value += f"*...and {len(res.changes) - 5} more.*\n"

            if res.endpoints:
                 field_value += f"\n**🎯 New Endpoints ({len(res.endpoints)}):**\n"
                 for endpoint in res.endpoints[:5]: # Limit to 5 endpoints
                     field_value += f"`{endpoint}`\n"
                 if len(res.endpoints) > 5:
                    field_value += f"*...and {len(res.endpoints) - 5} more.*\n"
                 
                 # Add file path information
                 if res.endpoints_file:
                     import os
                     filename = os.path.basename(res.endpoints_file)
                     field_value += f"\n💾 Saved to: `{filename}`\n"

            embed["fields"].append({
                "name": f"🌐 {res.domain}",
                "value": field_value,
                "inline": False
            })

        self._send({"embeds": [embed]})


def test_discord_notification(webhook_url: str):
    """Sends a simple test message to the provided webhook."""
    payload = {
        "embeds": [{
            "title": "✅ WebMonner Test Successful",
            "description": "If you can see this, your Discord webhook is configured correctly.",
            "color": 0x2ecc71, # Green
            "footer": {"text": f"Test sent at {log.get_timestamp()}"}
        }]
    }
    try:
        response = requests.post(
            webhook_url,
            data=json.dumps(payload),
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        response.raise_for_status()
        log.success("Test notification sent successfully!")
    except requests.RequestException as e:
        log.error(f"Failed to send test notification: {e}")

