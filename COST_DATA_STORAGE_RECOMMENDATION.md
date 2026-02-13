# Cost Data Storage: MongoDB vs Excel - Recommendation

## Recommendation: **Use MongoDB** ✅

Based on your existing infrastructure, I recommend migrating the cost data to MongoDB.

## Why MongoDB?

### 1. **Already Using MongoDB**
- You have MongoDB infrastructure set up
- You already store ingredient data in MongoDB (`branded_ingredients_col`, `distributor_col`, `inci_col`)
- Consistent with your existing architecture

### 2. **Better Performance**
- Indexed queries (much faster than Excel file I/O)
- Can query by INCI name, cost range, supplier, etc.
- Batch lookups are efficient
- No file I/O overhead

### 3. **Better Integration**
- Can merge with existing `distributor_col` pricing data
- Can link to `branded_ingredients_col` for richer data
- Single source of truth for all ingredient data

### 4. **Easier Updates**
- Update individual records without reloading entire file
- Can track update history
- Can add metadata (source, timestamp, version)

### 5. **Scalability**
- Handles concurrent access better
- Can add more fields later (min/max cost, cost history, etc.)
- Better for production use

## Implementation

### Step 1: Migrate Data to MongoDB

Run the migration script:

```bash
python -m app.ai_ingredient_intelligence.scripts.migrate_excel_costs_to_mongo
```

This will:
- Load the Excel file
- Create `ingredient_costs` collection
- Create indexes for fast lookups
- Insert/update all 4,201 ingredient records

### Step 2: Configuration

The system is already configured to use MongoDB by default. Check:

```python
# app/ai_ingredient_intelligence/logic/make_wish_prompts.py
USE_MONGODB_FOR_COSTS = True  # Set to False to use Excel instead
```

### Step 3: Verify

The system will automatically:
- Use MongoDB for cost lookups
- Include cost data in AI prompts
- Fall back to reference anchors for unknown ingredients

## Comparison

| Feature | Excel File | MongoDB |
|---------|-----------|---------|
| **Performance** | File I/O, slower | Indexed queries, fast |
| **Concurrent Access** | File locking issues | Handles concurrent access |
| **Updates** | Replace entire file | Update individual records |
| **Querying** | Limited | Rich query capabilities |
| **Integration** | Separate | Integrated with existing data |
| **Scalability** | Limited | Excellent |
| **Setup** | Simple | Requires migration |

## Migration Script

The migration script (`migrate_excel_costs_to_mongo.py`) will:
1. ✅ Load Excel file
2. ✅ Validate data
3. ✅ Create indexes
4. ✅ Insert/update records (upsert - won't duplicate)
5. ✅ Verify migration

## Usage After Migration

### Lookup Single Ingredient
```python
from app.ai_ingredient_intelligence.utils.inci_cost_lookup_mongo import lookup_cost_by_inci

cost_data = await lookup_cost_by_inci("Niacinamide")
# Returns: {'inci_name': 'Niacinamide', 'avg_cost': 2955.54, ...}
```

### Batch Lookup
```python
from app.ai_ingredient_intelligence.utils.inci_cost_lookup_mongo import lookup_multiple_costs

costs = await lookup_multiple_costs(["Niacinamide", "Glycerin", "Retinol"])
```

### Update Cost
```python
from app.ai_ingredient_intelligence.utils.inci_cost_lookup_mongo import update_cost

await update_cost("Niacinamide", 3000.0, source="distributor")
```

## Fallback Option

If you prefer to keep using Excel:
1. Set `USE_MONGODB_FOR_COSTS = False` in `make_wish_prompts.py`
2. Keep the Excel file in the project root
3. The system will use the Excel file instead

## Next Steps

1. **Run migration**: `python -m app.ai_ingredient_intelligence.scripts.migrate_excel_costs_to_mongo`
2. **Verify**: Check that costs are being used in Make a Wish
3. **Update costs**: Use the `update_cost()` function to update individual costs
4. **Monitor**: Check MongoDB collection for data quality

## Files Created

1. **Migration Script**: `app/ai_ingredient_intelligence/scripts/migrate_excel_costs_to_mongo.py`
2. **MongoDB Lookup Utility**: `app/ai_ingredient_intelligence/utils/inci_cost_lookup_mongo.py`
3. **Updated Prompts**: Already integrated in `make_wish_prompts.py`

The system is ready to use MongoDB for cost data! 🚀

