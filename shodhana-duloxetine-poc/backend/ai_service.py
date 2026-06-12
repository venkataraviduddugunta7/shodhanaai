APPROVAL_NOTE = "AI-generated output is a draft. Sales/business team must review before sending externally."

SHODHANA_POSITIONING = (
    "Shodhana has strong experience in Duloxetine API and Duloxetine Pellets. "
    "Shodhana can support API and semi-formulation/pellet requirements, DMF/non-DMF commercial models where applicable, "
    "and can position on quality, reliability, regulatory support, and long-term supply partnership."
)


def generateCustomerSummary(opportunity):
    data = _normalize_input(opportunity)
    opp = data["opportunity"]
    return "\n".join(
        [
            f"Customer/importer: {_text(opp.get('importer'))}",
            f"Country: {_text(opp.get('country'))}",
            f"Product category: {_text(opp.get('product'))}",
            f"Total quantity purchased: {_quantity(opp.get('total_quantity_kg'))}",
            f"Total value: {_money(opp.get('total_value_usd'))}",
            f"Average price/kg: {_money(opp.get('avg_price_per_kg'))}",
            f"Number of shipments: {_number(opp.get('shipment_count'))}",
            f"First shipment date: {_text(opp.get('first_shipment_date'))}",
            f"Last shipment date: {_text(opp.get('last_shipment_date'))}",
            f"Current observed supplier/exporter: {_text(opp.get('current_supplier') or opp.get('exporter'))}",
            f"Shodhana status: {_text(opp.get('shodhana_status'))}",
        ]
    )


def generateBuyingPattern(opportunity):
    data = _normalize_input(opportunity)
    opp = data["opportunity"]
    reasons = set(opp.get("reasons") or data.get("why_important") or [])
    price_difference = _float(opp.get("price_difference"))
    market_avg = _float(opp.get("market_avg_price_per_kg"))
    avg_price = _float(opp.get("avg_price_per_kg"))
    shipment_count = int(_float(opp.get("shipment_count")))
    status = opp.get("shodhana_status") or ""

    volume = "high-volume buyer" if "High quantity buyer" in reasons else "lower or emerging volume buyer"
    recency = "recent purchase activity is visible" if "Recent purchase activity" in reasons else "recent activity is not the strongest signal"
    repetition = "buying appears repeated" if shipment_count > 1 else "buying appears to be a one-off or limited shipment pattern"
    supplier = "currently buying from a competitor" if status != "Existing Shodhana Supply" else "already has observed Shodhana supply"
    if market_avg and avg_price:
        price = "above market average" if price_difference > 0 else "below market average"
        price_line = f"The observed average price/kg is {price} by {_money(abs(price_difference))}."
    else:
        price_line = "Price comparison should be reviewed because market average or customer price is incomplete."

    return (
        f"This customer is a {volume}. The trade data indicates that {recency}, and {repetition}. "
        f"The account is {supplier}. {price_line}"
    )


def generateCurrentSupplier(opportunity):
    data = _normalize_input(opportunity)
    opp = data["opportunity"]
    supplier = _text(opp.get("current_supplier") or opp.get("exporter"))
    status = _text(opp.get("shodhana_status"))
    product = _text(opp.get("product"))
    country = _text(opp.get("country"))
    return (
        f"Observed supplier/exporter: {supplier}. The account is classified as {status} for {product} in {country}. "
        "Sales should verify whether this supplier is the customer's current preferred source, spot supplier, or historical supplier before outreach."
    )


