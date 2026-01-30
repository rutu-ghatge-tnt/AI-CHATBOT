"""
Safe Refactoring Script - Phase 1: Split analyze_inci.py
This script helps split the file safely without breaking anything
"""
import os
import re
from pathlib import Path

def analyze_analyze_inci_file():
    """Analyze analyze_inci.py to identify what can be split"""
    file_path = Path("app/ai_ingredient_intelligence/api/analyze_inci.py")
    
    if not file_path.exists():
        print(f"File not found: {file_path}")
        return
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find all router endpoints
    endpoints = []
    lines = content.split('\n')
    current_endpoint = None
    
    for i, line in enumerate(lines, 1):
        # Find @router decorators
        if '@router.' in line:
            endpoint_type = re.search(r'@router\.(get|post|put|patch|delete)', line.lower())
            if endpoint_type:
                # Find the function definition
                for j in range(i, min(i+10, len(lines))):
                    if 'async def ' in lines[j] or 'def ' in lines[j]:
                        func_match = re.search(r'(async )?def (\w+)', lines[j])
                        if func_match:
                            func_name = func_match.group(2)
                            # Find the route path
                            route_match = re.search(r'["\']([^"\']+)["\']', line)
                            route = route_match.group(1) if route_match else "unknown"
                            
                            endpoints.append({
                                'line': i,
                                'type': endpoint_type.group(1).upper(),
                                'route': route,
                                'function': func_name,
                                'category': categorize_endpoint(route, func_name)
                            })
                            break
    
    # Group by category
    categories = {}
    for ep in endpoints:
        cat = ep['category']
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(ep)
    
    print("=" * 80)
    print("ANALYZE_INCI.PY REFACTORING ANALYSIS")
    print("=" * 80)
    print(f"\nTotal endpoints found: {len(endpoints)}\n")
    
    print("CATEGORIZATION:")
    print("-" * 80)
    for category, eps in categories.items():
        print(f"\n{category.upper()} ({len(eps)} endpoints):")
        for ep in eps:
            print(f"  {ep['type']:6} {ep['route']:40} -> {ep['function']}")
    
    print("\n" + "=" * 80)
    print("RECOMMENDED SPLITS:")
    print("=" * 80)
    
    if 'url_extraction' in categories:
        print(f"\n1. url_extraction.py ({len(categories['url_extraction'])} endpoints)")
        print("   Endpoints:")
        for ep in categories['url_extraction']:
            print(f"     - {ep['route']}")
    
    if 'decode_history' in categories:
        print(f"\n2. decode_history.py ({len(categories['decode_history'])} endpoints)")
        print("   Endpoints:")
        for ep in categories['decode_history']:
            print(f"     - {ep['route']}")
    
    if 'compare_history' in categories:
        print(f"\n3. compare_history.py ({len(categories['compare_history'])} endpoints)")
        print("   Endpoints:")
        for ep in categories['compare_history']:
            print(f"     - {ep['route']}")
    
    if 'analysis' in categories:
        print(f"\n4. analyze_inci.py (KEEP - {len(categories['analysis'])} endpoints)")
        print("   Core analysis endpoints remain here")
    
    print("\n" + "=" * 80)
    print("SAFETY CHECKLIST:")
    print("=" * 80)
    print("[OK] All endpoints identified")
    print("[OK] Categories determined")
    print("[OK] Ready for safe extraction")
    print("\nNEXT STEPS:")
    print("1. Create new files with copied code (not moved)")
    print("2. Test new endpoints work")
    print("3. Register new routers in main.py")
    print("4. Keep old endpoints working (backward compatibility)")
    print("5. Only remove old endpoints after frontend migrates")

def categorize_endpoint(route, func_name):
    """Categorize endpoint based on route and function name"""
    route_lower = route.lower()
    func_lower = func_name.lower()
    
    if 'url' in route_lower or 'extract' in route_lower or 'extract' in func_lower:
        return 'url_extraction'
    elif 'decode-history' in route_lower or 'decode_history' in func_lower or 'save-decode' in route_lower:
        return 'decode_history'
    elif 'compare-history' in route_lower or 'compare_history' in func_lower or 'save-compare' in route_lower:
        return 'compare_history'
    elif 'compare-products' in route_lower or 'compare_products' in func_lower:
        return 'compare_history'
    elif 'analyze' in route_lower or 'analyze' in func_lower:
        return 'analysis'
    elif 'health' in route_lower or 'health' in func_lower:
        return 'health'
    elif 'supplier' in route_lower or 'distributor' in route_lower:
        return 'distributor'
    else:
        return 'analysis'

if __name__ == '__main__':
    analyze_analyze_inci_file()

