"""
ingest_cocktails.py
───────────────────
Data Ingestion Pipeline for BarVision / SpiritSync.
Dev 2 Responsibility:
1. Fetch 600+ IBA & classic cocktails from TheCocktailDB.
2. Normalize volume measures (oz, cl, splash, dash) to standard millilitres (ml).
3. Classify ingredients (base_spirit, liqueur, acid, sweet, mixer, garnish).
4. Calculate estimated ABV % (Alcohol By Volume) and Sweet/Sour balance ratio.
5. Export clean dataset to data/cocktails_clean.json.
6. (Optional) Initialize Qdrant collection and upload vectors.
"""

import os
import re
import json
import logging
import urllib.request
from typing import Dict, List, Any, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("CocktailIngest")

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "cocktails_clean.json")

# Standard ABV mapping for typical bar ingredients
INGREDIENT_ABV_MAP = {
    # Base Spirits (approx 40%)
    "gin": 40.0, "vodka": 40.0, "white rum": 40.0, "dark rum": 40.0, "rum": 40.0,
    "light rum": 40.0, "tequila": 40.0, "bourbon": 40.0, "scotch": 40.0,
    "whiskey": 40.0, "whisky": 40.0, "brandy": 40.0, "cognac": 40.0,
    "mezcal": 40.0, "rye whiskey": 45.0, "pisco": 40.0,
    
    # Liqueurs & Fortified Wines
    "cointreau": 40.0, "triple sec": 30.0, "grand marnier": 40.0,
    "kahlua": 20.0, "baileys": 17.0, "amaretto": 28.0,
    "campari": 25.0, "aperol": 11.0, "sweet vermouth": 15.0, "dry vermouth": 18.0,
    "maraschino liqueur": 32.0, "blue curacao": 25.0, "chambord": 16.5,
    "benedictine": 40.0, "chartreuse": 55.0, "sambuca": 38.0,
    
    # Non-alcoholic (0%)
    "lime juice": 0.0, "lemon juice": 0.0, "orange juice": 0.0,
    "simple syrup": 0.0, "sugar syrup": 0.0, "grenadine": 0.0,
    "tonic water": 0.0, "soda water": 0.0, "club soda": 0.0, "cola": 0.0,
    "ginger beer": 0.0, "cranberry juice": 0.0, "pineapple juice": 0.0,
    "water": 0.0, "egg white": 0.0, "cream": 0.0, "milk": 0.0
}

def parse_measure_to_ml(measure_str: Optional[str]) -> float:
    """Convert arbitrary measure strings (oz, cl, shot, dash, tsp) into standard ml."""
    if not measure_str:
        return 15.0  # Default estimate if not specified
    
    raw = measure_str.lower().strip()
    
    # Handle fractions like "1 1/2", "1/2", "3/4"
    fraction_map = {"1/4": 0.25, "1/3": 0.33, "1/2": 0.5, "2/3": 0.66, "3/4": 0.75}
    total_val = 0.0
    
    # Check for ounces (oz)
    if "oz" in raw:
        num_part = raw.replace("oz", "").strip()
        parts = num_part.split()
        for p in parts:
            if p in fraction_map:
                total_val += fraction_map[p]
            elif "/" in p:
                try:
                    num, den = p.split("/")
                    total_val += float(num) / float(den)
                except Exception:
                    pass
            else:
                try:
                    total_val += float(p)
                except Exception:
                    pass
        if total_val > 0:
            return round(total_val * 29.5735, 1) # 1 oz approx 30 ml
        return 30.0

    # Check for centiliters (cl) -> 1 cl = 10 ml
    if "cl" in raw:
        m = re.search(r"(\d+(?:\.\d+)?)", raw)
        if m:
            return round(float(m.group(1)) * 10.0, 1)
        return 20.0

    # Check for ml
    if "ml" in raw:
        m = re.search(r"(\d+(?:\.\d+)?)", raw)
        if m:
            return float(m.group(1))

    # Bar measurements
    if "dash" in raw:
        return 1.0
    if "drop" in raw:
        return 0.5
    if "tsp" in raw or "teaspoon" in raw:
        return 5.0
    if "tbsp" in raw or "tablespoon" in raw:
        return 15.0
    if "shot" in raw:
        return 45.0
    if "part" in raw:
        return 30.0

    return 20.0

