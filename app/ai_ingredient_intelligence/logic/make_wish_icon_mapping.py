"""
Emoji to Heroicon/Lucide Icon Mapping for Make a Wish
=====================================================

This module provides mappings from emojis to heroicon/lucide icon names
for use in Make a Wish API responses.
"""

# Emoji to Icon Name Mapping
EMOJI_TO_ICON = {
    # Complexity icons
    "🌿": "leaf",  # Minimalist
    "⚖️": "scale",  # Classic
    "✨": "sparkles",  # Luxe
    
    # Ingredient icons
    "🍊": "citrus",  # Vitamin C variants
    "🍋": "lemon",  # Vitamin C variants
    "⚡": "bolt",  # Fast-acting
    "🌺": "flower",  # Natural extracts
    "👑": "crown",  # Gold standard
    "🌿": "leaf",  # Natural
    "🚀": "rocket",  # Advanced
    "🌱": "sprout",  # Ayurvedic
    "💎": "gem",  # Premium
    "🎯": "target",  # Targeted
    "💧": "droplet",  # Hydration
    "🔬": "microscope",  # Scientific
    "🛡️": "shield",  # Protection
    "🔷": "diamond",  # Peptides
    "🌟": "star",  # Special
    
    # Product type icons
    "🧪": "flask",  # Serum/Testing
    
    # Status/action icons
    "💡": "lightbulb",  # Insights
    "⚠️": "alert-triangle",  # Warnings
    "✅": "check-circle",  # Success/Allowed
    "❌": "x-circle",  # Error
    "💬": "message-circle",  # Consultation
    "📋": "clipboard",  # Documentation
    "🏭": "factory",  # Manufacturing
    "📊": "bar-chart",  # Analysis
    "📈": "arrow-trending-up",  # Cost factors / growth
    "💾": "save",  # Save
    "📝": "file-text",  # Notes
    "🔍": "search",  # Search
    "🚀": "rocket",  # Start
    "📋": "clipboard-list",  # Stage 1
    "🔧": "wrench",  # Stage 2
    "🏭": "factory",  # Stage 3
    "💰": "dollar-sign",  # Stage 4
    "🎉": "party-popper",  # Complete
}

# Reverse mapping for backward compatibility
ICON_TO_EMOJI = {v: k for k, v in EMOJI_TO_ICON.items()}

def emoji_to_icon(emoji: str, default: str = "circle") -> str:
    """
    Convert emoji to heroicon/lucide icon name.
    
    Args:
        emoji: Emoji string
        default: Default icon name if emoji not found
        
    Returns:
        Icon name (heroicon/lucide compatible)
    """
    return EMOJI_TO_ICON.get(emoji, default)

def icon_to_emoji(icon: str) -> str:
    """
    Convert icon name back to emoji (for backward compatibility).
    
    Args:
        icon: Icon name
        
    Returns:
        Emoji string
    """
    return ICON_TO_EMOJI.get(icon, "✨")

def replace_emoji_in_dict(data: dict, emoji_key: str = "emoji", icon_key: str = "icon") -> dict:
    """
    Replace emoji field with icon field in a dictionary.
    
    Args:
        data: Dictionary that may contain emoji field
        emoji_key: Key name for emoji field (default: "emoji")
        icon_key: Key name for icon field (default: "icon")
        
    Returns:
        Dictionary with icon field instead of emoji
    """
    if isinstance(data, dict):
        result = data.copy()
        if emoji_key in result:
            emoji_value = result.pop(emoji_key)
            result[icon_key] = emoji_to_icon(emoji_value)
        # Recursively process nested dictionaries and lists
        for key, value in result.items():
            if isinstance(value, dict):
                result[key] = replace_emoji_in_dict(value, emoji_key, icon_key)
            elif isinstance(value, list):
                result[key] = [replace_emoji_in_dict(item, emoji_key, icon_key) if isinstance(item, dict) else item for item in value]
        return result
    return data


def replace_icon_emoji_values(data, icon_key: str = "icon", default_icon: str = "circle"):
    """
    Recursively replace any "icon" key whose value is an emoji with heroicon/lucide name.
    Used for basic_mode_result so responses use icon names (like advanced mode) not emojis.
    If the value is already a known icon name, it is left unchanged.
    """
    if isinstance(data, dict):
        result = {}
        for k, v in data.items():
            if k == icon_key and isinstance(v, str):
                result[k] = EMOJI_TO_ICON.get(v, v)  # replace only known emojis; leave icon names as-is
            elif isinstance(v, dict):
                result[k] = replace_icon_emoji_values(v, icon_key, default_icon)
            elif isinstance(v, list):
                result[k] = [
                    replace_icon_emoji_values(i, icon_key, default_icon) if isinstance(i, dict) else i
                    for i in v
                ]
            else:
                result[k] = v
        return result
    return data

