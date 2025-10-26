import re
import json
from pathlib import Path
from urllib.parse import urlparse
from typing import List, Dict, Set
import esprima

from utils import log, DATA_DIR

class EndpointExtractor:
    """Extracts API endpoints from JavaScript code using regex and AST parsing."""

    def __init__(self, patterns: dict = None):
        """
        Initialize the EndpointExtractor with patterns from config or CLI.
        
        Args:
            patterns: Dict of pattern categories containing regex strings.
                     If None or empty, no patterns will be used.
        """
        # Compile all patterns from config/CLI
        self.patterns = {}
        
        if patterns:
            for category, pattern_strings in patterns.items():
                if pattern_strings:  # Only process non-empty pattern lists
                    compiled_patterns = []
                    for p in pattern_strings:
                        try:
                            compiled_patterns.append(re.compile(p))
                        except re.error as e:
                            log.warning(f"Invalid regex pattern in category '{category}': {p} - Error: {e}")
                    
                    if compiled_patterns:
                        self.patterns[category] = compiled_patterns
        
        # Log info about loaded patterns
        if self.patterns:
            total_patterns = sum(len(p) for p in self.patterns.values())
            log.info(f"Loaded {total_patterns} endpoint extraction patterns across {len(self.patterns)} categories")
        else:
            log.warning("No endpoint patterns loaded. Endpoint extraction may not find anything.")
        
        self.domain_data_path = DATA_DIR

    def _normalize_endpoint(self, endpoint: str) -> str:
        """Normalizes endpoints by replacing variables like ${id} with {var}."""
        # Replace complex template literal expressions with ternary operators
        # ${d ? '&cursor=' + d : ''} -> {var}
        endpoint = re.sub(r'\$\{[^}]+\?[^}]+:[^}]+\}', '{var}', endpoint)
        # Replace template literal variables: ${x.cart_id} -> {var}
        endpoint = re.sub(r'\$\{[^}]+\}', '{var}', endpoint)
        # Replace path parameters: :id -> {param}
        endpoint = re.sub(r':\w+', '{param}', endpoint)
        # Replace x.cart_id or similar inline variables with {var}
        endpoint = re.sub(r'\b[a-z]\.\w+', '{var}', endpoint)
        return endpoint

    def _is_clean_endpoint(self, endpoint: str) -> bool:
        """Filters out common false positives like image paths, regex patterns, or simple strings."""
        if not endpoint.startswith('/'):
            return False
        
        # Minimum length: /v1, /me are valid (3 chars including leading /)
        if len(endpoint) < 2:
            return False
        
        # Filter out HTML tags (e.g., /h5>, /p>, /div>)
        if re.search(r'/[a-z0-9]+>', endpoint, re.IGNORECASE):
            return False
        
        # Filter out URLs (protocol-relative URLs like //domain.com)
        if endpoint.startswith('//'):
            return False
        
        # Filter out JavaScript regex patterns like /pattern/flags or /pattern/);
        # Common endings: /g, /gi, /gm, /i, /m, /), /,
        # But allow trailing slash for routes like /api/
        if re.search(r'/[gimsuvy,);]*$', endpoint) and not endpoint.endswith('/'):
            return False
        
        # Filter out obvious regex patterns with backslash escapes
        if '\\' in endpoint:
            return False
        
        # Filter out patterns with regex brackets
        if '[' in endpoint or ']' in endpoint:
            return False
        
        # Filter out regex lookaheads and special groups (but not query params with ?)
        if '?:' in endpoint or '?=' in endpoint or '?!' in endpoint:
            return False
        
        # Filter out file extensions
        if re.search(r'\.(js|css|html|png|jpg|jpeg|gif|svg|woff|ttf|pdf|heic)$', endpoint, re.IGNORECASE):
            return False
        
        # Filter out paths with invalid/suspicious characters
        # Allow: {var}, {param}, :param (route parameters), ?, &, =, -, _, ., /, trailing /
        # Disallow: <, >, |, *, %, (, ), +, ;, ,, !, @, #, $
        invalid_chars = [' ', '<', '>', '|', '*', '%', '(', ')', '+', ';', ',', '!', '@', '#', '$']
        
        # Check for invalid characters
        if any(c in endpoint for c in invalid_chars):
            return False
        
        # Allow colons for route parameters like :id, :userId
        # Allow { and } for {var} and {param} placeholders
        # Just ensure they're not malformed
        
        # Must contain meaningful content (letters, numbers, or common path chars)
        # Allow single char paths like /v1, /v2, /me
        if not re.search(r'[a-zA-Z0-9_-]', endpoint):
            return False
        
        # Filter out suspicious single-char segments after slash
        # Bad: /9, /-, /;  Good: /v1, /me, /api
        if endpoint.count('/') == 1:  # Single segment path
            path_content = endpoint[1:]  # Remove leading /
            # If it's a single non-letter char, reject
            if len(path_content) == 1:
                if not path_content.isalpha():  # Must be a letter for single-char paths
                    return False
        
        return True

    def _extract_template_path(self, endpoint: str) -> str:
        """
        Extracts the path from a template literal, handling nested expressions.
        Handles complex cases like: ${ o }/api/v1/orders?x=${ n.value }&y=6${ d ? '&cursor=' + d : '' }
        """
        # Find where the actual path starts (first /)
        path_start = endpoint.find('/')
        if path_start == -1:
            return endpoint
        
        # Extract from / to end, preserving ${...} blocks even if they contain quotes
        result = []
        i = path_start
        in_template_expr = False
        brace_depth = 0
        
        while i < len(endpoint):
            char = endpoint[i]
            
            if char == '$' and i + 1 < len(endpoint) and endpoint[i + 1] == '{':
                in_template_expr = True
                result.append(char)
                i += 1
                result.append(endpoint[i])  # Add the '{'
                brace_depth = 1
            elif in_template_expr:
                result.append(char)
                if char == '{':
                    brace_depth += 1
                elif char == '}':
                    brace_depth -= 1
                    if brace_depth == 0:
                        in_template_expr = False
            elif char == '`':
                # End of template literal
                break
            elif char in ('"', "'") and not in_template_expr:
                # Quote outside of template expression - might be end of string
                break
            elif char in (' ', '\n', '\r', '\t'):
                # Whitespace - likely end of path
                break
            else:
                result.append(char)
            
            i += 1
        
        return ''.join(result)

    def _extract_with_regex(self, code: str) -> Set[str]:
        """Extracts endpoints using predefined regex patterns."""
        found = set()
        for category, patterns in self.patterns.items():
            for pattern in patterns:
                matches = pattern.findall(code)
                for match in matches:
                    # Handle tuples from patterns with capture groups
                    endpoint = match if isinstance(match, str) else match[-1]
                    
                    # For template literals, clean up the path
                    if category in ["template_literal_paths", "e_method_patterns", "axios_patterns", "fetch_patterns"]:
                        endpoint = self._extract_template_path(endpoint)
                    
                    # Normalize first (replaces ${...} with {var}), then check if clean
                    normalized = self._normalize_endpoint(endpoint)
                    if self._is_clean_endpoint(normalized):
                        found.add(normalized)
        return found
        
    def _extract_with_ast(self, code: str) -> Set[str]:
        """Extracts endpoints by parsing the JS code into an AST and finding string literals."""
        found = set()
        try:
            tree = esprima.parse(code, {'loc': False})
            
            # Simple recursive traversal to find string literals
            def traverse(node):
                if isinstance(node, dict):
                    if node.get('type') == 'Literal' and isinstance(node.get('value'), str):
                        val = node['value']
                        if self._is_clean_endpoint(val):
                            found.add(self._normalize_endpoint(val))
                    
                    # Also check template literals for paths
                    if node.get('type') == 'TemplateElement' and node.get('value', {}).get('raw'):
                         val = node['value']['raw']
                         if self._is_clean_endpoint(val):
                            found.add(self._normalize_endpoint(val))

                    for key in node:
                        traverse(node[key])
                elif isinstance(node, list):
                    for item in node:
                        traverse(item)

            traverse(tree.toDict())

        except Exception as e:
            # AST parsing can fail on modern JS syntax (optional chaining, private fields, etc.)
            # This is not critical since regex extraction still works
            pass
        return found
        
    def extract(self, file_path: Path, domain: str, filters: dict) -> Set[str]:
        """
        Main extraction method. Reads a file and extracts all endpoints.
        Returns a set of endpoints found in this file (not compared yet).
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                code = f.read()
        except FileNotFoundError:
            log.warning(f"File not found for endpoint extraction: {file_path}")
            return set()
        
        # Combine results from all methods
        regex_endpoints = self._extract_with_regex(code)
        ast_endpoints = self._extract_with_ast(code)
        all_endpoints = regex_endpoints.union(ast_endpoints)
        
        return all_endpoints
    
    def save_and_compare(self, domain: str, extracted_endpoints: Set[str]) -> List[str]:
        """
        Compares extracted endpoints with existing ones and saves new ones.
        This should be called once per domain after all files are processed.
        
        Args:
            domain: Domain name
            extracted_endpoints: All endpoints extracted from all files in this scan
            
        Returns:
            List of NEW endpoints (sorted)
        """
        # Sanitize domain name for Windows (colons not allowed in directory names)
        safe_domain = domain.replace(':', '_')
        endpoints_dir = self.domain_data_path / safe_domain / "endpoints"
        endpoints_dir.mkdir(exist_ok=True, parents=True)
        all_endpoints_path = endpoints_dir / "all-endpoints.json"
        
        existing_endpoints = set()
        if all_endpoints_path.exists():
            with open(all_endpoints_path, 'r') as f:
                try:
                    existing_endpoints.update(json.load(f))
                except json.JSONDecodeError:
                    pass
        
        # Find truly NEW endpoints
        new_endpoints = sorted(list(extracted_endpoints - existing_endpoints))
        
        # Save the combined list (existing + newly extracted)
        if extracted_endpoints:
            updated_list = sorted(list(extracted_endpoints.union(existing_endpoints)))
            with open(all_endpoints_path, 'w') as f:
                json.dump(updated_list, f, indent=4)
                
        return new_endpoints