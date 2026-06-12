# First Grow Process: Duloxetine Customer Pitch Pilot

This is the first practical process for Shodhana AI.

The goal is:

```text
For Duloxetine, create customer-specific pitches for priority customers using Shodhana knowledge + customer/market data.
```

Do not start with every product. Start with Duloxetine API and Duloxetine Pellets.

## 1. What We Are Building First

We are building the first **Grow** workflow:

```text
Customer data -> Opportunity score -> Customer-specific pitch -> Review by Shodhana team -> Send/Present
```

The output for each customer should be:

- Customer opportunity note
- Product fitment summary
- Email draft
- Powerful PPT outline
- Recommended next action

Later, the same workflow can generate an actual PPT file.

## 2. Who To Speak With At Shodhana

Collect information from these people or teams:

| Team / Person | What To Collect |
|---|---|
| Management / CEO | Business goal, management style, target regions, strategic customers |
| Business Development / Sales | Existing customers, target customers, follow-up style, email examples |
| Product / Technical | Duloxetine API and Pellets strengths, limitations, process capability |
| Regulatory / QA | DMF, CEP, filings, audits, cGMP, certificates, approved claims |
| Manufacturing / Plant | Capacity, batch size, scale-up, supply reliability, facility strengths |
| Purchase / Market Intelligence | Competitor suppliers, pricing, export/import insights |
| Salesforce / CRM Team | Existing customer records and opportunity stages |

## 3. What To Collect Now

### A. Shodhana Company Knowledge

Collect:

- Company profile
- Corporate brochure
- Facility details
- Manufacturing sites
- R&D capability
- Quality systems
- Regulatory approvals
- Certifications
- CDMO capability
- Existing product list
- Existing corporate pitch deck
- Approved language that Shodhana uses with customers

Put this in:

```text
data/knowledge/
```

### B. Duloxetine Product Knowledge

Collect separately for:

- Duloxetine Hydrochloride API
- Duloxetine Pellets
- Duloxetine intermediates, if relevant

For each product collect:

- Product name
- Product type
- Therapeutic category
- CAS number
- Commercial status
- Regulatory support
- DMF/CEP details
- Countries/markets filed
- Capacity
- Batch size
- Manufacturing strengths
- Quality advantages
- Supply reliability points
- Competitor comparison
- What should not be claimed

Use this template:

```text
data/knowledge/product_knowledge_template.md
```

### C. Customer And Market Data

For every potential customer collect:

- Company name
- Region
- Country
- Product interest: Duloxetine API / Pellets / CDMO
- Buyer type: API buyer / formulation company / CDMO prospect / competitor
- Estimated volume
- Estimated price
- Current supplier, if known
- Competitor supplying them
- Whether Shodhana already supplies them
- Buying trend: growing / stable / reducing
- Last purchase date, if known
- Contact person, if approved
- Notes from sales team

Put structured rows in:

```text
data/imports/duloxetine_market.csv
```

Use this template:

```text
data/imports/customer_pitch_intake.csv
```

### D. Approved Pitch Examples

Collect:

- Best old introductory emails
- Best follow-up emails
- Best product pitch decks
- Best CDMO pitch decks
- Successful customer conversion examples
- Lost opportunity examples

These examples are important because they teach the AI Shodhana's tone and pitch style.

## 4. The Process Step By Step

### Step 1: Build Shodhana Knowledge

Input:

- Public website
- Internal profile
- Brochure
- Approvals
- Facility and product documents

Action:

- Put files into `data/knowledge/`
- Click `Ingest Knowledge`

Output:

- AI can answer: "Who is Shodhana and why should a pharma company work with them?"

### Step 2: Build Duloxetine Product Knowledge

Input:

- Duloxetine API profile
- Duloxetine Pellets profile
- Regulatory details
- Manufacturing/capacity details

Output:

- AI knows what to highlight for API customers vs Pellets customers.

### Step 3: Import Customer/Market Data

Input:

- ChemGenXia
- API-FDF
- Export/import data
- Internal customer data
- Competitor price/supplier data

Action:

- Add rows to `data/imports/duloxetine_market.csv`
- Click `Import CSV`

Output:

- Top opportunity list
- Tier 1 / Tier 2 customers
- Customers to avoid

### Step 4: Score Customers

The system should classify each customer:

- Tier 1: strategic high-volume customer
- Tier 2: high-potential growing customer
- Tier 3: existing customer expansion
- Tier 4: low priority
- Tier 5: competitor / unsuitable

### Step 5: Generate First Pitch

For each customer, generate:

- Why this customer matters
- What product to pitch
- Why Shodhana is relevant
- What proof points to show
- Email draft
- PPT outline
- Next action

### Step 6: Staff Review

Before sending anything externally, Shodhana staff must review:

- Is every claim true?
- Are regulatory claims correct?
- Is capacity correct?
- Is the product fit correct?
- Is this customer worth approaching?
- Should price or competitor information be removed?

### Step 7: Improve The Knowledge

Every review should improve the system.

When staff corrects a pitch, save the corrected version as an approved example.

Later, these approved examples can be used for fine-tuning or style training.

## 5. How To Demo This To Shodhana

Use this demo flow:

1. Open dashboard
2. Show `Knowledge Chunks`
3. Ask: `Tell me about Shodhana company`
4. Click `Import CSV`
5. Show `Top Opportunities`
6. Explain Tier 1/Tier 2 scoring
7. Click `Pitch` for a Tier 1 customer
8. Show output:
   - opportunity note
   - product fit
   - email draft
   - PPT outline
9. Say:

```text
This is currently a Duloxetine pilot. Once Shodhana provides internal product, regulatory, customer, and competitor data, the pitch becomes much more powerful and customer-specific.
```

## 6. What Makes The Pitch Powerful

A strong customer-specific pitch needs five things:

1. **Customer insight**: what the customer buys, region, size, trend
2. **Product fit**: why Duloxetine API or Pellets fits them
3. **Shodhana proof**: regulatory, quality, capacity, R&D, vertical integration
4. **Competitor angle**: who supplies them now and where Shodhana can win
5. **Clear next action**: meeting, sample, technical package, regulatory discussion

If any of these are missing, the pitch will be generic.

## 7. What To Ask Shodhana In The Next Meeting

Ask these questions:

1. Which 10 Duloxetine customers should we test first?
2. Which 5 competitors should we track for Duloxetine?
3. What are Shodhana's strongest Duloxetine proof points?
4. What regulatory claims are approved to mention?
5. What capacity or supply strengths can we mention?
6. Which regions are highest priority?
7. Do they want API pitch, Pellets pitch, or CDMO pitch for each customer?
8. Can they provide 3 good old emails and 1 good pitch deck?
9. Who will approve AI-generated pitch before external use?

## 8. First Deliverable

The first real deliverable should be:

```text
Top 10 Duloxetine customer pitch pack
```

For each customer:

- Score and tier
- Reason to target
- Product to pitch
- Email draft
- PPT outline
- Missing data
- Review status

