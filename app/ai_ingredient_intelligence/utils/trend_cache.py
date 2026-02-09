"""
Trend Cache Manager
===================

Caching layer for SerpAPI trend data to reduce API costs and improve performance.
Uses MongoDB for persistent caching.
"""

from typing import Optional, Any, Dict
from datetime import datetime, timedelta
import hashlib
import json

from app.ai_ingredient_intelligence.db.collections import trend_cache_col


class TrendCache:
    """Manages caching for trend analysis data"""
    
    # Cache TTL configuration (in seconds)
    TTL_CONFIG = {
        "trends_timeseries": 24 * 60 * 60,  # 24 hours
        "trends_regional": 7 * 24 * 60 * 60,  # 7 days
        "trends_related": 12 * 60 * 60,  # 12 hours
        "shopping_results": 6 * 60 * 60,  # 6 hours
        "paa_questions": 24 * 60 * 60,  # 24 hours
    }
    
    def _generate_key(self, cache_type: str, **kwargs) -> str:
        """Generate cache key from parameters"""
        # Sort kwargs for consistent key generation
        key_data = f"{cache_type}:{json.dumps(kwargs, sort_keys=True)}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    async def get(self, cache_type: str, **kwargs) -> Optional[Any]:
        """
        Get cached data if it exists and is not expired
        
        Args:
            cache_type: Type of cache (trends_timeseries, trends_regional, etc.)
            **kwargs: Parameters used to generate cache key
            
        Returns:
            Cached data or None if not found/expired
        """
        cache_key = self._generate_key(cache_type, **kwargs)
        ttl = self.TTL_CONFIG.get(cache_type, 3600)  # Default 1 hour
        
        try:
            cached_entry = await trend_cache_col.find_one({
                "cache_key": cache_key,
                "cache_type": cache_type,
                "expires_at": {"$gt": datetime.utcnow()}
            })
            
            if cached_entry:
                # Update access stats
                await trend_cache_col.update_one(
                    {"_id": cached_entry["_id"]},
                    {
                        "$inc": {"access_count": 1},
                        "$set": {"last_accessed": datetime.utcnow()}
                    }
                )
                return cached_entry.get("data")
            
            return None
        except Exception as e:
            print(f"Error getting cache for {cache_type}: {e}")
            return None
    
    async def set(self, cache_type: str, data: Any, **kwargs):
        """
        Store data in cache
        
        Args:
            cache_type: Type of cache
            data: Data to cache
            **kwargs: Parameters used to generate cache key
        """
        cache_key = self._generate_key(cache_type, **kwargs)
        ttl = self.TTL_CONFIG.get(cache_type, 3600)
        expires_at = datetime.utcnow() + timedelta(seconds=ttl)
        
        try:
            cache_entry = {
                "cache_key": cache_key,
                "cache_type": cache_type,
                "data": data,
                "cached_at": datetime.utcnow(),
                "expires_at": expires_at,
                "access_count": 0,
                "last_accessed": datetime.utcnow(),
                "params": kwargs
            }
            
            await trend_cache_col.replace_one(
                {"cache_key": cache_key, "cache_type": cache_type},
                cache_entry,
                upsert=True
            )
        except Exception as e:
            print(f"Error setting cache for {cache_type}: {e}")
    
    async def invalidate(self, cache_type: str, **kwargs):
        """Invalidate specific cache entry"""
        cache_key = self._generate_key(cache_type, **kwargs)
        try:
            await trend_cache_col.delete_one({
                "cache_key": cache_key,
                "cache_type": cache_type
            })
        except Exception as e:
            print(f"Error invalidating cache: {e}")
    
    async def clear_expired(self):
        """Clear all expired cache entries"""
        try:
            result = await trend_cache_col.delete_many({
                "expires_at": {"$lt": datetime.utcnow()}
            })
            return result.deleted_count
        except Exception as e:
            print(f"Error clearing expired cache: {e}")
            return 0

