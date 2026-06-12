# Imports Folder

The MVP imports `duloxetine_market.csv` from this folder.

Required columns:

```text
company,region,country,product,role,estimated_volume_kg,estimated_price_usd_kg,competitor_supplier,current_shodhana_customer,last_purchase_date,trend,notes
```

Use this for ChemGenXia, API-FDF, export/import, or manually prepared pilot data.

## Shipment Cleanup Demo

Use these files to prove the first Grow workflow:

```text
raw_shipments_duloxetine.csv
product_aliases.csv
company_aliases.csv
```

Then click **Import Shipments** in the dashboard.

This will:

- normalize product names
- normalize company names
- remove duplicate shipment rows
- classify market category
- calculate average price per KG
- show target customer insights
