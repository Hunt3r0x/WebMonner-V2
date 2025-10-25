# Endpoint Patterns Reference

This document explains how to create and use endpoint extraction patterns in WebMonner.

## ⚠️ Important

WebMonner has **NO hardcoded patterns**. You must provide patterns via:
1. `config.json` file (recommended)
2. `--endpoint-regex` CLI flag

## Quick Start

Copy `config.json.example` to `config.json` and customize the `endpoint_patterns` section.

## Pattern Categories

Pattern categories are completely arbitrary - you can name them anything. They're just for organization.

### Suggested Categories:

- **path_patterns** - Simple string paths
- **fetch_patterns** - Browser fetch() API
- **axios_patterns** - Axios HTTP client
- **template_literal_paths** - Template literals with variables
- **e_method_patterns** - Custom HTTP client methods
- **custom_patterns** - Your own patterns

## Default Patterns Explained

### 1. Path Patterns
```regex
["\'](/[\w\-/]+(?:/\$[\w{}.]+)*/?[\w\-/]*)["\']
```
**Matches:**
- `"/api/users"`
- `'/dashboard/settings'`
- `"/api/cart/${id}"`

**Captures:** The path part between quotes

---

### 2. Fetch Patterns
```regex
fetch\s*\(\s*[`\'"]((?:https?://[^/]+)?/[^"\'`]+)
```
**Matches:**
- `fetch("/api/data")`
- `fetch('https://api.example.com/users')`
- ``fetch(`/api/items`)``

**Captures:** The URL argument to fetch()

---

### 3. Axios Patterns
```regex
\.(get|post|put|delete|patch)\s*\(\s*[`\'"]([^"\'`]+)
```
**Matches:**
- `axios.get("/api/users")`
- `client.post('/login')`
- `http.delete("/api/item/123")`

**Captures:** The URL argument (second capture group)

---

### 4. Template Literal Paths
```regex
`[^`]*?\$\{[^}]+\}(/(?:api|v\d+)/[^`\s"\']+)`
```
**Matches:**
- `` `${baseUrl}/api/v1/users` ``
- `` `${host}/v2/products` ``

**Captures:** The path part after the template variable

```regex
`[^`]*?\$\{[^}]+\}(/[^`]+?)`
```
**Matches:**
- `` `${base}/api/cart/${id}/checkout` ``

**Captures:** The entire path with variables (normalized later)

---

### 5. E Method Patterns (Custom HTTP Client)
```regex
e\.(get|post|put|delete|patch|head)\s*\(\s*`([^`]+?)`
```
**Matches:**
- ``e.get(`/api/resource`)``
- ``e.post(`/api/create`)``

**Captures:** The path argument (second capture group)

---

## Creating Custom Patterns

### Pattern Structure

Your regex should capture the endpoint path in a capture group. Examples:

#### Example 1: GraphQL Queries
```regex
query:\s*['"]([^'"]+)['"]
```
**Matches:** `query: "getUserById"`

#### Example 2: Custom API Client
```regex
api\.request\(['"](\w+)['"]\s*,\s*['"]([^'"]+)['"]
```
**Matches:** `api.request('GET', '/api/users')`

#### Example 3: Route Definitions
```regex
\.route\(['"]([^'"]+)['"]\)
```
**Matches:** `app.route('/api/login')`

#### Example 4: WebSocket Endpoints
```regex
new\s+WebSocket\(['"]([^'"]+)['"]
```
**Matches:** `new WebSocket('/ws/chat')`

### Tips for Writing Patterns

1. **Use capture groups `()`** - The captured part becomes the endpoint
2. **Escape special characters** - In JSON use `\\`, in CLI use `\`
3. **Test your patterns** - Use online regex testers
4. **Be specific** - Avoid overly broad patterns that match everything
5. **Handle quotes** - Match all quote types: `['"\`]`

### Common Regex Elements

| Element | Meaning | Example |
|---------|---------|---------|
| `\s` | Whitespace | Matches spaces, tabs |
| `\w` | Word character | Letters, digits, underscore |
| `[^']` | Not apostrophe | Anything except `'` |
| `+` | One or more | `/api/\w+` matches `/api/users` |
| `*` | Zero or more | `\s*` matches any whitespace |
| `?` | Optional | `s?` matches `s` or nothing |
| `\.` | Literal dot | Escaped dot character |
| `\(` | Literal paren | Escaped parenthesis |

## JSON Escaping Rules

In `config.json`, backslashes must be doubled:

| Pattern | JSON |
|---------|------|
| `\s` | `"\\s"` |
| `\w` | `"\\w"` |
| `\.` | `"\\."` |
| `\(` | `"\\("` |
| `\"` | `"\\\""` |

### Example Config:
```json
{
  "endpoint_patterns": {
    "api_calls": [
      "api\\.call\\(['\"]([^'\"]+)['\"]\\)"
    ],
    "routes": [
      "router\\.(get|post)\\(['\"]([^'\"]+)"
    ]
  }
}
```

## CLI Usage

Add patterns via command line (no JSON escaping needed):

```bash
# Single pattern
python main.py --url https://example.com --endpoint-regex "api\.call\(['\"]([^'\"]+)"

# Multiple patterns
python main.py \
  --url https://example.com \
  --endpoint-regex "api\.request\(['\"]([^'\"]+)" \
  --endpoint-regex "router\.(get|post)\(['\"]([^'\"]+)"
```

## Pattern Testing

Before adding patterns, test them:

1. **Online Tools:**
   - https://regex101.com/ (select Python flavor)
   - https://regexr.com/

2. **Sample JavaScript to Test:**
```javascript
fetch("/api/users")
axios.get("/api/products")
api.request('GET', '/api/items')
e.post(`/api/create`)
```

3. **Expected Results:**
   - `/api/users`
   - `/api/products`
   - `/api/items`
   - `/api/create`

## Troubleshooting

### Pattern Not Matching?

1. Check escaping (double backslash in JSON)
2. Verify capture group exists `()`
3. Test on regex101.com
4. Enable verbose mode: `--verbose`

### Too Many False Positives?

1. Make pattern more specific
2. Use word boundaries `\b`
3. Add context before/after the match
4. Filter out static files in pattern

### Invalid Regex Error?

Check the logs - WebMonner will show which pattern failed and why.

## Advanced Examples

### Match Multiple HTTP Methods
```regex
\b(get|post|put|patch|delete)Request\(['"]([^'"]+)
```

### Match REST API Versions
```regex
/api/v[0-9]+/([a-z\-/]+)
```

### Match Dynamic Routes with Params
```regex
router\.(get|post)\(['"]([^'"]+/:[\w]+[^'"]*)['"]\)
```

### Match jQuery AJAX
```regex
\$\.ajax\(\{[^}]*url:\s*['"]([^'"]+)['"]
```

## Best Practices

1. ✅ Start with provided patterns in `config.json.example`
2. ✅ Add custom patterns incrementally
3. ✅ Test patterns on sample code first
4. ✅ Use descriptive category names
5. ✅ Keep patterns focused and specific
6. ❌ Don't make patterns too greedy (avoid `.*`)
7. ❌ Don't forget to escape special characters
8. ❌ Don't capture too much context

## Need Help?

- Check the README.md for more examples
- Open an issue on GitHub
- Test your patterns on regex101.com

---

**Happy pattern hunting! 🎯**