def generatePriceAnalysis(opportunity):
    data = _normalize_input(opportunity)
    opp = data["opportunity"]
    price = data.get("price_analysis") or {}
    customer_avg = _float(price.get("customer_avg_price_per_kg") or opp.get("avg_price_per_kg"))
    market_avg = _float(price.get("market_avg_price_per_kg") or opp.get("market_avg_price_per_kg"))
    difference = customer_avg - market_avg if customer_avg and market_avg else _float(opp.get("price_difference"))
    direction = "above" if difference > 0 else "below"
    if not customer_avg or not market_avg:
        return (
            "Customer and market price signals are incomplete. Use the available price/kg only as an internal benchmark, "
            "then validate grade, quantity, documentation, delivery terms, and freight assumptions before any commercial discussion."
        )
    return (
        f"Customer average price/kg is {_money(customer_avg)} against market average {_money(market_avg)}. "
        f"This is {direction} market average by {_money(abs(difference))}. "
        f"Observed product-market range is {_money(price.get('market_min_price_per_kg'))} to {_money(price.get('market_max_price_per_kg'))}. "
        "This should be used as a negotiation benchmark, not a final confirmed price."
    )


def generatePriceStrategy(opportunity):
    data = _normalize_input(opportunity)
    opp = data["opportunity"]
    product = opp.get("product") or "Duloxetine"
    status = opp.get("shodhana_status") or "Competitor Supply"
    price_difference = _float(opp.get("price_difference"))
    product_note = (
        "Because this is a pellets opportunity, position Shodhana's semi-formulation/pellet capability, technical support, and supply reliability."
        if "PELLET" in product.upper()
        else "Because this is an API opportunity, position Shodhana's Duloxetine API manufacturing strength, documentation support, and reliable supply."
    )

    if status == "Existing Shodhana Supply":
        strategy = (
            "This is a retention and expansion account. Recommend protecting the relationship, checking whether the customer is also buying from competitors, "
            "and exploring cross-sell, continuity supply, or price optimization after validating actual demand."
        )
    elif price_difference > 0:
        strategy = (
            "Competitor average price appears higher than market average. Shodhana can explore a commercially competitive offer with slightly better commercial terms "
            "while protecting margin. Price discussion can be aligned after requirement validation and should be reviewed by the business team."
        )
    else:
        strategy = (
            "Competitor price appears at or below market average. Avoid a price war. Lead with quality, regulatory support, reliability, lead time, documentation readiness, "
            "and long-term partnership. Suggested pricing should be reviewed by the business team after validating specification and order size."
        )

    return f"{strategy}\n\n{product_note}\n\nDo not quote a final confirmed price from this system."


def generateWhyTarget(opportunity):
    data = _normalize_input(opportunity)
    opp = data["opportunity"]
    reasons = opp.get("reasons") or data.get("why_important") or []
    if not reasons:
        reasons = ["Visible Duloxetine buying activity", "Potential account for monitoring"]
    return (
        f"Shodhana should target this account because the data shows: {', '.join(reasons)}. "
        f"The opportunity score is {_number(opp.get('score'))}/100 and the account is classified as {_text(opp.get('opportunity_category') or opp.get('tier'))}."
    )


def generatePitchEmail(opportunity):
    data = _normalize_input(opportunity)
    opp = data["opportunity"]
    customer = _text(opp.get("importer"), "Customer")
    country = _text(opp.get("country"), "your market")
    product = _text(opp.get("product"), "Duloxetine API / Pellets")
    supplier = _text(opp.get("current_supplier") or opp.get("exporter"), "current supplier")
    subject = "Duloxetine API / Pellets Supply Opportunity from Shodhana Laboratories"
    product_capability = _product_capability(product)

    formal = f"""Subject: {subject}

Dear {customer} Team,

Greetings from Shodhana Laboratories.

We understand that your organization is active in {product} sourcing for {country}. Shodhana would be pleased to explore whether we can support your Duloxetine requirements with a reliable, quality-focused, and commercially suitable supply model.

{product_capability}

Shodhana can support API and semi-formulation/pellet requirements, with DMF/non-DMF commercial models where applicable. We can also support discussions around quality documentation, regulatory expectations, supply continuity, and long-term partnership.

We would be happy to understand your current requirement, target specification, documentation needs, and expected volumes before sharing a suitable commercial proposal.

Could we schedule a short call to discuss this opportunity?

Regards,
Shodhana Business Development"""

    short = f"""Subject: {subject}

Dear {customer} Team,

We would like to explore supply support for your {product} requirements in {country}.

Shodhana has strong experience in Duloxetine API and Pellets, with quality, regulatory, and supply reliability support. We can discuss a commercially competitive offer after validating your grade, documentation, and volume requirements.

Would you be open to a short call this week?

Regards,
Shodhana Business Development"""

    relationship = f"""Subject: {subject}

Dear {customer} Team,

I hope you are doing well.

We are reaching out from Shodhana Laboratories to explore whether we can support your future {product} sourcing plans. Based on market activity, your team appears to be active in this product area, and we would value the opportunity to understand your requirements more closely.

Shodhana can support Duloxetine API and Pellets with a focus on quality, reliability, regulatory support, and long-term supply partnership. If you are currently evaluating alternatives to {supplier}, we would be glad to discuss how Shodhana may fit your technical and commercial expectations.

Could we arrange a brief introductory discussion and share a focused capability presentation?

Regards,
Shodhana Business Development"""

    return {"subject": subject, "formal": formal, "short": short, "relationship": relationship}


