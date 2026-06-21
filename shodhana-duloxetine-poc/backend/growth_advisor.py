import sqlite3
from collections import defaultdict
from backend.db import connect
from backend.engine import opportunities

def generate_growth_insights(filters=None):
    """Compiles strategic AI growth insights from active trade databases."""
    # 1. Fetch opportunities scored by the engine
    all_opps = opportunities(filters=filters, limit=100)
    
    # 2. Get Top 3 target accounts (High opportunity & not existing Shodhana accounts)
    target_accounts = []
    for opp in all_opps:
        if len(target_accounts) >= 3:
            break
        # Exclude existing supply and generic identified buyers
        is_generic = opp.get("customer_identification_status") == "Generic Consignee / Forwarder"
        is_existing = opp.get("shodhana_status") == "Existing Shodhana Supply"
        if not is_generic and not is_existing and opp.get("score", 0) >= 45:
            target_accounts.append({
                "importer": opp.get("importer"),
                "country": opp.get("country"),
                "product": opp.get("product"),
                "volume_kg": opp.get("total_quantity_kg", 0),
                "avg_price": opp.get("avg_price_per_kg", 0),
                "competitor": opp.get("current_supplier") or opp.get("exporter") or "Unknown Competitor",
                "score": opp.get("score"),
                "opportunity_id": opp.get("opportunity_id"),
                "tier": opp.get("tier"),
                "reasons": opp.get("reasons", [])
            })
            
    # 3. Competitor Vulnerability Audit
    competitor_data = defaultdict(lambda: {
        "volume_kg": 0.0, 
        "value_usd": 0.0, 
        "clients": set(), 
        "price_records": 0,
        "priced_volume": 0.0,
        "priced_value": 0.0
    })
    
    # Query raw database directly for exporter metrics
    with connect() as conn:
        rows = conn.execute("""
            select 
                standard_exporter_name as exporter,
                standard_importer_name as importer,
                quantity_kg,
                value_usd,
                price_per_kg
            from clean_trade_records
            where coalesce(standard_exporter_name, '') != '' 
              and standard_exporter_name not in ('SHODHANA LABORATORIES', 'SHODHANA LABS', 'SHODHANA')
        """).fetchall()
        
    for r in rows:
        exp = r["exporter"]
        qty = r["quantity_kg"] or 0
        val = r["value_usd"] or 0
        price = r["price_per_kg"]
        
        competitor_data[exp]["volume_kg"] += qty
        competitor_data[exp]["value_usd"] += val
        competitor_data[exp]["clients"].add(r["importer"])
        if price:
            competitor_data[exp]["price_records"] += 1
            competitor_data[exp]["priced_volume"] += qty
            competitor_data[exp]["priced_value"] += val

    vulnerable_competitors = []
    for exp, stats in competitor_data.items():
        total_vol = stats["volume_kg"]
        priced_vol = stats["priced_volume"]
        priced_val = stats["priced_value"]
        avg_price = priced_val / priced_vol if priced_vol > 0 else 0
        
        # Determine vulnerability (e.g. charging above average, single client reliance)
        vulnerability_score = 0
        reasons = []
        
        # High average pricing (premium pricing)
        if avg_price > 120.0:  # Assumed benchmark high price
            vulnerability_score += 30
            reasons.append(f"Premium pricing observed (${avg_price:,.2f}/KG)")
        
        # Single client dependency (easy to disrupt)
        client_count = len(stats["clients"])
        if client_count == 1:
            vulnerability_score += 40
            reasons.append("Single-client sourcing dependency (high customer concentration risk)")
        elif client_count <= 2:
            vulnerability_score += 20
            reasons.append("Low client diversity (highly vulnerable to disruption)")
            
        if vulnerability_score > 0:
            vulnerable_competitors.append({
                "competitor": exp,
                "volume_kg": round(total_vol, 2),
                "clients_count": client_count,
                "avg_price": round(avg_price, 2),
                "vulnerability_reasons": reasons,
                "vulnerability_score": vulnerability_score
            })
            
    vulnerable_competitors.sort(key=lambda x: x["vulnerability_score"], reverse=True)
    
    # 4. Regional Entry Planner (Market entry recommendations)
    country_data = defaultdict(lambda: {"volume_kg": 0.0, "shodhana_vol": 0.0, "competitors": set()})
    with connect() as conn:
        records = conn.execute("""
            select 
                importer_country as country,
                standard_exporter_name as exporter,
                quantity_kg
            from clean_trade_records
            where coalesce(importer_country, '') != '' 
              and importer_country != 'Unknown'
        """).fetchall()
        
    for r in records:
        country = r["country"]
        qty = r["quantity_kg"] or 0
        exp = r["exporter"]
        
        country_data[country]["volume_kg"] += qty
        if exp and any(term in exp.upper() for term in ("SHODHANA", "SHODHANA LABORATORIES")):
            country_data[country]["shodhana_vol"] += qty
        else:
            if exp:
                country_data[country]["competitors"].add(exp)
                
    regional_strategies = []
    for country, stats in country_data.items():
        total_vol = stats["volume_kg"]
        shodhana_vol = stats["shodhana_vol"]
        shodhana_share = (shodhana_vol / total_vol) * 100 if total_vol > 0 else 0
        
        if shodhana_share < 15 and total_vol > 100:  # Low Shodhana presence but active market
            reasons = []
            if shodhana_vol == 0:
                reasons.append("Zero Shodhana supply footprint in this country")
            else:
                reasons.append(f"Low Shodhana market share ({shodhana_share:.1f}%)")
                
            reasons.append(f"High competitor activity ({len(stats['competitors'])} observed suppliers)")
            
            regional_strategies.append({
                "country": country,
                "total_volume_kg": round(total_vol, 2),
                "shodhana_share_pct": round(shodhana_share, 2),
                "competitors_count": len(stats["competitors"]),
                "recommendation_reasons": reasons,
                "priority": "High" if total_vol > 1000 else "Medium"
            })
            
    regional_strategies.sort(key=lambda x: x["total_volume_kg"], reverse=True)

    # 5. Market Pricing Matrix (Recommended price bounds)
    pricing_matrix = {}
    with connect() as conn:
        price_summary = conn.execute("""
            select 
                standard_product as product,
                min(price_per_kg) as min_price,
                avg(price_per_kg) as avg_price,
                max(price_per_kg) as max_price
            from clean_trade_records
            where price_per_kg is not null
            group by standard_product
        """).fetchall()
        
    for ps in price_summary:
        prod = ps["product"]
        if prod == "Other / Review Required":
            continue
        min_p = ps["min_price"] or 0
        avg_p = ps["avg_price"] or 0
        max_p = ps["max_price"] or 0
        
        pricing_matrix[prod] = {
            "observed_min": round(min_p, 2),
            "observed_avg": round(avg_p, 2),
            "observed_max": round(max_p, 2),
            "suggested_pitch_range": f"${round(min_p * 1.05, 2):,.2f} - ${round(avg_p * 0.95, 2):,.2f}/KG" if min_p < avg_p else f"${round(avg_p * 0.9, 2):,.2f}/KG"
        }

    return {
        "target_accounts": target_accounts,
        "vulnerable_competitors": vulnerable_competitors[:5],
        "regional_strategies": regional_strategies[:5],
        "pricing_matrix": pricing_matrix
    }
