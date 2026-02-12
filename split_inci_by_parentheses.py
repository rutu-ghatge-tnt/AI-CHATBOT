"""
Script to split Excel file based on whether INCI names contain parentheses.
Creates two separate files:
1. INCI names WITH parentheses (for review)
2. INCI names WITHOUT parentheses
"""

import pandas as pd
from pathlib import Path

# File paths
input_file = Path("Branded_Cosmetic_Ingredients_INCI_Mapped_MDB.xlsx")
output_with_parentheses = Path("Branded_Cosmetic_Ingredients_INCI_Mapped_MDB_WITH_PARENTHESES.xlsx")
output_without_parentheses = Path("Branded_Cosmetic_Ingredients_INCI_Mapped_MDB_WITHOUT_PARENTHESES.xlsx")

# Read the Excel file
print(f"Reading {input_file}...")
df = pd.read_excel(input_file)

print(f"Total rows: {len(df)}")
print(f"Columns: {list(df.columns)}")

# Check which column contains INCI names
inci_column = "INCI Name"
if inci_column not in df.columns:
    print(f"Error: Column '{inci_column}' not found!")
    print(f"Available columns: {list(df.columns)}")
    exit(1)

# Convert INCI Name to string and handle NaN values
df[inci_column] = df[inci_column].astype(str)

# Split based on parentheses
# Check if INCI name contains '(' or ')'
has_parentheses = df[inci_column].str.contains(r'[()]', na=False, regex=True)

df_with_parentheses = df[has_parentheses].copy()
df_without_parentheses = df[~has_parentheses].copy()

# Save the two files
print(f"\nSaving files...")
print(f"Rows WITH parentheses: {len(df_with_parentheses)}")
print(f"Rows WITHOUT parentheses: {len(df_without_parentheses)}")

df_with_parentheses.to_excel(output_with_parentheses, index=False)
df_without_parentheses.to_excel(output_without_parentheses, index=False)

print(f"\nCreated {output_with_parentheses}")
print(f"Created {output_without_parentheses}")
print(f"\nYou can now review the file with parentheses and merge it back later.")

