# app/db/collections.py

"""Typed collection refs (import these elsewhere)"""

from app.ai_ingredient_intelligence.db.mongodb import db

branded_ingredients_col = db["ingre_branded_ingredients"]
inci_col = db["ingre_inci"]
suppliers_col = db["ingre_suppliers"]
functional_categories_col = db["ingre_functional_categories"]
chemical_classes_col = db["ingre_chemical_classes"]
documents_col = db["ingre_documents"]
formulations_col = db["ingre_formulations"]
distributor_col = db["distributor"]
ingredient_costs_col = db["ingredient_costs"]  # Collection with avg_cost for ingredients

# Exclude hidden ingredient costs when fetching for formulas/cost lookup (admin can set hide via API)
INGREDIENT_COST_NOT_HIDDEN_QUERY = {"$or": [{"hide": {"$ne": True}}, {"hide": {"$exists": False}}]}
decode_history_col = db["decode_history"]
compare_history_col = db["compare_history"]
market_research_history_col = db["market_research_history"]
wish_history_col = db["wish_history"]
inspiration_boards_col = db["inspiration_boards"]
inspiration_products_col = db["inspiration_products"]
product_tags_col = db["product_tags"]
url_cache_col = db["url_cache"]
trend_cache_col = db["trend_cache"]
trend_alerts_col = db["trend_alerts"]
trend_history_col = db["trend_history"]

# ============================================================================
# NEW COLLECTIONS FOR REVISED MAKE A WISH FLOW (January 2025)
# ============================================================================

# Note: commercialization_requests removed - using qms_queries directly instead

# Formula versions collection for edit history
formula_versions_col = db["formula_versions"]

# Quotes collection for manufacturing quotes
quotes_col = db["quotes"]

# Ingredient alternatives cache collection
ingredient_alternatives_cache_col = db["ingredient_alternatives_cache"]

# ============================================================================
# NOTIFICATION COLLECTION
# ============================================================================

# Formulynx notifications collection for storing user notifications
notifications_col = db["formulynx_notifications"]

# ============================================================================
# QMS (Query Management System) COLLECTIONS
# ============================================================================

# Main users collection (shared across the app)
users_col = db["users"]

# Partners collection (formulation partners)
qms_partners_col = db["qms_partners"]

# Queries collection (core QMS table)
qms_queries_col = db["qms_queries"]

# Query notes collection (activity feed)
qms_query_notes_col = db["qms_query_notes"]

# Payments collection
qms_payments_col = db["qms_payments"]

# Audit log collection
qms_audit_log_col = db["qms_audit_log"]

# ============================================================================
# MARKET TRENDS STORAGE COLLECTION
# ============================================================================

# Market trends storage - stores pre-fetched market trend data for ingredients/topics
market_trends_storage_col = db["market_trends_storage"]
