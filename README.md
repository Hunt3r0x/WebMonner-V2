# WebMonner v2

A powerful Python tool for monitoring changes in JavaScript files on websites and extracting API endpoints.

## Features

- 🔍 **JS File Discovery**: Automatically discovers and downloads JavaScript files from target websites
- 📊 **Change Detection**: Tracks file modifications with detailed diffs
- 🎯 **Endpoint Extraction**: Extracts API endpoints and routes from JavaScript code
- 🔄 **Similarity Analysis**: Detects renamed or moved files using structural fingerprinting
- 🔔 **Discord Notifications**: Real-time notifications with detailed change summaries
- ⏰ **Live Mode**: Continuous monitoring with configurable intervals
- 🎨 **Code Beautification**: Beautifies minified JavaScript for better diff readability

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/webmonner-v2.git
cd webmonner-v2
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Install Playwright browsers

```bash
playwright install chromium
```

## Quick Start

### Basic scan of a single URL

```bash
python main.py --url https://example.com
```

### Enable endpoint extraction

**Note:** To use endpoint extraction, you must first configure patterns in `config.json` or use `--endpoint-regex` flags.

```bash
# Using config file (recommended)
cp config.json.example config.json
python main.py --config config.json --extract-endpoints

# Or using CLI patterns
python main.py \
  --url https://example.com \
  --extract-endpoints \
  --endpoint-regex "fetch\s*\(['\"]([^'\"]+)" \
  --endpoint-regex "\.(get|post)\(['\"]([^'\"]+)"
```

### Live monitoring with Discord notifications

```bash
python main.py --url https://example.com --live --interval 600 --discord-webhook "YOUR_WEBHOOK_URL"
```

### Using a configuration file

```bash
# Copy the example config
cp config.json.example config.json

# Edit config.json with your settings
# Then run:
python main.py --config config.json
```

## Usage

### Command-Line Options

#### Target Specification
```
-u, --url URL              A single URL to scan
-f, --urls-file FILE       Path to a file containing URLs (one per line)
-c, --config FILE          Path to a config.json file
```

#### Feature Modules
```
--extract-endpoints        Enable API endpoint extraction
--no-extract-endpoints     Disable endpoint extraction
--endpoint-regex PATTERN   Add custom regex pattern for endpoint extraction (can be used multiple times)
--analyze-similarity       Enable similarity analysis (rename detection)
--no-analyze-similarity    Disable similarity analysis
--display-endpoints        Display new endpoints on screen (enabled by default)
--no-display-endpoints     Disable displaying endpoints on screen
```

#### Filtering Options
```
--include-domain DOMAIN    Only process JS files from this domain (can be used multiple times)
--exclude-domain DOMAIN    Exclude JS files from this domain (can be used multiple times)
--include-url PATTERN      Only process URLs matching this regex pattern
--exclude-url PATTERN      Exclude URLs matching this regex pattern (e.g. ".*\\.map$" for source maps)
```

#### Behavior Configuration
```
--live                     Enable continuous monitoring mode
--no-live                  Disable live mode (default)
--interval SECONDS         Seconds between scans in live mode (default: 300)
--headless                 Run browser in headless mode (default: true)
--no-headless              Show browser window
-v, --verbose              Enable verbose logging
--no-verbose               Disable verbose logging
```

#### Notification Options
```
--discord-webhook URL      Discord webhook URL for notifications
--no-notifications         Disable all Discord notifications
```

#### Special Commands
```
--test-discord             Send a test message to Discord webhook and exit
```

## Configuration File

Create a `config.json` file based on `config.json.example`:

```json
{
  "urls": [
    "https://example.com"
  ],
  "extract_endpoints": true,
  "analyze_similarity": true,
  "display_endpoints": true,
  "filters": {
    "include_domain": [],
    "exclude_domain": [],
    "include_url": [],
    "exclude_url": [".*\\.map$"]
  },
  "endpoint_patterns": {
    "path_patterns": [
      "[\"\\'](/[\\w\\-/]+(?:/\\$[\\w{}.]+)*/?[\\w\\-/]*)[\"\\'']"
    ],
    "fetch_patterns": [
      "fetch\\s*\\(\\s*[`\\'\"]((?:https?://[^/]+)?/[^\"'`]+)"
    ],
    "axios_patterns": [
      "\\.(get|post|put|delete|patch)\\s*\\(\\s*[`'\"]([^\"'`]+)"
    ],
    "template_literal_paths": [
      "`[^`]*?\\$\\{[^}]+\\}(/(?:api|v\\d+)/[^`\\s\"']+)`",
      "`[^`]*?\\$\\{[^}]+\\}(/[^`]+?)`"
    ],
    "e_method_patterns": [
      "e\\.(get|post|put|delete|patch|head)\\s*\\(\\s*`([^`]+?)`"
    ],
    "custom_patterns": []
  },
  "live_mode": false,
  "interval": 300,
  "headless": true,
  "verbose": false,
  "discord_webhook": "https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN"
}
```

**Note**: CLI arguments always override config file settings.

### Endpoint Extraction Patterns

**⚠️ IMPORTANT:** WebMonner has NO hardcoded endpoint patterns. You MUST provide patterns via configuration file or CLI flags.

Endpoint extraction patterns are fully customizable regex patterns. You can define them in two ways:

#### 1. Via Configuration File (Recommended)

Add patterns to the `endpoint_patterns` section in `config.json`. You can organize patterns by category (category names are arbitrary):

**Common pattern categories:**
- **path_patterns**: Simple path strings like `"/api/users"`
- **fetch_patterns**: `fetch()` API calls
- **axios_patterns**: HTTP client methods (`.get()`, `.post()`, etc.)
- **template_literal_paths**: Template literals with variables
- **e_method_patterns**: Custom HTTP client patterns
- **custom_patterns**: Any custom patterns you define

The `config.json.example` includes default patterns for common JavaScript patterns (fetch, axios, etc.). Copy and customize as needed.

Example adding GraphQL endpoints:
```json
{
  "endpoint_patterns": {
    "path_patterns": [
      "[\"\\'](/[\\w\\-/]+(?:/\\$[\\w{}.]+)*/?[\\w\\-/]*)[\"\\'']"
    ],
    "graphql_patterns": [
      "query:\\s*['\"]([^'\"]+)['\"]",
      "mutation:\\s*['\"]([^'\"]+)['\"]"
    ]
  }
}
```

#### 2. Via Command Line

Add patterns directly from the command line using `--endpoint-regex` (can be used multiple times):

```bash
python main.py \
  --url https://example.com \
  --extract-endpoints \
  --endpoint-regex "[\"\\'](/[\\w\\-/]+)[\\\"\\']" \
  --endpoint-regex "fetch\\s*\\(\\s*['\\\"]([^'\\\"]+)"
```

**Pattern Requirements:**
- Patterns must be valid Python regex
- Use proper escaping (double backslashes `\\` in JSON, single `\` in CLI)
- Patterns should capture the endpoint path in a capture group
- CLI patterns are added to the `custom_patterns` category and merge with config file patterns
- If no patterns are provided, endpoint extraction will not find anything

## Discord Webhook Setup

1. Open your Discord server settings
2. Go to **Integrations** → **Webhooks**
3. Click **New Webhook**
4. Give it a name (e.g., "WebMonner Bot")
5. Select the channel for notifications
6. Copy the webhook URL
7. Use it with `--discord-webhook` or in your config file

Test your webhook:
```bash
python main.py --test-discord --discord-webhook "YOUR_WEBHOOK_URL"
```

## Examples

### Monitor a site every 10 minutes with all features enabled

```bash
python main.py \
  --url https://example.com \
  --live \
  --interval 600 \
  --extract-endpoints \
  --analyze-similarity \
  --discord-webhook "YOUR_WEBHOOK_URL"
```

### Scan multiple sites from a file, only include specific domains

```bash
python main.py \
  --urls-file targets.txt \
  --include-domain cdn.example.com \
  --include-domain static.example.com \
  --extract-endpoints
```

### Scan with verbose output and browser window visible

```bash
python main.py \
  --url https://example.com \
  --no-headless \
  --verbose
