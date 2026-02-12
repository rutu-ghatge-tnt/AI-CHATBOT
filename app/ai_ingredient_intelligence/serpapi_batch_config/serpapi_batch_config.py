"""
SerpAPI Batch Configuration Loader
===================================

Loads the JSON configuration file for monthly batch processing.
The actual JSON should be in serpapi_batch_config.json in this directory.
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional

# Path to config file
CONFIG_DIR = Path(__file__).parent
CONFIG_FILE = CONFIG_DIR / "serpapi_batch_config.json"

# Cache for loaded config
_config_cache: Optional[Dict[str, Any]] = None


def load_config() -> Dict[str, Any]:
    """
    Load the SerpAPI batch configuration from JSON file.
    
    Returns:
        Dictionary containing the full configuration
        
    Raises:
        FileNotFoundError: If config file doesn't exist
        json.JSONDecodeError: If JSON is invalid
    """
    global _config_cache
    
    if _config_cache is not None:
        return _config_cache
    
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(
            f"Config file not found: {CONFIG_FILE}\n"
            f"Please create the file and paste the JSON configuration."
        )
    
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        _config_cache = json.load(f)
    
    return _config_cache


def get_config() -> Dict[str, Any]:
    """Get cached config or load it if not cached."""
    return load_config()


def reload_config() -> Dict[str, Any]:
    """Force reload the config from file."""
    global _config_cache
    _config_cache = None
    return load_config()

