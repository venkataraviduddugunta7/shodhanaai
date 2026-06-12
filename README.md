# Shodhana AI Pilot

This is a focused MVP for the first Shodhana AI pilot: Duloxetine API and Duloxetine Pellets.

The goal is not to "train a ChatGPT clone." The first version uses a Shodhana-specific knowledge base plus structured market/customer data so the AI can:

- Explain Shodhana's strengths
- Search internal company/product knowledge
- Analyze Duloxetine market/customer data
- Score and prioritize customer opportunities
- Generate customer-specific pitch drafts
- Support the future Salesforce/email intelligence workflow

## What To Build First

Start with the pilot, not the full platform.

1. Add Shodhana documents to `data/knowledge/`
2. Add Duloxetine market/customer rows to `data/imports/duloxetine_market.csv`
3. Run the app
4. Ingest the knowledge and CSV data
5. Review the opportunity scores and generated pitches with the sales team

Once this works for Duloxetine, repeat the same structure for other products.

## Run Locally

```bash
python3 app.py
```

Then open:

```text
http://localhost:8000
```

Optional AI mode:

```bash
export OPENAI_API_KEY="your_key_here"
export OPENAI_MODEL="gpt-4o-mini"
python3 app.py
```

If no API key is configured, the app still runs in local rule-based mode.

## Import Public Website Knowledge

The app can use Shodhana's public website as an initial knowledge source.

In the dashboard, click:

```text
Import Public Website
```

This reads the public sitemap from `https://www.shodhana.com/`, imports same-domain pages, stores source URLs, writes the result to:

```text
data/knowledge/shodhana_public_website.md
```

Then it automatically reloads the knowledge chunks.

Important: public website information is useful for company/product positioning, but it is not enough for the sales intelligence pilot. You still need internal verified data such as regulatory approvals, capacity, customer lists, competitor data, and ChemGenXia/API-FDF/export data.

## How The AI Learns Shodhana

For this kind of business system, start with retrieval-augmented generation (RAG), not fine-tuning.

That means:

- Put company/product documents into the knowledge base
- Split them into searchable chunks
- Retrieve the most relevant context for each task
- Ask the model to answer only using that context and structured customer data

Fine-tuning can come later, after you have enough approved emails, pitch decks, opportunity notes, and management summaries.

## Data Needed For The Pilot

Minimum documents:

- Company profile
- Manufacturing capabilities
- Regulatory approvals and certifications
- Facility details
- Duloxetine API profile
- Duloxetine Pellets profile
- Existing corporate presentations
- Existing customer list
- Known competitor list

Minimum CSV columns:

```text
company,region,country,product,role,estimated_volume_kg,estimated_price_usd_kg,competitor_supplier,current_shodhana_customer,last_purchase_date,trend,notes
```

## MVP Modules

- Knowledge search and Q&A
- Duloxetine opportunity scoring
- Top customer prioritization
- Customer-specific pitch generation
- Data import from CSV
- Simple browser dashboard

## Planning And Demo Documents

Use these files to understand, explain, and demo the product:

- `docs/SHODHANA_AI_PLAYBOOK.md` - what Shodhana AI is, why it is AI, how RAG/training works, and the phase-wise build plan
- `docs/FIRST_GROW_PITCH_PROCESS.md` - first Grow workflow for Duloxetine customer-specific pitches
- `docs/REAL_TIME_GROW_DATA_ENGINE.md` - latest data-cleaning workflow from shipment/export Excel to target customers
- `docs/STAFF_INFORMATION_INTAKE.md` - questions to collect knowledge from Shodhana staff
- `docs/DEMO_SCRIPT.md` - step-by-step client demo script
- `docs/DATA_COLLECTION_CHECKLIST.md` - what data Shodhana must provide
- `data/knowledge/product_knowledge_template.md` - product knowledge template
- `data/knowledge/customer_pitch_brief_template.md` - customer pitch brief template
- `data/imports/customer_pitch_intake.csv` - customer pitch intake template
- `data/imports/raw_shipments_duloxetine.csv` - sample raw shipment/export data for cleanup demo
- `data/imports/product_aliases.csv` - product spelling/name normalization
- `data/imports/company_aliases.csv` - company duplicate/name normalization

## Next Build Steps

After this MVP is validated:

- Add login and role-based access
- Add PostgreSQL
- Add Salesforce integration
- Add Gmail/Outlook integration
- Add document/presentation export
- Add approval workflow before sending external emails
- Add executive dashboard
