"""
Prompt Cache Manager for Claude API
=====================================

This module implements system prompt caching using Claude's cache_control API
to reduce costs and latency. System prompts are cached and reused across requests.

COST SAVINGS:
- Writing to cache: 25% more expensive than base input tokens
- Reading from cache: Only 10% of base input token price
- For long system prompts (1000+ tokens), this saves ~90% on system prompt costs

USAGE:
    cache_manager = PromptCacheManager()
    cache_block_id = await cache_manager.get_or_create_cache(
        prompt_type="ingredient_selection",
        system_prompt=INGREDIENT_SELECTION_SYSTEM_PROMPT
    )
    
    # Use cache_block_id in API calls
"""

import os
import hashlib
import json
from typing import Dict, Optional, Any, Union
from datetime import datetime, timedelta

# In-memory cache store (can be replaced with Redis/database for production)
# Format: {prompt_hash: {"cache_block_id": "...", "created_at": "...", "ttl": 3600}}
_cache_store: Dict[str, Dict[str, Any]] = {}

# Cache TTL in seconds (24 hours default)
CACHE_TTL = 86400


class PromptCacheManager:
    """
    Manages Claude API prompt caching for system prompts.
    
    Each system prompt is cached once and reused across all requests,
    dramatically reducing token costs for the system prompt portion.
    """
    
    def __init__(self, claude_client=None):
        """
        Initialize the cache manager.
        
        Args:
            claude_client: Anthropic client instance (optional, will use global if not provided)
        """
        self.claude_client = claude_client
        self._cache_store = _cache_store
    
    def _get_prompt_hash(self, prompt: str) -> str:
        """
        Generate a hash for the prompt to use as cache key.
        
        Args:
            prompt: The system prompt text
            
        Returns:
            SHA256 hash of the prompt
        """
        return hashlib.sha256(prompt.encode('utf-8')).hexdigest()
    
    def _get_cache_key(self, prompt_type: str, prompt: str) -> str:
        """
        Generate a cache key combining prompt type and hash.
        
        Args:
            prompt_type: Type of prompt (e.g., "ingredient_selection")
            prompt: The system prompt text
            
        Returns:
            Combined cache key
        """
        prompt_hash = self._get_prompt_hash(prompt)
        return f"{prompt_type}:{prompt_hash}"
    
    def should_use_cache(self, prompt_type: str, system_prompt: str) -> bool:
        """
        Check if we should use caching for this prompt.
        
        Args:
            prompt_type: Type of prompt (e.g., "ingredient_selection", "optimization")
            system_prompt: The system prompt to check
            
        Returns:
            True if caching should be used, False otherwise
        """
        cache_key = self._get_cache_key(prompt_type, system_prompt)
        cached_entry = self._cache_store.get(cache_key)
        
        if cached_entry:
            created_at = datetime.fromisoformat(cached_entry['created_at'])
            age = (datetime.now() - created_at).total_seconds()
            
            if age < cached_entry.get('ttl', CACHE_TTL):
                # Cache is still valid
                return True
            else:
                # Cache expired, remove it
                del self._cache_store[cache_key]
        
        return False
    
    def get_cache_control_config(
        self,
        prompt_type: str,
        system_prompt: str,
        ttl: str = "1h"
    ) -> Optional[Dict[str, str]]:
        """
        Get cache_control configuration for Claude API.
        
        DEPRECATED: Use format_system_prompt_with_cache() instead for proper GA implementation.
        This method is kept for backward compatibility but returns cache_control dict
        that should be applied to content blocks, not as a top-level parameter.
        
        Args:
            prompt_type: Type of prompt (e.g., "ingredient_selection", "optimization")
            system_prompt: The system prompt to cache
            ttl: Time-to-live for cache (default: "1h" for 1 hour)
            
        Returns:
            cache_control dict with {"type": "ephemeral", "ttl": ttl}, or None if caching disabled
        """
        cache_key = self._get_cache_key(prompt_type, system_prompt)
        
        # Check if we have a valid cached entry
        cached_entry = self._cache_store.get(cache_key)
        if cached_entry:
            created_at = datetime.fromisoformat(cached_entry['created_at'])
            age = (datetime.now() - created_at).total_seconds()
            
            if age < cached_entry.get('ttl', CACHE_TTL):
                # Cache is still valid - Claude will use cached version
                print(f"✅ Cache HIT for {prompt_type} (age: {age:.0f}s) - using cached system prompt")
                return {"type": "ephemeral", "ttl": ttl}
            else:
                # Cache expired, remove it
                print(f"⏰ Cache EXPIRED for {prompt_type} (age: {age:.0f}s)")
                del self._cache_store[cache_key]
        
        # No valid cache, create new cache entry
        try:
            print(f"📝 Setting up cache for {prompt_type} (will cache for {ttl})...")
            
            # Store cache metadata
            cache_block_id = self._get_prompt_hash(system_prompt)
            
            self._cache_store[cache_key] = {
                "cache_block_id": cache_block_id,
                "created_at": datetime.now().isoformat(),
                "ttl": CACHE_TTL,
                "prompt_type": prompt_type,
                "system_prompt": system_prompt  # Store for reference
            }
            
            print(f"✅ Cache configured for {prompt_type} - first call will write to cache")
            return {"type": "ephemeral", "ttl": ttl}
            
        except Exception as e:
            print(f"⚠️ Failed to configure cache for {prompt_type}: {e}")
            # Return None to fall back to regular API call
            return None
    
    def format_system_prompt_with_cache(
        self,
        prompt_type: str,
        system_prompt: str,
        ttl: str = "1h"
    ) -> Union[str, list]:
        """
        Format system prompt as content blocks with cache_control for Claude API (GA).
        
        Prompt caching is now Generally Available. This method formats the system prompt
        as content blocks with cache_control, which is the correct way to use caching
        with SDK 0.34.0+.
        
        Args:
            prompt_type: Type of prompt (e.g., "ingredient_selection", "optimization")
            system_prompt: The system prompt to cache (can be string or already formatted)
            ttl: Time-to-live for cache (default: "1h" for 1 hour)
            
        Returns:
            If caching is enabled: List of content blocks with cache_control on the text block
            If caching is disabled: Original system_prompt string
        """
        cache_key = self._get_cache_key(prompt_type, system_prompt)
        
        # Check if we have a valid cached entry
        cached_entry = self._cache_store.get(cache_key)
        if cached_entry:
            created_at = datetime.fromisoformat(cached_entry['created_at'])
            age = (datetime.now() - created_at).total_seconds()
            
            if age < cached_entry.get('ttl', CACHE_TTL):
                # Cache is still valid - Claude will use cached version
                print(f"✅ Cache HIT for {prompt_type} (age: {age:.0f}s) - using cached system prompt")
                cache_control = {"type": "ephemeral", "ttl": ttl}
            else:
                # Cache expired, remove it
                print(f"⏰ Cache EXPIRED for {prompt_type} (age: {age:.0f}s)")
                del self._cache_store[cache_key]
                cache_control = None
        else:
            cache_control = None
        
        # If no valid cache, create new cache entry
        if not cache_control:
            try:
                print(f"📝 Setting up cache for {prompt_type} (will cache for {ttl})...")
                
                # Store cache metadata
                cache_block_id = self._get_prompt_hash(system_prompt)
                
                self._cache_store[cache_key] = {
                    "cache_block_id": cache_block_id,
                    "created_at": datetime.now().isoformat(),
                    "ttl": CACHE_TTL,
                    "prompt_type": prompt_type,
                    "system_prompt": system_prompt
                }
                
                cache_control = {"type": "ephemeral", "ttl": ttl}
                print(f"✅ Cache configured for {prompt_type} - first call will write to cache")
            except Exception as e:
                print(f"⚠️ Failed to configure cache for {prompt_type}: {e}")
                # Return original string if caching fails
                return system_prompt
        
        # Format system prompt as content blocks with cache_control
        # This is the GA (Generally Available) approach - cache_control goes in content blocks
        return [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": cache_control
            }
        ]
    
    async def get_or_create_cache(
        self,
        prompt_type: str,
        system_prompt: str,
        claude_client=None
    ) -> Optional[str]:
        """
        Get existing cache block ID or create a new one.
        
        DEPRECATED: Use get_cache_control_config() instead for proper Claude API integration.
        This method is kept for backward compatibility.
        
        Args:
            prompt_type: Type of prompt (e.g., "ingredient_selection", "optimization")
            system_prompt: The system prompt to cache
            claude_client: Anthropic client (optional, uses instance client or global)
            
        Returns:
            Cache block ID string, or None if caching is not available
        """
        cache_control = self.get_cache_control_config(prompt_type, system_prompt)
        if cache_control:
            cache_key = self._get_cache_key(prompt_type, system_prompt)
            cached_entry = self._cache_store.get(cache_key)
            if cached_entry:
                return cached_entry.get('cache_block_id')
        return None
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get statistics about cache usage.
        
        Returns:
            Dictionary with cache statistics
        """
        total_entries = len(self._cache_store)
        valid_entries = 0
        expired_entries = 0
        
        now = datetime.now()
        for entry in self._cache_store.values():
            created_at = datetime.fromisoformat(entry['created_at'])
            age = (now - created_at).total_seconds()
            if age < entry.get('ttl', CACHE_TTL):
                valid_entries += 1
            else:
                expired_entries += 1
        
        return {
            "total_entries": total_entries,
            "valid_entries": valid_entries,
            "expired_entries": expired_entries,
            "cache_types": list(set(e.get('prompt_type', 'unknown') for e in self._cache_store.values()))
        }
    
    def clear_cache(self, prompt_type: Optional[str] = None):
        """
        Clear cache entries.
        
        Args:
            prompt_type: If provided, only clear entries for this type. Otherwise clear all.
        """
        if prompt_type:
            keys_to_remove = [
                key for key, entry in self._cache_store.items()
                if entry.get('prompt_type') == prompt_type
            ]
            for key in keys_to_remove:
                del self._cache_store[key]
            print(f"🗑️ Cleared {len(keys_to_remove)} cache entries for {prompt_type}")
        else:
            count = len(self._cache_store)
            self._cache_store.clear()
            print(f"🗑️ Cleared all {count} cache entries")


# Global cache manager instance
_cache_manager: Optional[PromptCacheManager] = None


def get_cache_manager(claude_client=None) -> PromptCacheManager:
    """
    Get or create the global cache manager instance.
    
    Args:
        claude_client: Anthropic client (optional)
        
    Returns:
        PromptCacheManager instance
    """
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = PromptCacheManager(claude_client=claude_client)
    return _cache_manager


def get_cache_control_for_prompt(
    system_prompt: Optional[str],
    prompt_type: str = "general",
    claude_client=None,
    ttl: str = "1h"
) -> Optional[Dict[str, str]]:
    """
    Helper function to get cache_control config for Claude API calls.
    
    DEPRECATED: Use format_system_prompt_with_cache() instead for proper GA implementation.
    This function is kept for backward compatibility.
    
    Args:
        system_prompt: The system prompt to cache (None if no system prompt)
        prompt_type: Type of prompt for tracking (e.g., "ingredient_selection", "url_extraction")
        claude_client: Anthropic client (optional)
        ttl: Cache time-to-live (default: "1h" for 1 hour)
        
    Returns:
        cache_control dict with {"type": "ephemeral", "ttl": ttl}, or None if no system prompt
    """
    if not system_prompt:
        return None
    
    cache_manager = get_cache_manager(claude_client)
    return cache_manager.get_cache_control_config(
        prompt_type=prompt_type,
        system_prompt=system_prompt,
        ttl=ttl
    )


def format_system_prompt_with_cache(
    system_prompt: Optional[str],
    prompt_type: str = "general",
    claude_client=None,
    ttl: str = "1h"
) -> Union[str, list]:
    """
    Helper function to format system prompt as content blocks with cache_control (GA).
    
    This is the recommended way to use prompt caching with SDK 0.34.0+.
    Prompt caching is now Generally Available and no longer requires beta headers.
    
    Args:
        system_prompt: The system prompt to cache (None if no system prompt)
        prompt_type: Type of prompt for tracking (e.g., "ingredient_selection", "url_extraction")
        claude_client: Anthropic client (optional)
        ttl: Cache time-to-live (default: "1h" for 1 hour)
        
    Returns:
        If caching is enabled: List of content blocks with cache_control
        If caching is disabled or no system prompt: Original system_prompt string
    """
    if not system_prompt:
        return system_prompt
    
    cache_manager = get_cache_manager(claude_client)
    return cache_manager.format_system_prompt_with_cache(
        prompt_type=prompt_type,
        system_prompt=system_prompt,
        ttl=ttl
    )

