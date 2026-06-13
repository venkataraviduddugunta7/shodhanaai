# Shodhana Engine - Duloxetine Trade Intelligence

Sales-ready Duloxetine growth engine for uploading market files, normalizing messy trade data automatically, ranking customer opportunities, and preparing customer pitch material.

The engine supports:

1. Upload Duloxetine Excel/CSV market data
2. Detect columns from Chemdos/APIFDF style files
3. Classify products into Duloxetine API, Duloxetine Pellets, Duloxetine Placebo Pellets, or Review Required
4. Normalize importer/exporter company names
5. Convert quantity into KG where possible
6. Calculate price per KG
7. Automatically club grouped product, company, and country aliases
8. Keep optional reusable master mappings for admin refinement
9. Show opportunities immediately after upload
10. Show a business dashboard for demand, suppliers, countries, price, and Shodhana/competitor supply
11. Rank customer opportunities using quantity, recency, supplier, price, country market type, and data quality
12. Open a customer opportunity detail page with shipment history, supplier history, price analysis, and recommended action
13. Export cleaned data, opportunity rows, and dashboard summary
14. Generate AI-assisted customer summary, pitch email, price strategy, and PPT outline

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

## Engine Flow

```text
Upload Excel
-> Opportunities
-> Pitch
-> Dashboard
```

The browser supports `/cleaning-review` directly:

```text
http://127.0.0.1:8010/cleaning-review
```

## Optional Admin Review

The main user flow does not require mapping confirmation. Uploading a trade file processes data and opens opportunities directly.

The `/cleaning-review` page remains as an optional admin layer for refining mappings, saving defaults, or correcting edge cases.

It shows:

- Smart Confirm Mappings: grouped product, company, and country aliases that can be approved once at master level.
- Product Mapping Review: raw product description, suggested standard product/category, confidence, reason, status, and Approve/Edit/Reject actions.
- Company Mapping Review: raw importer/exporter name, suggested standard company name, confidence, role, status, and Approve/Edit/Reject actions.
- Country Mapping Review: raw importer/exporter country name, suggested standard country name, confidence, role, status, and Approve/Edit/Reject actions.
- Cleaning Summary: raw records, cleaned records, approved mappings, review-required records, valid KG rows, invalid units, price/kg rows, and missing value/quantity rows.
- Manual review filters: pending mappings, low-confidence rows, review-required products, invalid units, and missing price/kg rows.

### Smart Confirm Groups

Use `Open Smart Confirm` when the user wants a faster top-level review.

The system groups aliases by the suggested master value:

- Product groups: for example multiple raw Duloxetine pellet descriptions under `Duloxetine Pellets`.
- Company groups: importer/exporter spelling variants under one standard company name.
- Country groups: country aliases under one standard country.

The reviewer can confirm the whole group, edit the master value, or reject the group. Every alias has a checkbox, including high-confidence aliases. If an alias does not belong in that group, uncheck it before `Confirm Group` or `Save Edited`. The unchecked alias moves into `Remaining / Create New Mapping`, where the reviewer can select one or more aliases, type a new master product/company/country name, and click `Save New Mapping`.

Confirmed groups disappear from the Smart Confirm modal. Only groups that still need a decision remain visible, which keeps the review focused during a client demo. Mapping saves are intentionally fast: `Confirm Group`, `Save Edited`, `Save New Mapping`, and `Approve Confident` update the mapping configuration only. After review is complete, click `Apply Config` once to apply all approved mappings to the full Excel dataset and rebuild dashboard/opportunity results.

Use `Manage Groups` when an approved mapping needs correction later. In Manage mode, confirmed product, company, and country groups are editable:

- Rename the master group value and click `Save Group`.
- Uncheck aliases that do not belong; they move into `Remaining / Create New Mapping`.
- Open the Remaining group, select one or more aliases, type an existing master name to add them to that group, or type a new master name to create a new group.
- Click `Apply Config` once after group management is complete.

Approved mappings stay in the SQLite database. On the next upload, the same raw name or a very strong normalized company match is applied automatically, so the team does not approve the same company/product/country again.

