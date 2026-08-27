"""GICS Sub-Industry -> ``schema/reference.ttl`` ``:Industry`` rollup table.

WHY THIS EXISTS (Gap G5): ``reference.ttl``'s 26 ``:Ind_*`` individuals sit at
the GICS Industry-Group tier for every sector except Energy (which uses the
Industry tier -- ``07-ontology-topology.md`` / ``reference.ttl``'s own comments
flag this as a pre-existing inconsistency, not something this ETL invented or
silently "fixed"). The Wikipedia S&P 500 table gives Sub-Industry (a finer
tier: ~127 distinct values currently in use), never Industry-Group directly.
This table is the missing rollup, built from the public GICS classification
structure and verified against every Sub-Industry string present in the live
Wikipedia table as of 2026-08-26 -- not reconstructed from memory the way
``reference.ttl``'s own taxonomy was.

If Wikipedia's table ever adds a Sub-Industry not in this dict (a GICS revision,
or a new constituent in a sub-industry not currently represented),
:func:`lookup` returns ``None`` rather than guessing -- the caller skips
``classifiedAs`` for that Asset and logs it. ``classifiedAs`` is NOT
SHACL-required (see ``AssetShape`` in ``shapes.ttl``: only
``tickerSymbol``/``cikNumber`` are ``sh:minCount 1``), so an unmapped
sub-industry degrades gracefully instead of blocking the whole batch.
"""

from __future__ import annotations

