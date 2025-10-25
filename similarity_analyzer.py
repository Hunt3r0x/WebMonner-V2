import hashlib
import json
import re
from typing import Dict, Any, List, Tuple
from pathlib import Path
import esprima

from utils import log
from file_manager import FileManager

class SimilarityAnalyzer:
    """
    Detects renamed or moved JavaScript files by creating and comparing
    "fingerprints" of the code structure.
    """
    SIMILARITY_THRESHOLD = 0.70  # 70% similarity

    def __init__(self, file_manager: FileManager):
        self.file_manager = file_manager

    def _extract_features_from_ast(self, js_code: str) -> Tuple[set, set]:
        """Try to extract features using AST parsing."""
        function_signatures = set()
        import_exports = set()
        
        # Try parseModule first (for ES6 modules)
        tree = None
        try:
            tree = esprima.parseModule(js_code, {'loc': False, 'tolerant': True})
        except:
            pass
            
        # Fall back to parseScript (for regular scripts)
        if tree is None:
            try:
                tree = esprima.parseScript(js_code, {'loc': False, 'tolerant': True})
            except:
                return function_signatures, import_exports
        
        def traverse(node):
            if isinstance(node, dict):
                # Function declarations and class methods
                if node.get('type') in ('FunctionDeclaration', 'MethodDefinition'):
                    if node.get('id') and node.get('id').get('name'):
                        function_signatures.add(node['id']['name'])
                # Arrow functions assigned to variables
                if node.get('type') == 'VariableDeclarator' and node.get('init', {}).get('type') == 'ArrowFunctionExpression':
                     if node.get('id') and node.get('id').get('name'):
                        function_signatures.add(node['id']['name'])
                # Import/Export statements
                if node.get('type') in ('ImportDeclaration', 'ExportNamedDeclaration', 'ExportDefaultDeclaration'):
                    if node.get('source') and node.get('source').get('value'):
                         import_exports.add(f"source:{node['source']['value']}")
                for key in node:
                    traverse(node[key])
            elif isinstance(node, list):
                for item in node:
                    traverse(item)
        
        traverse(tree.toDict())
        return function_signatures, import_exports
    
    def _extract_features_from_regex(self, js_code: str) -> Tuple[set, set]:
        """Extract features using regex as fallback when AST parsing fails."""
        function_signatures = set()
        import_exports = set()
        
        # Extract function declarations: function name(...) or const name = function(...) or const name = (...) =>
        func_patterns = [
            r'\bfunction\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\(',  # function name()
            r'\b(?:const|let|var)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*=\s*function',  # const name = function
            r'\b(?:const|let|var)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*=\s*\([^)]*\)\s*=>',  # const name = () =>
            r'([a-zA-Z_$][a-zA-Z0-9_$]*)\s*:\s*function\s*\(',  # name: function() (object methods)
            r'([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\([^)]*\)\s*\{',  # name() { (method shorthand)
        ]
        
        for pattern in func_patterns:
            matches = re.finditer(pattern, js_code)
            for match in matches:
                function_signatures.add(match.group(1))
        
        # Extract imports/exports
        import_patterns = [
            r'import\s+.*?from\s+["\']([^"\']+)["\']',  # import ... from "..."
            r'export\s+.*?from\s+["\']([^"\']+)["\']',  # export ... from "..."
            r'require\s*\(\s*["\']([^"\']+)["\']\s*\)',  # require("...")
        ]
        
        for pattern in import_patterns:
            matches = re.finditer(pattern, js_code)
            for match in matches:
                import_exports.add(f"source:{match.group(1)}")
        
        return function_signatures, import_exports

    def _create_fingerprint(self, js_code: str, url: str) -> Dict[str, Any] | None:
        """
        Generates a structural fingerprint of the code.
        Uses AST parsing when possible, falls back to regex when parsing fails.
        """
        try:
            # 1. Try to extract function signatures and import/export statements via AST
            function_signatures, import_exports = self._extract_features_from_ast(js_code)
            
            # 2. If AST parsing yielded no results, fall back to regex
            if not function_signatures and not import_exports:
                function_signatures, import_exports = self._extract_features_from_regex(js_code)

            # 3. Generate content hash (normalized)
            normalized_code = ''.join(js_code.split()) # Remove all whitespace
            content_hash = hashlib.sha256(normalized_code.encode('utf-8')).hexdigest()

            return {
                "url": url,
                "function_signatures": sorted(list(function_signatures)),
                "import_exports": sorted(list(import_exports)),
                "content_hash": content_hash,
                "code_length": len(js_code)
            }
        except Exception as e:
            log.error(f"  > Fingerprint creation failed for {url}: {str(e).splitlines()[0]}")
            return None

    def _calculate_similarity(self, fp1: Dict, fp2: Dict) -> float:
        """Calculates a similarity score between two fingerprints."""
        if not fp1 or not fp2:
            return 0.0

        # Jaccard similarity for functions and imports
        funcs1, funcs2 = set(fp1['function_signatures']), set(fp2['function_signatures'])
        imports1, imports2 = set(fp1['import_exports']), set(fp2['import_exports'])

        func_sim = len(funcs1.intersection(funcs2)) / len(funcs1.union(funcs2)) if funcs1.union(funcs2) else 0
        import_sim = len(imports1.intersection(imports2)) / len(imports1.union(imports2)) if imports1.union(imports2) else 0
        
        hash_sim = 1.0 if fp1['content_hash'] == fp2['content_hash'] else 0.0

        # Weighted average
        score = (func_sim * 0.4) + (import_sim * 0.3) + (hash_sim * 0.3)
        return score

    def find_potential_renames(self, new_file_url: str, domain: str) -> List[Tuple[str, float]]:
        """
        Compares a new file's fingerprint against all existing fingerprints for a domain.
        """
        domain_path = self.file_manager._get_domain_path(domain)
        fingerprints_dir = domain_path / "fingerprints"
        fingerprints_dir.mkdir(exist_ok=True)
        
        # Get path to the new file's beautified code
        paths = self.file_manager._get_file_paths(domain_path, new_file_url)
        new_file_path = paths['beautified_path']

        if not new_file_path.exists():
            return []

        # Create fingerprint for the new file
        new_code = new_file_path.read_text(encoding='utf-8')
        new_fingerprint = self._create_fingerprint(new_code, new_file_url)
        if not new_fingerprint:
            return []

        # Compare with all existing fingerprints
        similar_files = []
        for fp_path in fingerprints_dir.glob("*.json"):
            existing_fp = json.loads(fp_path.read_text())
            
            # Don't compare to itself if it somehow exists already
            if existing_fp['url'] == new_file_url:
                continue
                
            similarity = self._calculate_similarity(new_fingerprint, existing_fp)
            if similarity >= self.SIMILARITY_THRESHOLD:
                similar_files.append((existing_fp['url'], similarity))

        # Save the new fingerprint for future comparisons
        new_fp_path = fingerprints_dir / f"{self.file_manager._get_file_paths(domain_path, new_file_url)['beautified_path'].stem}.json"
        new_fp_path.write_text(json.dumps(new_fingerprint, indent=4))
        
        return sorted(similar_files, key=lambda x: x[1], reverse=True)

