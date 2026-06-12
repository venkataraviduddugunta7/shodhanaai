# Shodhana AI - Duloxetine Trade Intelligence POC

Fresh proof of concept for the first Shodhana AI Grow module.

The first demo proves:

1. Upload Duloxetine Excel/CSV market data
2. Detect columns from Chemdos/APIFDF style files
3. Classify products into Duloxetine API, Duloxetine Pellets, Duloxetine Placebo Pellets, or Review Required
4. Normalize importer/exporter company names
5. Convert quantity into KG where possible
6. Calculate price per KG
7. Review and approve/edit/reject product and company mappings
8. Re-run cleaning from raw records using approved mappings
9. Show a business dashboard for demand, suppliers, countries, price, and Shodhana/competitor supply
10. Rank customer opportunities using quantity, recency, supplier, price, country market type, and data quality
11. Open a customer opportunity detail page with shipment history, supplier history, price analysis, and recommended action
12. Export cleaned data, opportunity rows, and dashboard summary
13. Generate AI-assisted customer summary, pitch email, price strategy, and PPT outline

## Run

```bash
python3 app.py
```

Open:

```text
http://127.0.0.1:8010
```

Then click `Import Sample File`, or upload a new `.xlsx`/`.csv`.

## Railway Hosting

Railway deployment notes are in:

```text
docs/RAILWAY_DEPLOYMENT.md
```

Use these key settings:

```text
Root Directory: /shodhana-duloxetine-poc
Start Command: python app.py
Volume Mount Path: /app/persistent-data
Variable: SHODHANA_DATA_DIR=/app/persistent-data
```

## Demo Flow

```text
Upload Excel
-> Initial Cleaning
-> Cleaning Review
-> Approve/Edit mappings
-> Re-run Cleaning
-> Dashboard
-> Opportunities
-> Pitch
```

The browser supports `/cleaning-review` directly:

```text
http://127.0.0.1:8010/cleaning-review
```

## Cleaning Review

The Cleaning Review module is the manual-control layer before the final dashboard.

It shows:

- Product Mapping Review: raw product description, suggested standard product, confidence, reason, status, and Approve/Edit/Reject actions.
- Company Mapping Review: raw importer/exporter name, suggested standard company name, confidence, role, status, and Approve/Edit/Reject actions.
- Cleaning Summary: raw records, cleaned records, approved mappings, review-required records, valid KG rows, invalid units, price/kg rows, and missing value/quantity rows.
- Manual review filters: pending mappings, low-confidence rows, review-required products, invalid units, and missing price/kg rows.

### How To Approve Mappings

For product rows, choose one of:

- `Duloxetine API`
- `Duloxetine Pellets`
- `Duloxetine Placebo Pellets`
- `Other / Review Required`

Then click `Approve` or `Edit`. `Reject` marks the suggestion as rejected and keeps it out of approved mappings.

For company rows, edit the suggested standard company name directly in the text field, then click `Approve` or `Edit`.

### How To Re-run Cleaning

After approving or editing mappings, click `Re-run Cleaning`.

The system will:

- Reprocess the raw uploaded records
- Apply approved product mappings
- Apply approved importer/exporter company mappings
- Recalculate KG quantity
- Recalculate price/kg
- Rebuild dashboard metrics
- Regenerate opportunity rows

This is the key proof for Shodhana: the sales team can move from messy Excel to controlled, reviewed, sales-ready intelligence without manually rebuilding pivot tables every time.

## Dashboard And Opportunity Engine

The dashboard is designed for Shodhana's Duloxetine API and Duloxetine Pellets sales team. It answers the questions they normally try to solve manually from Excel:

- Who is importing Duloxetine?
- Who is exporting and supplying the market?
- Which competitors are active?
- Which countries are buying?
- What is the average price per KG?
- Where is Shodhana already supplying?
- Where are competitors supplying?
- Which customers should be targeted first?

### Dashboard KPIs

The dashboard shows:

- Total Records
- Clean Records
- Total Quantity KG
- Total Value USD
- Average Price/KG
- Unique Importers
- Unique Exporters
- Unique Countries
- Review Required Records
- Competitor Supplied Records
- Shodhana Supplied Records

### Dashboard Filters

All dashboard intelligence can be filtered by:

- Product Category
- Importer Country
- Exporter Country
- Importer Name
- Exporter Name
- Year
- Month
- Shodhana Status

This lets the team focus the demo, for example: `Duloxetine Pellets`, `Brazil`, `Competitor Supply`, or a specific importer/exporter.

### Dashboard Charts And Tables

The dashboard includes demo-ready chart sections for:

- Product category split by quantity
- Country-wise demand by quantity
- Top 10 importer countries by quantity
- Top 10 importers by quantity
- Top 10 exporters by quantity
- Month-wise quantity trend
- Average price/kg trend by month
- Price range by product category

It also includes:

- Competitor Intelligence table: exporter, product, countries supplied, quantity, value, average price/kg, shipment count, and last shipment date.
- Customer Intelligence table: importer, country, product, current supplier, quantity, value, average price/kg, shipments, first/last shipment date, and Shodhana status.

### Opportunity Scoring

Each importer + product group receives an opportunity score.

The scoring model rewards:

- High quantity buyers
- Recent purchase activity
- Buying from a competitor
- Repeated shipments
- Regulated or semi-regulated markets
- Average price/kg above market average

