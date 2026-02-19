"""
Pydantic schemas for Trend Insights API
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class TrendAnalysisRequest(BaseModel):
    """Request schema for trend analysis"""
    ingredient: str = Field(..., description="Ingredient name to analyze")
    time_range: str = Field(default="today 12-m", description="Time range for analysis (e.g., 'today 12-m', 'today 5-y')")
    compare_with: Optional[List[str]] = Field(default=None, description="Optional list of ingredients to compare with")


class TrendAnalysisResponse(BaseModel):
    """Response schema for trend analysis"""
    ingredient: str
    analysis_period: str
    data_points: int
    trend_classification: Dict[str, Any]
    interest_metrics: Dict[str, Any]
    related_queries: Dict[str, List[Dict[str, Any]]]
    error: Optional[str] = None


class ConsumerIntentRequest(BaseModel):
    """Request schema for consumer intent analysis"""
    ingredient: str = Field(..., description="Ingredient name")
    concerns: Optional[List[str]] = Field(default=None, description="Optional list of skin concerns to analyze")


class ConsumerIntentResponse(BaseModel):
    """Response schema for consumer intent analysis"""
    ingredient: str
    queries_analyzed: int
    total_paa_questions: int
    unique_questions: int
    intent_breakdown: Dict[str, List[Dict[str, Any]]]


class CompetitiveAnalysisRequest(BaseModel):
    """Request schema for competitive analysis"""
    category: str = Field(..., description="Product category (e.g., 'niacinamide serum')")
    price_min: Optional[int] = Field(default=None, description="Minimum price filter")
    price_max: Optional[int] = Field(default=None, description="Maximum price filter")


class CompetitiveAnalysisResponse(BaseModel):
    """Response schema for competitive analysis"""
    category: str
    products_found: int
    brands_found: int
    analysis_date: str
    market_overview: Dict[str, Any]
    price_tier_distribution: Dict[str, Dict[str, Any]]
    brand_analysis: Dict[str, Any]
    error: Optional[str] = None


class RegionalAnalysisRequest(BaseModel):
    """Request schema for regional demand analysis"""
    ingredient: str = Field(..., description="Ingredient name")
    time_range: str = Field(default="today 12-m", description="Time range for analysis")


class RegionalAnalysisResponse(BaseModel):
    """Response schema for regional demand analysis"""
    ingredient: str
    total_regions: int
    high_demand_regions: List[Dict[str, Any]]
    moderate_demand_regions: List[Dict[str, Any]]
    low_demand_regions: List[Dict[str, Any]]
    error: Optional[str] = None


class CompareIngredientsRequest(BaseModel):
    """Request schema for ingredient comparison"""
    ingredients: List[str] = Field(..., description="List of ingredients to compare (max 5)")
    time_range: str = Field(default="today 12-m", description="Time range for analysis")


class CompareIngredientsResponse(BaseModel):
    """Response schema for ingredient comparison"""
    ingredients: List[str]
    time_range: str
    comparison: List[Dict[str, Any]]
    error: Optional[str] = None


class TrendSynthesisRequest(BaseModel):
    """Request schema for comprehensive trend synthesis"""
    ingredient: str = Field(..., description="Ingredient name")
    time_range: str = Field(default="today 12-m", description="Time range for analysis")
    include_regional: bool = Field(default=True, description="Include regional analysis")
    include_competitive: bool = Field(default=True, description="Include competitive analysis")
    include_consumer_intent: bool = Field(default=True, description="Include consumer intent analysis")


class TrendSynthesisResponse(BaseModel):
    """Response schema for trend synthesis"""
    ingredient: str
    trend_analysis: Optional[Dict[str, Any]] = None
    consumer_intent: Optional[Dict[str, Any]] = None
    competitive_landscape: Optional[Dict[str, Any]] = None
    regional_demand: Optional[Dict[str, Any]] = None
    synthesis: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
