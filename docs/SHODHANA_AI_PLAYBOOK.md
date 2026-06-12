# Shodhana AI Playbook

This document explains what we are building, why it is called AI, how to demo it, and how to grow it into a strong product.

## 1. What Shodhana AI Is

Shodhana AI should be positioned as:

```text
A pharma sales intelligence and pitch automation platform for Shodhana.
```

It is not just a chatbot.

It should help the team:

- Understand Shodhana's strengths
- Understand a pilot product, starting with Duloxetine
- Read public and internal company/product knowledge
- Analyze customer and market data
- Score customer opportunities
- Generate a customer-specific pitch
- Suggest next actions for the sales team

## 2. Why This Is AI

There are three layers:

```text
AI model + Shodhana knowledge + business rules/scoring = Shodhana AI
```

### AI Model

The AI model is the large language model. It can write, summarize, compare, reason, and generate pitch content.

In the current MVP:

- If no AI API key is connected, the app runs in local search/rule mode.
- If an AI API key is connected, the app can generate stronger answers and pitch drafts.

So the current app is an AI-ready pilot. To make it feel like real AI, connect an LLM API and provide good Shodhana knowledge.

### Shodhana Knowledge

The model does not automatically know private Shodhana information.

You must provide:

- Company profile
- Product details
- Approvals
- Facility details
- Capacity
- Customer data
- Competitor data
- Export/import data
- Existing pitch decks

This is what makes it Shodhana AI instead of generic ChatGPT.

### Scoring

Scoring ranks customers by opportunity.

For example:

- Buyer: higher score
- Growing demand: higher score
- High volume: higher score
- Existing customer: cross-sell opportunity
- Competitor: avoid or handle carefully

The AI then uses this score to decide who to focus on first.

## 3. Do We Need To Train A Model Now?

Not first.

The correct first step is RAG.

RAG means:

```text
The AI searches Shodhana documents first, then answers using that knowledge.
```

This is faster, cheaper, safer, and better for a pilot.

Fine-tuning comes later.

Fine-tuning is useful only after Shodhana has many approved examples, such as:

- Approved pitch emails
- Approved customer presentations
- Approved opportunity notes
- Approved follow-up emails
- Approved management summaries

Do not fine-tune before you have quality examples. Otherwise the model will learn weak or wrong patterns.

## 4. Where To Provide Knowledge

Put knowledge files here:

```text
data/knowledge/
```

The app currently accepts:

- `.md`
- `.txt`
- `.csv`

Recommended files:

```text
data/knowledge/company_profile.md
data/knowledge/duloxetine_api_profile.md
data/knowledge/duloxetine_pellets_profile.md
data/knowledge/regulatory_approvals.md
data/knowledge/facility_capacity.md
data/knowledge/competitor_notes.md
data/knowledge/approved_pitch_language.md
```

After adding files, click:

```text
Ingest Knowledge
```

## 5. Where To Provide Customer And Market Data

Put Duloxetine market data here:

```text
data/imports/duloxetine_market.csv
```

Then click:

```text
Import CSV
```

Minimum columns:

```text
company,region,country,product,role,estimated_volume_kg,estimated_price_usd_kg,competitor_supplier,current_shodhana_customer,last_purchase_date,trend,notes
```

This data can come from:

- ChemGenXia
- API-FDF
- export/import data
- internal sales data
- competitor shipment data
- manually prepared pilot sheet

## 6. Pilot Product: Duloxetine

For the pilot, focus only on:

- Duloxetine Hydrochloride API
- Duloxetine Pellets
- Duloxetine intermediates, if useful for positioning

Do not start with every product.

First prove:

```text
For Duloxetine, Shodhana AI can identify targets, explain why they matter, and generate a better pitch.
```

Once the Duloxetine pilot works, repeat the same framework for other products.

## 7. Phase-Wise Build Plan

### Phase 0: Understand Shodhana

Goal:

The AI should answer:

