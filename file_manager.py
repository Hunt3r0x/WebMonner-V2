import os
import json
import difflib
from pathlib import Path
from urllib.parse import urlparse, quote_plus
from typing import Dict, Any, Tuple
import jsbeautifier

from utils import log, DATA_DIR

class FileManager:
    """Handles all file system operations: saving, diffing, and managing data directories."""

    def __init__(self, base_dir: Path = DATA_DIR):
        self.base_dir = base_dir
        self.base_dir.mkdir(exist_ok=True)

    def _get_domain_path(self, domain: str) -> Path:
        """Gets the base path for a given domain."""
        # Sanitize domain name for Windows (colons are not allowed in directory names)
        safe_domain = domain.replace(':', '_')
        domain_path = self.base_dir / safe_domain
        domain_path.mkdir(exist_ok=True)
        return domain_path

    def _get_file_paths(self, domain_path: Path, url: str) -> Dict[str, Path]:
        """Creates the necessary subdirectories and returns paths for a JS file."""
        # Use hash of URL to avoid Windows path length issues
        import hashlib
        url_hash = hashlib.sha256(url.encode('utf-8')).hexdigest()[:16]
        
        # Try to extract a meaningful name from the URL
        try:
            parsed = urlparse(url)
            path_parts = parsed.path.strip('/').split('/')
            filename = path_parts[-1] if path_parts else 'index'
            # Remove query string and clean filename
            filename = filename.split('?')[0].replace('.js', '')
            # Limit length and sanitize
            filename = filename[:50]
            safe_filename = f"{filename}_{url_hash}"
        except Exception:
            safe_filename = url_hash
        
        paths = {
            "original": domain_path / "original",
            "beautified": domain_path / "beautified",
            "diffs": domain_path / "diffs",
            "endpoints": domain_path / "endpoints",
            "fingerprints": domain_path / "fingerprints"
        }
        for path in paths.values():
            path.mkdir(exist_ok=True)
        
        return {
            "original_path": paths["original"] / f"{safe_filename}.js",
            "beautified_path": paths["beautified"] / f"{safe_filename}.js",
            "hashes_path": domain_path / "hashes.json",
        }

    def _load_hashes(self, hashes_path: Path) -> Dict[str, Any]:
        """Loads the hash database for a domain."""
        if not hashes_path.exists():
            return {}
        with open(hashes_path, 'r') as f:
            return json.load(f)

    def _save_hashes(self, hashes_path: Path, hashes: Dict[str, Any]):
        """Saves the hash database for a domain."""
        with open(hashes_path, 'w') as f:
            json.dump(hashes, f, indent=4)
            
    def _generate_diff(self, old_content: str, new_content: str) -> Tuple[str, int, int]:
        """Generates a unified diff and counts added/removed lines."""
        diff_lines = list(difflib.unified_diff(
            old_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile='old',
            tofile='new'
        ))
        
        added = sum(1 for line in diff_lines if line.startswith('+') and not line.startswith('+++'))
        removed = sum(1 for line in diff_lines if line.startswith('-') and not line.startswith('---'))
        
        return "".join(diff_lines), added, removed

    def process_js_file(self, url: str, content: bytes, new_hash: str) -> Tuple[str, Dict[str, Any]]:
        """
        Processes a single JS file: compares hash, saves files, and generates diffs.
        Returns the status and a dictionary of file info.
        """
        try:
            domain = urlparse(url).netloc
            domain_path = self._get_domain_path(domain)
            paths = self._get_file_paths(domain_path, url)

            hashes = self._load_hashes(paths["hashes_path"])
            existing_entry = hashes.get(url)

            # Beautify the content
            try:
                beautified_content = jsbeautifier.beautify(content.decode('utf-8'))
            except Exception:
                log.warning(f"Could not beautify {url}, using original content for diff.")
                beautified_content = content.decode('utf-8')
            
            file_info = {
                "url": url,
                "size": len(content),
                "lines": len(beautified_content.splitlines()),
                "original_path": paths["original_path"],
                "beautified_path": paths["beautified_path"],
            }
            
            # Case 1: File is completely new
            if not existing_entry:
                status = "NEW"
                paths["original_path"].write_bytes(content)
                paths["beautified_path"].write_text(beautified_content, encoding='utf-8')
            
            # Case 2: File is unchanged
            elif existing_entry['hash'] == new_hash:
                return "UNCHANGED", {}
                
            # Case 3: File has been modified
            else:
                status = "MODIFIED"
                old_beautified_path = Path(existing_entry.get("beautified_path", paths["beautified_path"]))
                
                old_content = ""
                if old_beautified_path.exists():
                    old_content = old_beautified_path.read_text(encoding='utf-8')

                diff, added, removed = self._generate_diff(old_content, beautified_content)
                file_info.update({"diff": diff, "added": added, "removed": removed})
                
                # Overwrite old files with new content
                paths["original_path"].write_bytes(content)
                paths["beautified_path"].write_text(beautified_content, encoding='utf-8')

            # Update hash database for NEW or MODIFIED files
            hashes[url] = {
                "hash": new_hash,
                "timestamp": log.get_timestamp(),
                "size": file_info['size'],
                "lines": file_info['lines'],
                "beautified_path": str(paths["beautified_path"]),
            }
            self._save_hashes(paths["hashes_path"], hashes)

            return status, file_info

        except Exception as e:
            log.error(f"Error in FileManager for {url}: {e}", exc_info=True)
            return "ERROR", {}