The app separates system suggestions from confirmed configuration:

- System suggestions can be recalculated as the cleaning rules improve.
- User-confirmed mappings are saved as master configuration.
- Confirmed mappings are also synced into `data/seed/*.csv` as default mappings, so a fresh DB can load the same knowledge.
- Product masters can be edited into subcategories such as `Duloxetine Pellets 17%`, `Duloxetine Pellets 22.5%`, or `Duloxetine Pellets 25%`.
- Company masters club variants like `EVA PHARMA`, `EVA PHARMA FOR PHARMACEUTICALS`, and `EVA PHARMA FOR PHARMACEUTICALSAND MEDICAL APPLIANCES SA`.
- Future AI/LLM support should suggest difficult mappings, but the approved result should still be stored in these mapping tables.

Use `Save Defaults` to manually rewrite the seed CSV files from the current confirmed master mappings. Approve/Edit/Reject actions also sync defaults automatically.

### How To Approve Mappings

For product rows, choose one of:

- `Duloxetine API`
- `Duloxetine Pellets`
- `Duloxetine Placebo Pellets`
- `Other / Review Required`

Then click `Approve` or `Edit`. `Reject` marks the suggestion as rejected and keeps it out of approved mappings.

For company rows, edit the suggested standard company name directly in the text field, then click `Approve` or `Edit`.

For country rows, edit the suggested standard country name directly in the text field, then click `Approve` or `Edit`.

### How To Apply Config

Approving, editing, rejecting, or removing aliases does not reprocess the full Excel immediately. This keeps group confirmation fast. After the reviewer finishes mapping decisions, click `Apply Config` once.

The system will:

- Reprocess the raw uploaded records
- Apply approved product mappings
- Apply approved importer/exporter company mappings
- Apply approved importer/exporter country mappings
- Recalculate KG quantity
- Recalculate price/kg
- Rebuild duplicate keys using approved standard product, company, and country values
- Rebuild dashboard metrics
- Regenerate opportunity rows

This is the key proof for Shodhana: the sales team can move from messy Excel to controlled, reviewed, sales-ready intelligence without manually rebuilding pivot tables every time.

### Similar Name Clubbing

The cleaning review intentionally separates `suggestion` from `approval`.

When a document is scanned, the system suggests clubbing for:

- Importer names
- Exporter names
- Product descriptions and subcategories
- Importer countries
- Exporter countries

Examples:

- `Nosch Labs Pvt Ltd` and `Nosch Labs Private Limited` can be approved under one master company.
- `Republic of Korea` and `South Korea` can be approved under one standard country.
- `Duloxetine EC Pellets 17%` and other pellet subcategory descriptions can be approved under `Duloxetine Pellets`.

Pending suggestions are not treated as final master data. After the user approves or edits mappings, cleaning runs automatically and clubs the approved standards into one clean view for dashboard, opportunities, and pitch generation.

The opportunity engine groups rows by the approved master importer name. It also shows how many raw company names were clubbed and lists those aliases in the opportunity detail view. Supplier history is grouped by the approved master exporter name with its raw aliases visible.

The Opportunities page is not gated by mapping review. Automatic normalization is applied immediately so sales users can move from Excel to ranked customers and pitch generation without a manual cleanup meeting.

Single trusted values do not create review work. For example, a normal country value like \`Brazil\` is treated as already clean; only new aliases or fuzzy matches such as \`US America\` against an existing \`United States\` master are sent to confirmation.

The approved master data is stored in:

- `product_mappings`
- `company_mappings`
- `country_mappings`

These tables are not cleared when a new trade file is uploaded. New files reuse the approved master mappings and only ask for review when a genuinely new or low-confidence alias appears.

On app startup, the seed CSV files are loaded into the mapping tables as approved master defaults. This gives the POC a simple configuration lifecycle:

```text
Review alias
-> confirm/edit master value
-> save to SQLite mapping table
-> sync to seed CSV defaults
-> future uploads reuse automatically
```

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
