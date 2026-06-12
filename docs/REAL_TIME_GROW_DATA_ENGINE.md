# Real-Time Grow Data Engine

This document captures the new understanding from the latest Shodhana discussion.

The first proof should not start with email automation or final PPT generation.

The first proof should be:

```text
Can Shodhana AI clean messy export/customer Excel data and identify better customers for one product?
```

Pilot product:

```text
Duloxetine API and Duloxetine Pellets
```

## 1. The Business Problem

The sales team repeatedly does the same manual work:

1. Download Excel/export data from sources such as ChemDoss/ChemGenXia/API-FDF.
2. Search for one product, such as Duloxetine.
3. Clean product names because the same product appears with different spellings.
4. Clean company names because the same company appears in different formats.
5. Remove duplicate shipment rows across sources.
6. Create pivots by customer, supplier, country, year, quantity, and price.
7. Calculate average price per KG.
8. Compare competitor prices against Shodhana's possible offer.
9. Identify which customers to target.
10. Prepare a customer-specific pitch.

This is slow, repetitive, and depends heavily on manual Excel work.

## 2. What Shodhana AI Should Prove First

For Duloxetine, the system should show:

- Which companies are importing Duloxetine from India
- Which exporters/suppliers are selling to them
- What quantity they bought
- What average price per KG they paid
- Whether they are buying from Shodhana or competitors
- Whether they are in a regulated, semi-regulated, or non-regulated market
- Which customers are target opportunities
- What product pitch should be prepared

## 3. Key Pharma Concepts Captured

### Market Categories

Countries can be grouped as:

- Regulated: US, Europe, Japan, Korea, Australia, Canada, etc.
- Semi-regulated: India, Egypt, Argentina, Bangladesh, Brazil, Indonesia, etc.
- Non-regulated: markets with lighter regulatory expectations

This matters because the pitch changes by market.

For regulated markets, lead with:

- DMF support
- cGMP
- audit readiness
- regulatory documentation
- quality systems

For non-regulated markets, price and supply reliability may matter more.

### DMF vs Non-DMF

DMF-grade material is not just a product claim.

It includes documentation and responsibility:

- Manufacturing process documentation
- Vendor and intermediate traceability
- Cleaning validation
- impurity control
- analytical method validation
- audit readiness
- response support if the customer's regulator asks questions

DMF-grade material can carry a major price premium compared with non-DMF material.

The pitch must not casually claim DMF support unless verified.

### API vs Pellets

Shodhana sells:

- API: active ingredient powder/material
- Pellets: semi-formulation stage, before final capsule/tablet

Customers are usually formulators or companies making finished dosage products.

## 4. Data Cleaning Requirements

### Product Name Normalization

The same medicine may appear as:

- Duloxetine HCL
- Duloxetine HCl
- Duloxetine Hydrochloride
- Duloxetin Hydrochloride
- Duloxetine Pellets 20%

The system should map variants to:

```text
Duloxetine HCL
Duloxetine Pellets
```

Template:

```text
data/imports/product_aliases.csv
```

### Company Name Normalization

The same company may appear as:

- Shodhana Laboratories Pvt Ltd
- Shodhana Laboratories Private Limited
- Existing Customer Ltd
- Existing Customer Limited
- Asher Pharma GmbH
- Asher Pharma GMBH

The system should group these under one canonical company.

Template:

```text
data/imports/company_aliases.csv
```

### Duplicate Removal

The same shipment may appear in two sources.

The system should detect duplicates using:

- date
- canonical product
- canonical exporter
- canonical importer
- quantity
- total value

Then it should keep one row and remove duplicate rows from analysis.

## 5. Price Analysis

For each customer and product:

```text
average price per KG = total invoice value / total quantity KG
```

Example:

If a customer bought 1,400 KG in a year across multiple shipments, the system should calculate:

```text
total value of all shipments / 1,400 KG
```

Then Shodhana can decide:

- offer slightly below competitor price to enter
- increase price if Shodhana is already selling too low
- avoid customer if volume is too small
- defend customer if competitor is also supplying

## 6. What The Dashboard Now Proves

The MVP now includes:

- `Import Shipments`
- product alias mapping
- company alias mapping
- duplicate shipment removal
- regulated/semi-regulated/non-regulated classification
- customer/product/supplier aggregation
- average price per KG
- target price suggestion
- shipment insight table

Templates:

```text
data/imports/raw_shipments_duloxetine.csv
data/imports/product_aliases.csv
data/imports/company_aliases.csv
```

## 7. Immediate Demo Flow

Use this in the next demo:

1. Open Shodhana AI dashboard.
2. Click `Import Website`.
3. Ask `Tell me about Shodhana company`.
4. Click `Import Shipments`.
5. Show that messy Duloxetine names were grouped.
6. Show that duplicate rows were removed.
7. Show customer-level insight:
   - importer
   - product
   - market category
   - quantity
   - average price
   - suppliers
   - recommended action
8. Click or generate pitch for a target customer.
9. Explain that real ChemDoss/API-FDF/IMS Excel data can replace the sample CSV.

## 8. Next Data Needed From Shodhana

Ask for:

1. One real Duloxetine export Excel from ChemDoss/ChemGenXia.
2. One API-FDF export for Duloxetine.
3. If available, one IMS sample for Duloxetine formulation sales.
4. Shodhana's own Duloxetine customer sales data.
5. Product alias list used by the sales team.
6. Company alias list or common duplicate names.
7. Shodhana's Duloxetine API price range.
8. Shodhana's Duloxetine Pellets price range.
9. Approved DMF/CEP/regulatory claims.
10. One old customer pitch/PPT for style.

## 9. Later Email Attachment Flow

Email automation should come after the Grow workflow.

When it comes, every attachment should follow this process:

```text
Email received
-> Read email metadata/body
-> Save attachment in quarantine
-> Check file type, size, extension, sender, and content
-> Virus/malware scan
-> Parse only approved Excel/PDF files
-> Ingest data into Shodhana AI
-> Human review before external response
```

Do not directly open or ingest unknown attachments.

## 10. First Real Milestone

The first milestone should be:

```text
Upload one real Duloxetine shipment Excel and produce the Top 10 target customers with average price, supplier, market category, and pitch recommendation.
```

That proves Shodhana AI is useful for business growth.