The scoring model penalizes:

- Missing or invalid KG quantity
- Product rows still marked as Review Required

Opportunity categories:

- `High Opportunity`: 75 and above
- `Medium Opportunity`: 45 to 74
- `Low Opportunity`: below 45

Every opportunity includes plain-English reasons such as `High quantity buyer`, `Recent purchase activity`, `Buying from competitor`, `Price above market average`, and `Requires manual product review`.

### Opportunity Detail Page

Click `View Details` from the opportunity table to open:

```text
/opportunities/<opportunity-id>
```

The detail page shows:

- Customer summary
- Product summary
- Supplier history
- Shipment history
- Price analysis
- Why this customer is important
- Recommended Shodhana action
- Button to generate the pitch

This is the strongest demo path:

```text
Upload messy Duloxetine Excel
-> Clean and approve mappings
-> Dashboard shows market demand and supplier activity
-> Opportunity engine ranks customers
-> Open the top customer
-> System explains why to target them
-> Generate pitch
```

## AI Pitch Generation

The pitch module turns a ranked opportunity into a customer-specific sales draft. It is still deterministic and template-based for the POC, but the backend is separated behind an AI service interface so it can later be replaced by OpenAI or AWS Bedrock.

Current pitch service functions:

- `generateCustomerSummary(opportunity)`
- `generatePitchEmail(opportunity)`
- `generatePriceStrategy(opportunity)`
- `generatePptOutline(opportunity)`
- `generateFollowUpPlan(opportunity)`

Open a pitch directly at:

```text
/pitch/<opportunity-id>
```

The pitch workspace shows:

- Customer Intelligence Summary
- Buying Pattern
- Current Supplier
- Price Analysis
- Why Shodhana Should Target
- Recommended Commercial Strategy
- Pitch Email Draft
- PPT Outline
- Follow-up Plan

Pitch emails include three variants:

- Formal
- Short direct
- Relationship-building

The generated pitch uses Shodhana positioning:

- Shodhana has strong experience in Duloxetine API and Duloxetine Pellets.
- Shodhana can support API and semi-formulation/pellet requirements.
- Shodhana can support DMF/non-DMF commercial models where applicable.
- Shodhana can position on quality, reliability, regulatory support, and long-term supply partnership.

The commercial guidance does not generate final confirmed pricing. It uses safe language such as `commercially competitive offer`, `price discussion can be aligned after requirement validation`, and `suggested pricing should be reviewed by business team`.

### Pitch Storage

Generated pitches are saved in `generated_pitches` with:

- Opportunity ID
- Customer summary
- Buying pattern
- Price strategy
- Formal email draft
- Short direct email draft
- Relationship-building email draft
- PPT outline JSON
- Follow-up plan
- Created timestamp

The user can regenerate the pitch from latest opportunity data.

### Pitch Exports

The pitch workspace supports:

- Copy current email draft
- Export full pitch as text
- Export PPT outline as markdown
- Download customer summary as markdown

Every generated pitch shows this approval reminder:

```text
AI-generated output is a draft. Sales/business team must review before sending externally.
```

The pitch demo flow is:

```text
Opportunity row
-> Generate pitch
-> Customer summary
-> Price strategy
-> Email draft
-> PPT outline
-> Follow-up plan
```

### Export Options

The app can export:

- Cleaned data as Excel
- Opportunity table as Excel
- Dashboard summary as CSV

This matters because Shodhana can still use Excel for internal review while the POC removes the repeated manual cleaning, pivoting, scoring, and pitch-preparation work.

## Project Shape

```text
backend/
  ai_service.py       Mock AI action layer
  db.py               SQLite schema and persistence
  engine.py           Upload, cleaning, dashboard, opportunity scoring
  excel_reader.py     CSV/XLSX reader without external packages
  normalization.py    Product, company, unit, market classification
web/
  index.html          Browser UI
  styles.css          Layout, dashboard, tooltips
  app.js              API calls and rendering
data/
  samples/            Local sample file for demo
  seed/               Product and company synonym masters
  uploads/            Uploaded files
docs/
  POC_FLOW.md         Business demo flow
  NEXT_PRISMA_TARGET.md Production stack migration notes
prisma/
  schema.prisma       Target production schema
```

## Why This Is AI

The first value is not a generic chatbot. The useful engine is:

- Data cleaning intelligence: recognizes product aliases, messy company names, units, duplicate rows, price/kg, and low-confidence review gaps.
- Opportunity intelligence: groups buyers/suppliers/countries, scores accounts, and recommends actions.
- Generative intelligence: turns structured market facts into pitch emails, summaries, price strategies, and PPT outlines.

The current AI output is template-based so it is demo-safe. Later, replace `backend/ai_service.py` with OpenAI/AWS Bedrock while keeping the same structured opportunity input.

The dashboard charts are implemented as browser-native demo charts in this no-build Python POC. In the production Next.js version, the same chart data can be rendered with Recharts.

## Important Note

The requested production stack is Next.js + TypeScript + Tailwind + PostgreSQL + Prisma. This machine currently has no `npm`, `npx`, Next.js, React, Prisma, or `xlsx` package installed, so this fresh POC is built to run immediately with Python standard library + SQLite.

The migration target is documented in `docs/NEXT_PRISMA_TARGET.md` and `prisma/schema.prisma`.