# Sub-Industry (Wikipedia's exact string) -> reference.ttl :Ind_* local name
SUB_INDUSTRY_TO_INDUSTRY = {
    # --- Energy ---
    "Oil & Gas Equipment & Services": "Ind_EnergyEquipServices",
    "Integrated Oil & Gas": "Ind_OilGasConsumableFuels",
    "Oil & Gas Exploration & Production": "Ind_OilGasConsumableFuels",
    "Oil & Gas Refining & Marketing": "Ind_OilGasConsumableFuels",
    "Oil & Gas Storage & Transportation": "Ind_OilGasConsumableFuels",
    # --- Materials (single reference.ttl Industry covers the whole sector) ---
    "Commodity Chemicals": "Ind_Materials",
    "Construction Materials": "Ind_Materials",
    "Copper": "Ind_Materials",
    "Fertilizers & Agricultural Chemicals": "Ind_Materials",
    "Gold": "Ind_Materials",
    "Industrial Gases": "Ind_Materials",
    "Metal, Glass & Plastic Containers": "Ind_Materials",
    "Paper & Plastic Packaging Products & Materials": "Ind_Materials",
    "Specialty Chemicals": "Ind_Materials",
    "Steel": "Ind_Materials",
    # --- Industrials: Capital Goods ---
    "Aerospace & Defense": "Ind_CapitalGoods",
    "Agricultural & Farm Machinery": "Ind_CapitalGoods",
    "Building Products": "Ind_CapitalGoods",
    "Construction & Engineering": "Ind_CapitalGoods",
    "Construction Machinery & Heavy Transportation Equipment": "Ind_CapitalGoods",
    "Electrical Components & Equipment": "Ind_CapitalGoods",
    "Heavy Electrical Equipment": "Ind_CapitalGoods",
    "Industrial Conglomerates": "Ind_CapitalGoods",
    "Industrial Machinery & Supplies & Components": "Ind_CapitalGoods",
    "Trading Companies & Distributors": "Ind_CapitalGoods",
    # --- Industrials: Commercial & Professional Services ---
    "Diversified Support Services": "Ind_CommercialServices",
    "Environmental & Facilities Services": "Ind_CommercialServices",
    "Human Resource & Employment Services": "Ind_CommercialServices",
    "Research & Consulting Services": "Ind_CommercialServices",
    # Confirmed via the sector_matches() cross-check against the live Wikipedia row
    # (ticker BR / Broadridge): this sub-industry's own GICS Sector is Industrials,
    # not Information Technology -- corrected from an initial IT-sector guess.
    "Data Processing & Outsourced Services": "Ind_CommercialServices",
    # --- Industrials: Transportation ---
    "Air Freight & Logistics": "Ind_Transportation",
    "Passenger Airlines": "Ind_Transportation",
    "Rail Transportation": "Ind_Transportation",
    "Cargo Ground Transportation": "Ind_Transportation",
    "Passenger Ground Transportation": "Ind_Transportation",
    # --- Consumer Discretionary: Automobiles & Components ---
    "Automobile Manufacturers": "Ind_Automobiles",
    "Automotive Parts & Equipment": "Ind_Automobiles",
    # --- Consumer Discretionary: Consumer Durables & Apparel ---
    "Apparel, Accessories & Luxury Goods": "Ind_ConsumerDurables",
    "Footwear": "Ind_ConsumerDurables",
    "Homebuilding": "Ind_ConsumerDurables",
    "Leisure Products": "Ind_ConsumerDurables",
    "Consumer Electronics": "Ind_ConsumerDurables",
    # --- Consumer Discretionary: Consumer Services ---
    "Casinos & Gaming": "Ind_ConsumerServices",
    "Hotels, Resorts & Cruise Lines": "Ind_ConsumerServices",
    "Restaurants": "Ind_ConsumerServices",
    "Specialized Consumer Services": "Ind_ConsumerServices",
    # --- Consumer Discretionary: Consumer Discretionary Distribution & Retail ---
    "Distributors": "Ind_ConsumerDiscRetail",
    "Broadline Retail": "Ind_ConsumerDiscRetail",
    "Apparel Retail": "Ind_ConsumerDiscRetail",
    "Computer & Electronics Retail": "Ind_ConsumerDiscRetail",
    "Home Improvement Retail": "Ind_ConsumerDiscRetail",
    "Other Specialty Retail": "Ind_ConsumerDiscRetail",
    "Automotive Retail": "Ind_ConsumerDiscRetail",
    "Homefurnishing Retail": "Ind_ConsumerDiscRetail",
    # --- Consumer Staples: Consumer Staples Distribution & Retail ---
    "Consumer Staples Merchandise Retail": "Ind_ConsumerStaplesRetail",
    "Food Distributors": "Ind_ConsumerStaplesRetail",
    "Food Retail": "Ind_ConsumerStaplesRetail",
    # --- Consumer Staples: Food, Beverage & Tobacco ---
    "Brewers": "Ind_FoodBeverageTobacco",
    "Distillers & Vintners": "Ind_FoodBeverageTobacco",
    "Soft Drinks & Non-alcoholic Beverages": "Ind_FoodBeverageTobacco",
    "Agricultural Products & Services": "Ind_FoodBeverageTobacco",
    "Packaged Foods & Meats": "Ind_FoodBeverageTobacco",
    "Tobacco": "Ind_FoodBeverageTobacco",
    # --- Consumer Staples: Household & Personal Products ---
    "Household Products": "Ind_HouseholdPersonalProds",
    "Personal Care Products": "Ind_HouseholdPersonalProds",
    # --- Health Care: Health Care Equipment & Services ---
    "Health Care Equipment": "Ind_HealthCareEquipServices",
    "Health Care Supplies": "Ind_HealthCareEquipServices",
    "Health Care Distributors": "Ind_HealthCareEquipServices",
    "Health Care Services": "Ind_HealthCareEquipServices",
    "Health Care Facilities": "Ind_HealthCareEquipServices",
    "Managed Health Care": "Ind_HealthCareEquipServices",
    "Health Care Technology": "Ind_HealthCareEquipServices",
    # --- Health Care: Pharmaceuticals, Biotechnology & Life Sciences ---
    "Biotechnology": "Ind_PharmaBiotechLifeSci",
    "Pharmaceuticals": "Ind_PharmaBiotechLifeSci",
    "Life Sciences Tools & Services": "Ind_PharmaBiotechLifeSci",
    # --- Financials: Banks ---
    "Diversified Banks": "Ind_Banks",
    "Regional Banks": "Ind_Banks",
    # --- Financials: Financial Services ---
    "Multi-Sector Holdings": "Ind_FinancialServices",
    "Consumer Finance": "Ind_FinancialServices",
    "Asset Management & Custody Banks": "Ind_FinancialServices",
    "Investment Banking & Brokerage": "Ind_FinancialServices",
    "Financial Exchanges & Data": "Ind_FinancialServices",
    "Transaction & Payment Processing Services": "Ind_FinancialServices",
    # --- Financials: Insurance ---
    "Insurance Brokers": "Ind_Insurance",
    "Life & Health Insurance": "Ind_Insurance",
    "Multi-line Insurance": "Ind_Insurance",
    "Property & Casualty Insurance": "Ind_Insurance",
    "Reinsurance": "Ind_Insurance",
    # --- Information Technology: Software & Services ---
    "Application Software": "Ind_SoftwareServices",
    "Systems Software": "Ind_SoftwareServices",
    "IT Consulting & Other Services": "Ind_SoftwareServices",
    "Internet Services & Infrastructure": "Ind_SoftwareServices",
    # --- Information Technology: Technology Hardware & Equipment ---
    "Communications Equipment": "Ind_TechHardwareEquip",
    "Technology Hardware, Storage & Peripherals": "Ind_TechHardwareEquip",
    "Electronic Equipment & Instruments": "Ind_TechHardwareEquip",
    "Electronic Components": "Ind_TechHardwareEquip",
    "Electronic Manufacturing Services": "Ind_TechHardwareEquip",
    "Technology Distributors": "Ind_TechHardwareEquip",
    # --- Information Technology: Semiconductors & Semiconductor Equipment ---
    "Semiconductors": "Ind_Semiconductors",
    "Semiconductor Materials & Equipment": "Ind_Semiconductors",
    # --- Communication Services: Telecommunication Services ---
    "Integrated Telecommunication Services": "Ind_TelecomServices",
    "Wireless Telecommunication Services": "Ind_TelecomServices",
    # --- Communication Services: Media & Entertainment ---
    "Advertising": "Ind_MediaEntertainment",
    "Broadcasting": "Ind_MediaEntertainment",
    "Cable & Satellite": "Ind_MediaEntertainment",
    "Publishing": "Ind_MediaEntertainment",
    "Movies & Entertainment": "Ind_MediaEntertainment",
    "Interactive Home Entertainment": "Ind_MediaEntertainment",
    "Interactive Media & Services": "Ind_MediaEntertainment",
    # --- Utilities (single reference.ttl Industry covers the whole sector) ---
    "Electric Utilities": "Ind_Utilities",
    "Gas Utilities": "Ind_Utilities",
    "Multi-Utilities": "Ind_Utilities",
    "Water Utilities": "Ind_Utilities",
    "Independent Power Producers & Energy Traders": "Ind_Utilities",
    # --- Real Estate: Equity REITs ---
    "Industrial REITs": "Ind_EquityREITs",
    "Hotel & Resort REITs": "Ind_EquityREITs",
    "Office REITs": "Ind_EquityREITs",
    "Health Care REITs": "Ind_EquityREITs",
    "Multi-Family Residential REITs": "Ind_EquityREITs",
    "Single-Family Residential REITs": "Ind_EquityREITs",
    "Retail REITs": "Ind_EquityREITs",
    "Data Center REITs": "Ind_EquityREITs",
    "Self-Storage REITs": "Ind_EquityREITs",
    "Telecom Tower REITs": "Ind_EquityREITs",
    "Timber REITs": "Ind_EquityREITs",
    "Other Specialized REITs": "Ind_EquityREITs",
    # --- Real Estate: Real Estate Management & Development ---
    "Real Estate Services": "Ind_RealEstateMgmtDev",
}

