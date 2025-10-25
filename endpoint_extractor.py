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
        # Replace template literal variables: ${x.cart_id} -> {var}
        endpoint = re.sub(r'\$\{[\w.]+\}', '{var}', endpoint)
        # Replace path parameters: :id -> {param}
        endpoint = re.sub(r':\w+', '{param}', endpoint)
        # Replace x.cart_id or similar inline variables with {var}
        endpoint = re.sub(r'\b[a-z]\.\w+', '{var}', endpoint)
        return endpoint

    def _is_clean_endpoint(self, endpoint: str) -> bool:
        """Filters out common false positives like image paths or simple strings."""
        if not endpoint.startswith('/'):
            return False
        if len(endpoint) < 3:
            return False
        if re.search(r'\.(js|css|html|png|jpg|jpeg|gif|svg|woff|ttf)$', endpoint, re.IGNORECASE):
            return False
        if ' ' in endpoint or '<' in endpoint or '>' in endpoint:
            return False
        return True

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
                    if category in ["template_literal_paths", "e_method_patterns"]:
                        # Extract just the path part (everything starting with /)
                        path_match = re.search(r'(/[^`\s"\']*)', endpoint)
                        if path_match:
                            endpoint = path_match.group(1)
                    
                    if self._is_clean_endpoint(endpoint):
                        found.add(self._normalize_endpoint(endpoint))
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
        
    def extract(self, file_path: Path, domain: str, filters: dict) -> List[str]:
        """
        Main extraction method. Reads a file and uses all techniques to find endpoints.
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                code = f.read()
        except FileNotFoundError:
            log.warning(f"File not found for endpoint extraction: {file_path}")
            return []
        
        # Combine results from all methods
        regex_endpoints = self._extract_with_regex(code)
        ast_endpoints = self._extract_with_ast(code)
        all_endpoints = regex_endpoints.union(ast_endpoints)

        # --- Load existing endpoints to find only new ones ---
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
        
        new_endpoints = sorted(list(all_endpoints - existing_endpoints))
        
        # --- Save updated list ---
        if new_endpoints:
            updated_list = sorted(list(all_endpoints.union(existing_endpoints)))
            with open(all_endpoints_path, 'w') as f:
                json.dump(updated_list, f, indent=4)
                
        return new_endpoints