def classify_ingredient(name: str) -> str:
    """Classify ingredient type into base_spirit, liqueur, acid, sweet, mixer, garnish."""
    n = name.lower()
    if any(s in n for s in ["gin", "vodka", "rum", "tequila", "whiskey", "whisky", "bourbon", "brandy", "cognac", "mezcal", "pisco"]):
        return "base_spirit"
    if any(s in n for s in ["liqueur", "cointreau", "triple sec", "kahlua", "vermouth", "campari", "aperol", "curacao", "amaretto"]):
        return "liqueur"
    if any(s in n for s in ["lime", "lemon", "acid", "grapefruit juice"]):
        return "acid"
    if any(s in n for s in ["syrup", "sugar", "honey", "grenadine", "agave"]):
        return "sweet"
    if any(s in n for s in ["soda", "tonic", "cola", "ginger", "juice", "water", "sprite"]):
        return "mixer"
    return "garnish"

def calculate_cocktail_abv(ingredients: List[Dict[str, Any]]) -> float:
    """Calculate Alcohol By Volume (%) based on weighted volume and estimated ABV."""
    total_volume = sum(i["measure_ml"] for i in ingredients)
    if total_volume <= 0:
        return 0.0
    
    total_alcohol_ml = 0.0
    for ing in ingredients:
        name_lower = ing["name"].lower()
        abv = 0.0
        # Lookup exact or partial
        for key, val in INGREDIENT_ABV_MAP.items():
            if key in name_lower:
                abv = val
                break
        total_alcohol_ml += ing["measure_ml"] * (abv / 100.0)
    
    return round((total_alcohol_ml / total_volume) * 100.0, 1)

def fetch_cocktails_from_api() -> List[Dict[str, Any]]:
    """Fetch cocktail data from TheCocktailDB (letters a to z)."""
    cocktails = []
    seen_ids = set()
    
    # Letters to search
    letters = [chr(c) for c in range(ord('a'), ord('z') + 1)]
    logger.info("Fetching cocktails from TheCocktailDB across alphabet...")
    
    for letter in letters:
        url = f"https://www.thecocktaildb.com/api/json/v1/1/search.php?f={letter}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "BarVision-ETL/1.0"})
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())
                drinks = data.get("drinks")
                if not drinks:
                    continue
                
                for d in drinks:
                    drink_id = d.get("idDrink")
                    if drink_id in seen_ids:
                        continue
                    seen_ids.add(drink_id)
                    
                    # Parse ingredients
                    raw_ingredients = []
                    for idx in range(1, 16):
                        ing_name = d.get(f"strIngredient{idx}")
                        if not ing_name:
                            continue
                        measure_raw = d.get(f"strMeasure{idx}")
                        measure_ml = parse_measure_to_ml(measure_raw)
                        ing_type = classify_ingredient(ing_name)
                        
                        raw_ingredients.append({
                            "name": ing_name.strip(),
                            "measure_raw": measure_raw.strip() if measure_raw else None,
                            "measure_ml": measure_ml,
                            "type": ing_type
                        })
                    
                    if not raw_ingredients:
                        continue
                    
                    calculated_abv = calculate_cocktail_abv(raw_ingredients)
                    
                    clean_cocktail = {
                        "id": f"cocktail_{drink_id}",
                        "name": d.get("strDrink"),
                        "category": d.get("strCategory"),
                        "iba_category": d.get("strIBA"),
                        "alcoholic": d.get("strAlcoholic"),
                        "glass": d.get("strGlass"),
                        "instructions": d.get("strInstructions"),
                        "image_url": d.get("strDrinkThumb"),
                        "ingredients": raw_ingredients,
                        "metrics": {
                            "estimated_abv": calculated_abv,
                            "difficulty": "easy" if len(raw_ingredients) <= 3 else "medium",
                            "method": "stirred" if "stir" in (d.get("strInstructions") or "").lower() else "shaken"
                        },
                        "flavor_tags": [
                            tag for tag in ["refreshing", "citrus", "sweet", "strong", "bitter", "creamy"]
                            if tag in (d.get("strInstructions") or "").lower() or tag in (d.get("strCategory") or "").lower()
                        ]
                    }
                    cocktails.append(clean_cocktail)
        except Exception as e:
            logger.warning(f"Failed fetching for letter {letter}: {e}")
            continue

    logger.info(f"Successfully processed {len(cocktails)} unique cocktails.")
    return cocktails

def main():
    logger.info("Starting Cocktail Ingestion Pipeline (Dev 2)...")
    cocktails = fetch_cocktails_from_api()
    
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(cocktails, f, indent=2, ensure_ascii=False)
        
    logger.info(f"Clean cocktail dataset saved to: {OUTPUT_PATH}")

if __name__ == "__main__":
    main()