def generatePptOutline(opportunity):
    data = _normalize_input(opportunity)
    opp = data["opportunity"]
    customer = _text(opp.get("importer"), "Target customer")
    product = _text(opp.get("product"), "Duloxetine")
    status = _text(opp.get("shodhana_status"))
    supplier = _text(opp.get("current_supplier") or opp.get("exporter"))
    country = _text(opp.get("country"))

    return [
        {
            "title": "Shodhana Introduction",
            "bullets": [
                "Overview of Shodhana Laboratories",
                "Experience in regulated pharmaceutical supply",
                "Focus on quality, reliability, and long-term customer partnership",
                f"Purpose of discussion with {customer}",
            ],
            "speaker_note": f"Introduce Shodhana as a serious supply partner for {customer}, not as a generic vendor.",
        },
        {
            "title": "Duloxetine API / Pellets Capability",
            "bullets": [
                "Strong experience in Duloxetine API and Duloxetine Pellets",
                "Support for API and semi-formulation/pellet requirements",
                "Ability to discuss customer-specific specification and grade needs",
                "Commercial model can be aligned after technical requirement validation",
            ],
            "speaker_note": f"Connect the capability directly to the observed product interest: {product}.",
        },
        {
            "title": "Quality and Regulatory Strength",
            "bullets": [
                "Quality-first supply positioning",
                "Regulatory and documentation support where applicable",
                "DMF/non-DMF commercial models can be discussed based on market need",
                "Business team review required before external commitments",
            ],
            "speaker_note": "Avoid overclaiming. Use this slide to invite requirement validation and documentation discussion.",
        },
        {
            "title": "Supply Reliability and Manufacturing Experience",
            "bullets": [
                "Reliable long-term supply partnership positioning",
                "Technical and commercial coordination for repeat business",
                "Focus on continuity, responsiveness, and practical support",
                f"Observed current supplier context: {supplier}",
            ],
            "speaker_note": f"Explain that {customer} appears to have active supply history, so reliability is central.",
        },
        {
            "title": "Commercial / Partnership Proposal",
            "bullets": [
                f"Target market: {country}",
                f"Current status: {status}",
                "Commercially competitive offer can be explored after validation",
                "Pricing should be reviewed by Shodhana business team before quotation",
                "Partnership discussion should include volume, grade, documents, and delivery expectations",
            ],
            "speaker_note": "Frame price as a business discussion, not as an automated quote.",
        },
        {
            "title": "Next Steps",
            "bullets": [
                "Confirm product grade and specification",
                "Validate annual or quarterly volume expectations",
                "Understand documentation and regulatory requirements",
                "Schedule technical-commercial call",
                "Prepare reviewed commercial proposal if fit is confirmed",
            ],
            "speaker_note": "Close with a low-friction call and a clear validation checklist.",
        },
    ]


