"""
Script to merge the cleaned INCI names file with the file without parentheses
to create a complete combined list.
"""

import pandas as pd
from pathlib import Path

# File paths
cleaned_file = Path("Cleaned_INCI_Names.xlsx")
without_parentheses_file = Path("Branded_Cosmetic_Ingredients_INCI_Mapped_MDB_WITHOUT_PARENTHESES.xlsx")
output_file = Path("Branded_Cosmetic_Ingredients_INCI_Mapped_MDB_COMBINED.xlsx")

# Read both files
print(f"Reading {cleaned_file}...")
df_cleaned = pd.read_excel(cleaned_file)

print(f"Reading {without_parentheses_file}...")
df_without = pd.read_excel(without_parentheses_file)

print(f"\nCleaned file: {len(df_cleaned)} rows")
print(f"Without parentheses file: {len(df_without)} rows")

# Check if cleaned file has "Cleaned INCI Name" column and rename it to "INCI Name"
if "Cleaned INCI Name" in df_cleaned.columns:
    df_cleaned = df_cleaned.rename(columns={"Cleaned INCI Name": "INCI Name"})
    print("Renamed 'Cleaned INCI Name' to 'INCI Name' in cleaned file")

# Ensure both files have the same column order
expected_columns = ['Branded Ingredient', 'INCI Name', 'Avg Cost', 'Primary Supplier']
df_cleaned = df_cleaned[expected_columns]
df_without = df_without[expected_columns]

# Merge the two dataframes
print("\nMerging files...")
df_combined = pd.concat([df_cleaned, df_without], ignore_index=True)

print(f"Combined total: {len(df_combined)} rows")

# Save the combined file
print(f"\nSaving combined file to {output_file}...")
df_combined.to_excel(output_file, index=False)

print(f"Successfully created {output_file}")
print(f"\nSummary:")
print(f"  - Entries from cleaned file (with parentheses): {len(df_cleaned)}")
print(f"  - Entries from without parentheses file: {len(df_without)}")
print(f"  - Total combined entries: {len(df_combined)}")