```

### Extract endpoints with custom regex patterns

```bash
python main.py \
  --url https://example.com \
  --extract-endpoints \
  --endpoint-regex "api\.request\(['\"]([^'\"]+)" \
  --endpoint-regex "endpoints\.[a-zA-Z]+\s*=\s*['\"]([^'\"]+)"
```

### Extract endpoints without displaying them on screen

```bash
python main.py \
  --url https://example.com \
  --extract-endpoints \
  --no-display-endpoints
```

## Data Structure

WebMonner stores all data in the `./data/` directory:

```
data/
├── example.com/
│   ├── original/          # Original downloaded JS files
│   ├── beautified/        # Beautified versions for diff analysis
│   ├── diffs/             # Diff files (if needed)
│   ├── endpoints/         # Extracted endpoints
│   │   ├── all-endpoints.json                  # All discovered endpoints (cumulative)
│   │   ├── new-endpoints-2025-11-18_14-30-45.json  # NEW endpoints from a specific scan
│   │   └── new-endpoints-2025-11-18_15-00-12.json  # NEW endpoints from another scan
│   ├── fingerprints/      # Structural fingerprints for similarity analysis
│   └── hashes.json        # File hashes and metadata
└── another-site.com/
    └── ...
```

### Understanding Endpoint Files

- **`all-endpoints.json`**: Contains ALL endpoints ever discovered (cumulative)
- **`new-endpoints-{timestamp}.json`**: Contains ONLY the new endpoints discovered in a specific scan
  - Created automatically when new endpoints are found
  - Timestamped for easy identification (format: `YYYY-MM-DD_HH-MM-SS`)
  - Discord notifications include the filename for quick reference
  - Perfect for quickly reviewing what changed after a deployment

### Endpoint Display Options

By default, new endpoints are displayed on the console during scanning:

```
===============================================================
🎯 New Endpoints for example.com (3 total)
===============================================================
    1. /api/v2/users
    2. /api/v2/products
    3. /api/v2/orders
===============================================================
```

You can disable this behavior with `--no-display-endpoints` or by setting `"display_endpoints": false` in your config file. Endpoints will still be saved to files and sent to Discord (if configured).

## How It Works

1. **Discovery**: Uses Playwright to load target URLs and intercept all JavaScript file requests
2. **Download**: Fetches discovered JS files and calculates SHA-256 hashes
3. **Change Detection**: Compares hashes against stored database to detect new/modified files
4. **Beautification**: Beautifies minified code using jsbeautifier for better diff readability
5. **Endpoint Extraction**: Uses regex patterns and AST parsing (esprima) to find API endpoints
6. **Similarity Analysis**: Creates structural fingerprints to detect renamed/moved files
7. **Notification**: Sends batched summaries to Discord with all changes and findings

**📖 For detailed pattern creation guide, see [ENDPOINT_PATTERNS.md](ENDPOINT_PATTERNS.md)**

## Troubleshooting

### Playwright Installation Issues

If you encounter browser installation errors:
```bash
playwright install --force chromium
```

### SSL Certificate Errors

WebMonner ignores HTTPS errors by default. If you need stricter validation, modify `crawler.py` line 75.

### Memory Issues

For sites with many JS files, consider:
- Using domain filters to reduce scope
- Increasing system swap space
- Running in smaller batches

## Security Considerations

⚠️ **Important**: WebMonner is designed for authorized security research and monitoring of your own web applications.

- Always obtain proper authorization before scanning websites
- Respect robots.txt and rate limits
- Use responsibly and ethically
- Be aware of legal implications in your jurisdiction

## Requirements

- Python 3.9+
- Chromium browser (installed via Playwright)
- Internet connection

## License

MIT License - see LICENSE file for details

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Roadmap

- [ ] Multi-threaded scanning for better performance
- [ ] Support for authenticated scanning
- [ ] Custom JavaScript execution before scanning
- [ ] Webhook support for other platforms (Slack, Teams)
- [ ] Export results to JSON/CSV
- [ ] Web dashboard for viewing results

## Author

Created for security researchers and DevOps teams who need to monitor JavaScript changes on web applications.

---

**Happy Monitoring! 🚀**

