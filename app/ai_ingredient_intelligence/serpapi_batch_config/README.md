# SerpAPI Batch Configuration

## Setup Instructions

1. **Paste the JSON Configuration**
   - Open `app/ai_ingredient_intelligence/serpapi_batch_config/serpapi_batch_config.json`
   - Paste the full JSON configuration provided by Techs n Tomes
   - Save the file

2. **Ensure SERPAPI_KEY is set in .env**
   - Make sure your `.env` file has: `SERPAPI_KEY=your_key_here`

2. **Run the Monthly Batch Script**
   ```bash
   # Dry run (generate queries but don't fetch)
   python app/ai_ingredient_intelligence/scripts/fetch_market_trends_scheduled.py --dry-run
   
   # Actual run (requires --enable-api flag)
   python app/ai_ingredient_intelligence/scripts/fetch_market_trends_scheduled.py --enable-api
   ```

## What the Script Does

1. **Loads Configuration**: Reads the JSON config file
2. **Generates Queries**: Creates queries for:
   - Level 1: Ingredient × Format combinations
   - Level 2: Benefit × Format combinations  
   - Level 3: Brand × Hero Product combinations
   - Comparison queries for Google Trends
3. **Fetches Data**: Uses SerpAPI to fetch:
   - Google Trends interest over time
   - Related queries (rising & top)
   - Regional interest data
   - Google Shopping data (for price ranges)
4. **Stores Data**: Saves to MongoDB `market_trends_storage` collection
5. **Rate Limiting**: Respects 5 requests/second limit with retries

## Scheduling

The script is designed to run monthly on the 1st at 2:00 AM IST. You can schedule it using:
- Cron (Linux/Mac)
- Task Scheduler (Windows)
- APScheduler/Celery in your application

## Configuration File Structure

The JSON config should contain:
- `_meta`: Metadata about the config
- `batch_job_config`: Scheduling and API settings
- `ingredients`: All ingredients (modern + Ayurvedic)
- `product_formats`: Product format definitions
- `benefits`: Benefit/claim terms
- `brands`: Brand definitions
- `query_generation_rules`: Rules for generating queries

## Notes

- The script automatically deduplicates queries
- Failed queries are retried up to 3 times
- Shopping data is fetched for every 10th ingredient query
- All data is stored with `fetch_source: "batch"` for tracking