def generateFollowUpPlan(opportunity):
    return "\n".join(
        [
            "Day 0: Send email and presentation.",
            "Day 3: Send follow-up email with a short reminder and offer to share documents/capability details.",
            "Day 7: Call, LinkedIn, or local agent follow-up to identify the right purchase/BD/regulatory contact.",
            "Day 14: Follow up on commercial proposal discussion after confirming product grade, quantity, and documentation needs.",
            "Day 30: Re-prioritize based on response, buying activity, and account fit.",
        ]
    )


def generate_pitch_package(opportunity):
    data = _normalize_input(opportunity)
    emails = generatePitchEmail(data)
    return {
        "customer_summary": generateCustomerSummary(data),
        "buying_pattern": generateBuyingPattern(data),
        "current_supplier": generateCurrentSupplier(data),
        "price_analysis": generatePriceAnalysis(data),
        "why_target": generateWhyTarget(data),
        "commercial_strategy": generatePriceStrategy(data),
        "price_strategy": generatePriceStrategy(data),
        "email_drafts": emails,
        "ppt_outline": generatePptOutline(data),
        "follow_up_plan": generateFollowUpPlan(data),
        "human_approval_note": APPROVAL_NOTE,
        "positioning": SHODHANA_POSITIONING,
    }


def pitch_package_text(package):
    return "\n\n".join(
        [
            "# Shodhana AI Customer Pitch Draft",
            "## Customer Intelligence Summary\n" + package.get("customer_summary", ""),
            "## Buying Pattern\n" + package.get("buying_pattern", ""),
            "## Current Supplier\n" + package.get("current_supplier", ""),
            "## Price Analysis\n" + package.get("price_analysis", ""),
            "## Why Shodhana Should Target\n" + package.get("why_target", ""),
            "## Recommended Commercial Strategy\n" + package.get("commercial_strategy", ""),
            "## Formal Email Draft\n" + (package.get("email_drafts") or {}).get("formal", ""),
            "## Short Direct Email Draft\n" + (package.get("email_drafts") or {}).get("short", ""),
            "## Relationship-building Email Draft\n" + (package.get("email_drafts") or {}).get("relationship", ""),
            "## PPT Outline\n" + ppt_outline_markdown(package.get("ppt_outline") or []),
            "## Follow-up Plan\n" + package.get("follow_up_plan", ""),
            package.get("human_approval_note", APPROVAL_NOTE),
        ]
    )


def ppt_outline_markdown(slides):
    blocks = []
    for index, slide in enumerate(slides, start=1):
        bullets = "\n".join(f"- {item}" for item in slide.get("bullets", []))
        blocks.append(
            f"### Slide {index}: {slide.get('title', '')}\n"
            f"{bullets}\n\n"
            f"Speaker note: {slide.get('speaker_note', '')}"
        )
    return "\n\n".join(blocks)


def generate_ai_action(action, opportunity):
    package = generate_pitch_package(opportunity)
    if action == "summary":
        return package["customer_summary"]
    if action == "price":
        return package["price_strategy"]
    if action == "ppt":
        return ppt_outline_markdown(package["ppt_outline"])
    return package["email_drafts"]["formal"]


def _normalize_input(opportunity):
    if not isinstance(opportunity, dict):
        return {"opportunity": {}}
    if "opportunity" in opportunity:
        return opportunity
    return {"opportunity": opportunity}


def _product_capability(product):
    if "PELLET" in product.upper():
        return (
            "For Duloxetine Pellets, Shodhana can position semi-formulation/pellet capability, technical understanding, "
            "quality focus, and dependable supply support."
        )
    return (
        "For Duloxetine API, Shodhana can position manufacturing strength, documentation support, quality focus, "
        "and dependable long-term supply."
    )


def _text(value, fallback="Not available"):
    text = str(value or "").strip()
    return text or fallback


def _float(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _number(value):
    number = _float(value)
    if number.is_integer():
        return f"{int(number):,}"
    return f"{number:,.2f}"


def _quantity(value):
    return f"{_number(value)} KG"


def _money(value):
    return f"${_float(value):,.2f}"