# reference.ttl :Ind_* local name -> reference.ttl :Sec_* local name, used
# only as a runtime cross-check against the Wikipedia row's own GICS Sector
# column (defense against a mapping typo above, not load-bearing logic).
INDUSTRY_TO_SECTOR = {
    "Ind_EnergyEquipServices": "Sec_Energy",
    "Ind_OilGasConsumableFuels": "Sec_Energy",
    "Ind_Materials": "Sec_Materials",
    "Ind_CapitalGoods": "Sec_Industrials",
    "Ind_CommercialServices": "Sec_Industrials",
    "Ind_Transportation": "Sec_Industrials",
    "Ind_Automobiles": "Sec_ConsumerDiscretionary",
    "Ind_ConsumerDurables": "Sec_ConsumerDiscretionary",
    "Ind_ConsumerServices": "Sec_ConsumerDiscretionary",
    "Ind_ConsumerDiscRetail": "Sec_ConsumerDiscretionary",
    "Ind_ConsumerStaplesRetail": "Sec_ConsumerStaples",
    "Ind_FoodBeverageTobacco": "Sec_ConsumerStaples",
    "Ind_HouseholdPersonalProds": "Sec_ConsumerStaples",
    "Ind_HealthCareEquipServices": "Sec_HealthCare",
    "Ind_PharmaBiotechLifeSci": "Sec_HealthCare",
    "Ind_Banks": "Sec_Financials",
    "Ind_FinancialServices": "Sec_Financials",
    "Ind_Insurance": "Sec_Financials",
    "Ind_SoftwareServices": "Sec_InformationTechnology",
    "Ind_TechHardwareEquip": "Sec_InformationTechnology",
    "Ind_Semiconductors": "Sec_InformationTechnology",
    "Ind_TelecomServices": "Sec_CommunicationServices",
    "Ind_MediaEntertainment": "Sec_CommunicationServices",
    "Ind_Utilities": "Sec_Utilities",
    "Ind_EquityREITs": "Sec_RealEstate",
    "Ind_RealEstateMgmtDev": "Sec_RealEstate",
}

# Wikipedia's "GICS Sector" column string -> reference.ttl :Sec_* local name
# (verified identical to articles.gics_sector strings in urls.db too).
SECTOR_LOCAL_NAME = {
    "Energy": "Sec_Energy",
    "Materials": "Sec_Materials",
    "Industrials": "Sec_Industrials",
    "Consumer Discretionary": "Sec_ConsumerDiscretionary",
    "Consumer Staples": "Sec_ConsumerStaples",
    "Health Care": "Sec_HealthCare",
    "Financials": "Sec_Financials",
    "Information Technology": "Sec_InformationTechnology",
    "Communication Services": "Sec_CommunicationServices",
    "Utilities": "Sec_Utilities",
    "Real Estate": "Sec_RealEstate",
}


def lookup(sub_industry: str) -> str | None:
    """Return the ``:Ind_*`` local name, or ``None`` if unmapped (caller logs + skips)."""
    return SUB_INDUSTRY_TO_INDUSTRY.get(sub_industry)


def sector_matches(industry_local: str, wikipedia_sector: str) -> bool:
    """Cross-check a rolled-up Industry against the row's own GICS Sector column."""
    expected_sector = SECTOR_LOCAL_NAME.get(wikipedia_sector)
    return INDUSTRY_TO_SECTOR.get(industry_local) == expected_sector
