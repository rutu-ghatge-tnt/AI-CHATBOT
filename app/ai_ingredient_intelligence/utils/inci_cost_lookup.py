"""
INCI Cost Lookup Utility
========================

Loads and queries the combined Excel file for ingredient costs.
Used by Make a Wish costing system to get actual ingredient prices.
"""

import pandas as pd
from pathlib import Path
from typing import Optional, Dict, List
import re

# Path to the combined Excel file
EXCEL_FILE_PATH = Path(__file__).parent.parent.parent.parent / "Branded_Cosmetic_Ingredients_INCI_Mapped_MDB_COMBINED.xlsx"

# Cache for loaded data
_cost_data_cache: Optional[pd.DataFrame] = None


def load_cost_data() -> pd.DataFrame:
    """Load the Excel file and cache it."""
    global _cost_data_cache
    
    if _cost_data_cache is not None:
        return _cost_data_cache
    
    if not EXCEL_FILE_PATH.exists():
        raise FileNotFoundError(
            f"Cost data file not found: {EXCEL_FILE_PATH}\n"
            "Please ensure Branded_Cosmetic_Ingredients_INCI_Mapped_MDB_COMBINED.xlsx exists in the project root."
        )
    
    try:
        df = pd.read_excel(EXCEL_FILE_PATH)
        # Normalize column names (handle spaces, case)
        df.columns = df.columns.str.strip()
        
        # Ensure required columns exist
        required_cols = ['INCI Name', 'Avg Cost']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")
        
        # Clean data
        df = df.dropna(subset=['INCI Name'])  # Remove rows without INCI names
        df['INCI Name'] = df['INCI Name'].astype(str).str.strip()
        
        # Handle Avg Cost - convert to float, handle missing values
        df['Avg Cost'] = pd.to_numeric(df['Avg Cost'], errors='coerce')
        df = df.dropna(subset=['Avg Cost'])  # Remove rows without cost
        
        _cost_data_cache = df
        print(f"Loaded {len(df)} ingredient cost records from Excel file")
        return df
    
    except Exception as e:
        raise RuntimeError(f"Error loading cost data from Excel: {e}")


def normalize_inci_name(inci: str) -> str:
    """Normalize INCI name for matching (lowercase, remove extra spaces)."""
    if not inci or pd.isna(inci):
        return ""
    return re.sub(r'\s+', ' ', str(inci).strip().lower())


def lookup_cost_by_inci(inci_name: str, exact_match: bool = False) -> Optional[Dict]:
    """
    Look up cost for an ingredient by INCI name.
    
    Args:
        inci_name: The INCI name to search for
        exact_match: If True, requires exact match. If False, does fuzzy matching.
    
    Returns:
        Dict with keys: 'inci_name', 'branded_ingredient', 'avg_cost', 'primary_supplier'
        or None if not found
    """
    if not inci_name or not inci_name.strip():
        return None
    
    try:
        df = load_cost_data()
        inci_normalized = normalize_inci_name(inci_name)
        
        if exact_match:
            # Exact match (case-insensitive)
            matches = df[df['INCI Name'].str.lower().str.strip() == inci_normalized]
        else:
            # Fuzzy match - check if INCI name contains the search term
            matches = df[
                df['INCI Name'].str.lower().str.strip().str.contains(inci_normalized, na=False, regex=False)
            ]
        
        if len(matches) == 0:
            return None
        
        # If multiple matches, prefer exact match or take first
        if len(matches) > 1:
            exact = matches[matches['INCI Name'].str.lower().str.strip() == inci_normalized]
            if len(exact) > 0:
                matches = exact
        
        # Get first match
        row = matches.iloc[0]
        
        return {
            'inci_name': row['INCI Name'],
            'branded_ingredient': row.get('Branded Ingredient', ''),
            'avg_cost': float(row['Avg Cost']),
            'primary_supplier': row.get('Primary Supplier', '')
        }
    
    except Exception as e:
        print(f"Error looking up cost for {inci_name}: {e}")
        return None


def lookup_multiple_costs(inci_names: List[str]) -> Dict[str, Optional[Dict]]:
    """
    Look up costs for multiple INCI names at once.
    
    Returns:
        Dict mapping INCI name to cost data (or None if not found)
    """
    results = {}
    for inci in inci_names:
        results[inci] = lookup_cost_by_inci(inci)
    return results


def get_cost_reference_table_from_excel() -> str:
    """
    Generate a cost reference table string from the Excel data
    to be included in AI prompts.
    
    Returns:
        Formatted string with ingredient costs from Excel
    """
    try:
        df = load_cost_data()
        
        # Group by INCI name and get average cost (in case of duplicates)
        cost_summary = df.groupby('INCI Name')['Avg Cost'].agg(['mean', 'min', 'max', 'count']).reset_index()
        cost_summary.columns = ['INCI Name', 'Avg Cost', 'Min Cost', 'Max Cost', 'Count']
        
        # Sort by cost
        cost_summary = cost_summary.sort_values('Avg Cost')
        
        # Format as markdown table
        lines = [
            "## INGREDIENT COST REFERENCE FROM DATABASE",
            "",
            "The following costs are from the actual ingredient database (Branded_Cosmetic_Ingredients_INCI_Mapped_MDB_COMBINED.xlsx).",
            "Use these EXACT costs when available. For ingredients not in this list, use the reference anchors below.",
            "",
            "| INCI Name | Avg Cost (₹/kg) | Min Cost | Max Cost | Count |",
            "|-----------|----------------|---------|---------|-------|"
        ]
        
        # Add top 100 most common ingredients (or all if less than 100)
        for _, row in cost_summary.head(100).iterrows():
            inci = row['INCI Name']
            avg = row['Avg Cost']
            min_cost = row['Min Cost']
            max_cost = row['Max Cost']
            count = int(row['Count'])
            
            lines.append(f"| {inci} | ₹{avg:.2f} | ₹{min_cost:.2f} | ₹{max_cost:.2f} | {count} |")
        
        lines.append("")
        lines.append(f"Total ingredients in database: {len(cost_summary)}")
        lines.append("")
        lines.append("**IMPORTANT:** When an ingredient is found in this database, use the exact cost from the database.")
        lines.append("Only use the reference anchors below for ingredients NOT in this database.")
        
        return "\n".join(lines)
    
    except Exception as e:
        print(f"Error generating cost reference table: {e}")
        return ""


def clear_cache():
    """Clear the cached cost data (useful for testing or reloading)."""
    global _cost_data_cache
    _cost_data_cache = None

