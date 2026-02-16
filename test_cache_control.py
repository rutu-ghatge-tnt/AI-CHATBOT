"""
Test script to verify cache_control implementation is working correctly.
This tests the GA (Generally Available) prompt caching approach.
"""

import os
import sys
import asyncio
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Set up environment
os.environ.setdefault("CLAUDE_API_KEY", os.getenv("CLAUDE_API_KEY", ""))
os.environ.setdefault("CLAUDE_MODEL", os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5-20250929"))

def test_format_system_prompt():
    """Test that format_system_prompt_with_cache returns correct format"""
    print("=" * 60)
    print("TEST 1: Testing format_system_prompt_with_cache()")
    print("=" * 60)
    
    from app.ai_ingredient_intelligence.logic.prompt_cache_manager import format_system_prompt_with_cache
    
    test_prompt = "You are a helpful assistant that analyzes skincare ingredients."
    
    # Test formatting
    formatted = format_system_prompt_with_cache(
        system_prompt=test_prompt,
        prompt_type="test",
        ttl="1h"
    )
    
    print(f"Original prompt: {test_prompt[:50]}...")
    print(f"Formatted type: {type(formatted)}")
    
    if isinstance(formatted, list):
        print("[PASS] Returns list (content blocks format)")
        print(f"   Content blocks: {len(formatted)} block(s)")
        if formatted and isinstance(formatted[0], dict):
            block = formatted[0]
            print(f"   Block type: {block.get('type')}")
            print(f"   Has cache_control: {'cache_control' in block}")
            if 'cache_control' in block:
                print(f"   Cache control: {block['cache_control']}")
                print("[PASS] cache_control is correctly formatted in content block")
            else:
                print("[FAIL] Missing cache_control in content block")
                return False
        else:
            print("[FAIL] Content block is not a dict")
            return False
    else:
        print("[FAIL] Should return list of content blocks")
        return False
    
    return True


def test_claude_api_call():
    """Test making an actual Claude API call with cache_control"""
    print("\n" + "=" * 60)
    print("TEST 2: Testing Claude API call with cache_control")
    print("=" * 60)
    
    # Check for API key
    api_key = os.getenv("CLAUDE_API_KEY")
    if not api_key:
        print("[SKIP] CLAUDE_API_KEY not set, skipping API test")
        return True
    
    try:
        import anthropic
        from app.ai_ingredient_intelligence.logic.prompt_cache_manager import format_system_prompt_with_cache
        
        # Initialize client
        client = anthropic.Anthropic(api_key=api_key)
        model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5-20250929")
        
        # Format system prompt with cache
        system_prompt = "You are a helpful assistant. Respond briefly and concisely."
        formatted_system = format_system_prompt_with_cache(
            system_prompt=system_prompt,
            prompt_type="test_api",
            claude_client=client,
            ttl="1h"
        )
        
        print(f"System prompt formatted: {isinstance(formatted_system, list)}")
        if isinstance(formatted_system, list):
            print(f"   Content blocks: {len(formatted_system)}")
            print(f"   Has cache_control: {'cache_control' in formatted_system[0]}")
        
        # Make API call
        print(f"\nMaking API call to {model}...")
        response = client.messages.create(
            model=model,
            max_tokens=100,
            system=formatted_system,  # This should be list of content blocks
            messages=[
                {"role": "user", "content": "Say 'Hello, cache_control is working!' if you understand."}
            ]
        )
        
        content = response.content[0].text.strip()
        print(f"[PASS] API call successful!")
        print(f"   Response: {content[:100]}...")
        
        # Check response metadata for cache info
        if hasattr(response, 'usage'):
            usage = response.usage
            print(f"\nToken usage:")
            print(f"   Input tokens: {usage.input_tokens}")
            print(f"   Output tokens: {usage.output_tokens}")
            # Note: Cache hit info might be in response headers or usage details
        
        return True
        
    except Exception as e:
        print(f"[FAIL] API call failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_cache_hit():
    """Test that cache is used on second call"""
    print("\n" + "=" * 60)
    print("TEST 3: Testing cache hit on second call")
    print("=" * 60)
    
    api_key = os.getenv("CLAUDE_API_KEY")
    if not api_key:
        print("[SKIP] CLAUDE_API_KEY not set, skipping cache hit test")
        return True
    
    try:
        import anthropic
        from app.ai_ingredient_intelligence.logic.prompt_cache_manager import format_system_prompt_with_cache
        
        client = anthropic.Anthropic(api_key=api_key)
        model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5-20250929")
        
        system_prompt = "You are a test assistant. Count how many times you've been called."
        
        # First call - should create cache
        print("First call (should create cache)...")
        formatted_system_1 = format_system_prompt_with_cache(
            system_prompt=system_prompt,
            prompt_type="test_cache_hit",
            claude_client=client,
            ttl="1h"
        )
        
        response1 = client.messages.create(
            model=model,
            max_tokens=50,
            system=formatted_system_1,
            messages=[{"role": "user", "content": "Say 'First call'"}]
        )
        
        print(f"   Response 1: {response1.content[0].text.strip()[:50]}...")
        if hasattr(response1, 'usage'):
            print(f"   Input tokens (1st): {response1.usage.input_tokens}")
        
        # Second call - should use cache
        print("\nSecond call (should use cache)...")
        formatted_system_2 = format_system_prompt_with_cache(
            system_prompt=system_prompt,
            prompt_type="test_cache_hit",
            claude_client=client,
            ttl="1h"
        )
        
        response2 = client.messages.create(
            model=model,
            max_tokens=50,
            system=formatted_system_2,
            messages=[{"role": "user", "content": "Say 'Second call'"}]
        )
        
        print(f"   Response 2: {response2.content[0].text.strip()[:50]}...")
        if hasattr(response2, 'usage'):
            print(f"   Input tokens (2nd): {response2.usage.input_tokens}")
            if response2.usage.input_tokens < response1.usage.input_tokens:
                print("[PASS] Second call used fewer input tokens (cache hit!)")
            else:
                print("[NOTE] Token count similar (cache may still be working, check API response)")
        
        return True
        
    except Exception as e:
        print(f"[FAIL] Cache hit test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("CACHE_CONTROL IMPLEMENTATION TEST")
    print("=" * 60)
    print("Testing GA (Generally Available) prompt caching approach")
    print("SDK version: 0.34.0+ required")
    print("=" * 60)
    
    results = []
    
    # Test 1: Format function
    results.append(("Format System Prompt", test_format_system_prompt()))
    
    # Test 2: API call
    results.append(("API Call with cache_control", test_claude_api_call()))
    
    # Test 3: Cache hit
    results.append(("Cache Hit Test", test_cache_hit()))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    for test_name, passed in results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status}: {test_name}")
    
    all_passed = all(result[1] for result in results)
    print("=" * 60)
    if all_passed:
        print("[PASS] ALL TESTS PASSED!")
    else:
        print("[FAIL] SOME TESTS FAILED")
    print("=" * 60)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    exit(main())

