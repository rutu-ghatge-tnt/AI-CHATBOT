r"""
Prompt bodies for Label Looker — structure matches Node post-processing:
- image flow: model returns a bracketed list; code uses regex \[\s*([\s\S]*?)\s*\] then comma split.
- analysis flows: strip fences; first \{...\} brace object; JSON.parse equivalent.

When src/controllers/productIngredientScan.controller.js is added to the repo, diff these
strings against that file and align verbatim.
"""

from __future__ import annotations

import json


def scan_image_to_text_prompt() -> str:
    return "Give me the list of ingredient from above attact image? give ingredient list in array format, and also seperate ingredient name."


def ingredient_analysis_user_message(
    *,
    ingredients_text: str,
    specific_type: str | None,
    main_benefit: str | None,
    langauge: str,
) -> str:
    st = specific_type or ""
    mb = main_benefit or ""
    lg = langauge or "English"
    return f"""You must respond with ONLY valid JSON. Do not include any explanatory text before or after the JSON.
Analyze the following {st} formula for {mb}. Generate a response in {lg}. Retain ingredient names in {lg} and structure as follows:
 
        1.  Opinion on product efficacy in minimum 30 words. => with key "opinion" for json object       
 
        2. Key Ingredients: List top 3-5 active ingredients with names and one key benefit. => with key "keyIngredients" for json object       
 
        3. Benefits Offered: State 2-3 most important benefits offered by the whole formula. => with key "benefitsOffered" for json object
 
        4. Important Considerations: List 2 key points. => with key "importantConsiderations" for json object
 
        5. Product Usage Tips: Provide 3 specific tips. => with key "productUsageTips" for json object
 
        6. Ingredient Categorization: Group ingredients into: => with key "ingredientCategorization" for json object
 
           - Plant-Derived => with key "plant-derived"
 
           - Synthetic => with key "synthetic"
 
           - Marine => with key "marine-non-animal"
 
           - Animal-Origin => with key "animal-origin"
 
           - Unknown (if source cannot be confirmed or if multiple sources available) => with key "unknown"           
 
        Note: Do not include water in any category
 
        Ingredient list:  {ingredients_text}
        
        IMPORTANT: Return ONLY valid JSON. Start your response with {{ and end with }}. Do not include any text before or after the JSON object."""

def prompt_ai_to_get_ingredient_details(
    *,
    ingredient_name: str,
    skin_benefits: list[str],
    categories: list[str],
    naturalities: list[str],
) -> str:
    return f"""Provide detailed information about the skin ingredient: "{ingredient_name}".
            Please follow these rules for each field:
            1. Return the response as a valid JSON object.
            2. Ensure that all strings are enclosed in double quotes.
            3. Escape any quotes or special characters inside string values.
            For the JSON structure, include the following fields:
            1. "benefits": An array selected from the list {json.dumps(skin_benefits)}.
            2. "category": An array selected from the list {json.dumps(categories)}.
            3. "subTitle": A string.
            4. "casNumber": A string.
            5. "ewgSafetyScore": A value selected from [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, "N/A"].
            6. "description": A string in HTML format describing "{ingredient_name}".
            7. "originStory": A string in HTML format about the origin of "{ingredient_name}".
            8. "science": A string in HTML format explaining the science behind "{ingredient_name}".
            9. "routine": A string in HTML format explaining how to incorporate "{ingredient_name}" into skincare routines.
            10. "efficiencyEvidence": A string in HTML format showing efficacy evidence for "{ingredient_name}".
            11. "recommendedLevel": A string in HTML format describing the recommended usage level.
            12. "naturality": An array selected from the list {json.dumps(naturalities)}.
            13. "naturalityReason": A string explaining why "{ingredient_name}" is considered natural.
            14. "shouldNotUse": A string in HTML format explaining who should avoid "{ingredient_name}".
            15. "bestForSkinType": A string in HTML format describing the best skin types for "{ingredient_name}".
            16. "keepInMind": A string in HTML format for important notes about "{ingredient_name}".
            17. "didYouKnow": A string in HTML format with interesting facts about "{ingredient_name}".
            18. "conclusion": A string in HTML format summarizing the use of "{ingredient_name}".
            19. "references": A string in HTML format for any references related to "{ingredient_name}".
            20. "additionalInfo": A string in HTML format with any additional information.
            Please ensure the entire response is in valid JSON format. Do not add extra comments, and ensure there are no syntax errors.
            
            IMPORTANT: Return ONLY valid JSON. Start your response with {{ and end with }}. Do not include any text before or after the JSON object."""
