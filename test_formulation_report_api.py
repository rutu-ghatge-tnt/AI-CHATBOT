#!/usr/bin/env python3
"""
Test script for Formulation Report API
Tests the fix for the cache_control error
"""

import requests
import json
import sys
from typing import Optional

# Configuration
BASE_URL = "http://127.0.0.1:8000"
API_BASE = f"{BASE_URL}/api"

def get_auth_token() -> Optional[str]:
    """Get JWT token for authentication"""
    print("🔑 Getting authentication token...")
    
    try:
        # Login to get token
        login_url = f"{API_BASE}/auth/login"
        login_data = {
            "user_id": "test_user",
            "email": "test@example.com"
        }
        
        response = requests.post(login_url, json=login_data)
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            print(f"✅ Authentication successful")
            print(f"   Token: {token[:30]}... (length: {len(token)})")
            return token
        else:
            print(f"❌ Login failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return None
            
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to server. Make sure the FastAPI server is running on localhost:8000")
        return None
    except Exception as e:
        print(f"❌ Error getting token: {e}")
        return None

def test_formulation_report_api(token: str) -> bool:
    """Test the formulation report API endpoint"""
    print("\n" + "="*80)
    print("🧪 Testing Formulation Report API")
    print("="*80)
    
    # Test payload
    test_payload = {
        "inciList": [
            "Aqua",
            "Glycerin",
            "Niacinamide",
            "Hyaluronic Acid",
            "Salicylic Acid"
        ],
        "brandedIngredients": [],
        "notBrandedIngredients": [],
        "bisCautions": None,
        "expectedBenefits": None
    }
    
    print(f"\n📤 Sending request to /api/formulation-report")
    print(f"   Ingredients: {', '.join(test_payload['inciList'])}")
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    try:
        response = requests.post(
            f"{API_BASE}/formulation-report",
            json=test_payload,
            headers=headers,
            timeout=120  # 2 minutes timeout for report generation
        )
        
        print(f"\n📥 Response Status: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ API call successful!")
            print(f"   Response length: {len(response.text)} characters")
            
            # Check if response is HTML (formulation-report returns HTML)
            if response.text.strip().startswith("<!DOCTYPE") or response.text.strip().startswith("<html"):
                print("   Response type: HTML report")
                # Check for key sections
                if "Executive Summary" in response.text:
                    print("   ✅ Executive Summary found")
                if "Submitted INCI List" in response.text:
                    print("   ✅ INCI List found")
                if "Analysis" in response.text:
                    print("   ✅ Analysis section found")
            else:
                print(f"   Response preview: {response.text[:200]}...")
            
            return True
            
        elif response.status_code == 500:
            error_detail = response.text
            print(f"❌ Server Error (500)")
            print(f"   Error detail: {error_detail[:500]}")
            
            # Check specifically for cache_control error
            if "cache_control" in error_detail.lower() or "unexpected keyword argument" in error_detail.lower():
                print("\n   ⚠️  CACHE_CONTROL ERROR DETECTED!")
                print("   The fix may not be working correctly.")
                return False
            else:
                print("\n   ℹ️  Different error (not cache_control related)")
                return False
                
        elif response.status_code == 401:
            print("❌ Authentication failed")
            print("   Token may be invalid or expired")
            return False
            
        else:
            print(f"❌ Unexpected status code: {response.status_code}")
            print(f"   Response: {response.text[:500]}")
            return False
            
    except requests.exceptions.Timeout:
        print("❌ Request timed out (took longer than 2 minutes)")
        return False
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to server")
        return False
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")
        return False

def test_formulation_report_json_api(token: str) -> bool:
    """Test the formulation report JSON API endpoint"""
    print("\n" + "="*80)
    print("🧪 Testing Formulation Report JSON API")
    print("="*80)
    
    # Test payload
    test_payload = {
        "inciList": [
            "Aqua",
            "Glycerin",
            "Niacinamide"
        ],
        "brandedIngredients": [],
        "notBrandedIngredients": [],
        "bisCautions": None,
        "expectedBenefits": None
    }
    
    print(f"\n📤 Sending request to /api/formulation-report-json")
    print(f"   Ingredients: {', '.join(test_payload['inciList'])}")
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    try:
        response = requests.post(
            f"{API_BASE}/formulation-report-json",
            json=test_payload,
            headers=headers,
            timeout=120  # 2 minutes timeout
        )
        
        print(f"\n📥 Response Status: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ API call successful!")
            data = response.json()
            print(f"   Response type: JSON")
            
            # Check for key fields
            if "inci_list" in data:
                print(f"   ✅ INCI list found ({len(data['inci_list'])} ingredients)")
            if "analysis_table" in data:
                print(f"   ✅ Analysis table found")
            if "compliance_panel" in data:
                print(f"   ✅ Compliance panel found")
            
            return True
            
        elif response.status_code == 500:
            error_detail = response.text
            print(f"❌ Server Error (500)")
            print(f"   Error detail: {error_detail[:500]}")
            
            # Check specifically for cache_control error
            if "cache_control" in error_detail.lower() or "unexpected keyword argument" in error_detail.lower():
                print("\n   ⚠️  CACHE_CONTROL ERROR DETECTED!")
                print("   The fix may not be working correctly.")
                return False
            else:
                print("\n   ℹ️  Different error (not cache_control related)")
                return False
                
        elif response.status_code == 401:
            print("❌ Authentication failed")
            return False
            
        else:
            print(f"❌ Unexpected status code: {response.status_code}")
            print(f"   Response: {response.text[:500]}")
            return False
            
    except requests.exceptions.Timeout:
        print("❌ Request timed out")
        return False
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to server")
        return False
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")
        return False

def main():
    """Main test function"""
    print("="*80)
    print("🧪 FORMULATION REPORT API TEST")
    print("Testing fix for cache_control error")
    print("="*80)
    
    # Step 1: Get authentication token
    token = get_auth_token()
    if not token:
        print("\n❌ Cannot proceed without authentication token")
        sys.exit(1)
    
    # Step 2: Test formulation-report endpoint
    test1_passed = test_formulation_report_api(token)
    
    # Step 3: Test formulation-report-json endpoint
    test2_passed = test_formulation_report_json_api(token)
    
    # Summary
    print("\n" + "="*80)
    print("📊 TEST SUMMARY")
    print("="*80)
    print(f"   Formulation Report API:      {'✅ PASSED' if test1_passed else '❌ FAILED'}")
    print(f"   Formulation Report JSON API: {'✅ PASSED' if test2_passed else '❌ FAILED'}")
    
    if test1_passed and test2_passed:
        print("\n✅ All tests passed! The cache_control fix is working correctly.")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed. Check the error messages above.")
        sys.exit(1)

if __name__ == "__main__":
    main()