```text
What is Shodhana, what are its strengths, and why should a global pharma company work with Shodhana?
```

Inputs:

- Website
- Company profile
- Brochures
- Product list
- Approvals
- Facility and capacity data

Output:

- Company knowledge base
- Corporate pitch language
- CDMO pitch language
- API/pellets positioning

### Phase 1: Duloxetine Product Knowledge

Goal:

The AI should understand Duloxetine API and Pellets.

Inputs:

- Product profile
- CAS number
- Regulatory support
- DMF/CEP details
- Markets filed
- Intermediates
- Strengths over competitors
- Product-specific limitations

Output:

- Product facts
- Product positioning
- Product pitch angle

### Phase 2: Market And Competitor Data

Goal:

The system should know who is buying and who is supplying.

Inputs:

- ChemGenXia/API-FDF/export data
- Customer names
- Competitor names
- Region
- Price
- Volume
- Trend

Output:

- Buyer list
- Competitor list
- Region-wise opportunity
- Lost/gained business signals

### Phase 3: Customer Scoring

Goal:

Rank customers so the sales team knows who to focus on.

Output:

- Tier 1: immediate business development focus
- Tier 2: high-potential customer
- Tier 3: existing customer expansion
- Tier 4: low priority
- Tier 5: avoid or review carefully

### Phase 4: Customer-Specific Pitch

Goal:

Generate a pitch that feels made for that customer.

The pitch should include:

- Why this customer is relevant
- What product to pitch
- What Shodhana strength to highlight
- What not to pitch
- Email draft
- PPT outline
- Next action

### Phase 5: Powerful PPT Generation

Goal:

Create a polished customer-specific presentation.

For a customer interested in Duloxetine API, the deck should include:

1. Customer opportunity summary
2. Shodhana overview
3. Duloxetine API capability
4. Regulatory and quality strength
5. Supply reliability and vertical integration
6. Why Shodhana is a strong fit
7. Suggested discussion points
8. Next steps

Important:

The AI should not invent facts. It must only use verified knowledge.

### Phase 6: Email And Salesforce Automation

Goal:

Reduce manual work.

Future features:

- Email summaries
- Action item extraction
- Follow-up reminders
- Draft replies
- Customer-wise communication history
- Salesforce opportunity updates

### Phase 7: Scale To Other Products

After Duloxetine works, repeat for:

- Product 2
- Product 3
- Product 4

Each product needs:

- Product knowledge
- Market data
- Competitor data
- Customer data
- Pitch strategy

## 8. What The Demo Should Show

Do not demo it as a finished enterprise system.

Demo it as:

```text
A working Duloxetine AI pilot that proves the business workflow.
```

Suggested demo flow:

1. Show the dashboard
2. Click Import Website
3. Ask: "Tell me about Shodhana company"
4. Click Import CSV
5. Show Top Opportunities
6. Explain scoring
7. Click Pitch for a Tier 1 customer
8. Show generated pitch
9. Explain what internal data is still needed
10. Present the next 30-60-90 day roadmap

## 9. What Is Missing For A Strong Real Product

Current MVP has:

- Public website import
- Knowledge ingestion
- Duloxetine CSV import
- Customer scoring
- Basic pitch generation
- Dashboard UI

To make it strong, add:

- Real Shodhana internal knowledge
- Real Duloxetine market data
- AI model API connection
- PPT generation
- Approval workflow
- User login
- Database backend
- Salesforce/email integration
- Human review before sending anything externally

## 10. Simple Explanation For The Client

Use this wording:

```text
This pilot is not a generic chatbot. It is the first version of a Shodhana-specific pharma sales intelligence system.

The AI first learns from Shodhana's public and internal knowledge. Then it combines that with Duloxetine market data to identify target customers, rank opportunities, and generate customer-specific pitches.

We are starting with Duloxetine because it is a focused pilot product. Once the workflow is proven, we can repeat the same model across other products.
```

