# Section-detection validation

## Item/Part headings matched by the regex, in document order (13 total)

- [page 4] 'PART I - FINANCIAL INFORMATION'
- [page 4] 'Item 1. Financial Statements'
- [page 21] "Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations"
- [page 28] 'Item 3. Quantitative and Qualitative Disclosures About Market Risk'
- [page 28] 'Item 4. Controls and Procedures'
- [page 29] 'PART II - OTHER INFORMATION'
- [page 29] 'Item 1. Legal Proceedings'
- [page 30] 'Item 1A. Risk Factors'
- [page 36] 'Item 2. Unregistered Sales of Equity Securities and Use of Proceeds'
- [page 36] 'Item 3. Defaults Upon Senior Securities'
- [page 36] 'Item 4. Mine Safety Disclosures'
- [page 37] 'Item 5. Other Information'
- [page 37] 'Item 6. Exhibits'

## Cross-check against the filing's own Table of Contents

(best-effort substring match -- eyeball anything flagged)

- Item 1. Financial Statements 1 -> OK
- Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations 13 -> OK
- Item 3. Quantitative and Qualitative Disclosures About Market Risk 19 -> OK
- Item 4. Controls and Procedures 19 -> OK
- Item 1. Legal Proceedings 20 -> OK
- Item 1A. Risk Factors 21 -> OK
- Item 2. Unregistered Sales of Equity Securities and Use of Proceeds 24 -> OK
- Item 3. Defaults Upon Senior Securities 24 -> OK
- Item 4. Mine Safety Disclosures 24 -> OK
- Item 5. Other Information 25 -> OK
- Item 6. Exhibits 25 -> OK

## Non-noise headings that did NOT match the Item/Part regex

(expected to be mostly real sub-headings -- skim for anything that looks like it should have been Item/Part level but wasn't worded the standard way)

- [page 1] 'UNITED STATES SECURITIES AND EXCHANGE COMMISSION'
- [page 3] 'Form 10-Q'
- [page 3] 'For the Fiscal Quarter Ended June 27, 2026'
- [page 3] 'TABLE OF CONTENTS'
- [page 4] 'CONDENSED CONSOLIDATED STATEMENTS OF OPERATIONS (Unaudited)'
- [page 5] 'CONDENSED CONSOLIDATED STATEMENTS OF COMPREHENSIVE INCOME (Unaudited) (In millions)'
- [page 6] 'CONDENSED CONSOLIDATED BALANCE SHEETS (Unaudited)'
- [page 8] "CONDENSED CONSOLIDATED STATEMENTS OF SHAREHOLDERS' EQUITY (Unaudited)"
- [page 9] 'CONDENSED CONSOLIDATED STATEMENTS OF CASH FLOWS (Unaudited)'
- [page 11] 'Notes to Condensed Consolidated Financial Statements (Unaudited)'
- [page 11] 'Note 1 - Summary of Significant Accounting Policies'
- [page 11] 'Basis of Presentation and Preparation'
- [page 11] 'Note 2 - Revenue'
- [page 12] 'Note 3 - Earnings Per Share'
- [page 12] 'Note 4 - Financial Instruments'
- [page 12] 'Cash, Cash Equivalents and Marketable Securities'
- [page 13] 'Derivative Instruments and Hedging'
- [page 13] 'Foreign Exchange Rate Risk'
- [page 13] 'Interest Rate Risk'
- [page 15] 'Accounts Receivable'
- [page 15] 'Trade Receivables'
- [page 15] 'Vendor Non-Trade Receivables'
- [page 15] 'Note 5 - Condensed Consolidated Financial Statement Details'
- [page 15] 'Inventories'
- [page 15] 'Property, Plant and Equipment, Net'
- [page 17] 'Intangible Assets, Net'
- [page 17] 'Note 6 - Debt'
- [page 17] 'Commercial Paper'
- [page 17] 'Term Debt'
- [page 17] "Note 7 - Shareholders' Equity"
- [page 17] 'Share Repurchase Program'
- [page 18] 'Note 8 - Share-Based Compensation'
- [page 18] 'Restricted Stock Units'
- [page 18] 'Share-Based Compensation'
- [page 18] 'Note 9 - Commitments and Contingencies'
- [page 18] 'Unconditional Purchase Obligations'
- [page 18] 'Contingencies'
- [page 20] 'Note 10 - Segment Information'
- [page 20] 'Three Months Ended June 28, 2025'
- [page 20] 'Nine Months Ended June 27, 2026'
- [page 20] 'Nine Months Ended June 28, 2025'
- [page 21] 'Available Information'
- [page 21] 'Business Seasonality and Product Introductions'
- [page 21] 'Macroeconomic Conditions'
- [page 22] 'Tariffs and Other Measures'
- [page 22] 'Segment Operating Performance'
- [page 22] 'Americas'
- [page 22] 'Europe'
- [page 22] 'Greater China'
- [page 23] 'Japan'
- [page 23] 'Rest of Asia Pacific'
- [page 23] 'Products and Services Performance'
- [page 23] 'iPhone'
- [page 23] 'Mac'
- [page 23] 'iPad'
- [page 23] 'Wearables, Home and Accessories'
- [page 23] 'Services'
- [page 24] 'Gross Margin'
- [page 24] 'Products Gross Margin'
- [page 24] 'Services Gross Margin'
- [page 25] 'Operating Expenses'
- [page 25] 'Research and Development'
- [page 25] 'Selling, General and Administrative'
- [page 25] 'Provision for Income Taxes'
- [page 26] 'Liquidity and Capital Resources'
- [page 26] 'Manufacturing Purchase Obligations'
- [page 26] 'Other Purchase Obligations'
- [page 26] 'Deemed Repatriation Tax Payable'
- [page 26] 'Capital Return Program'
- [page 26] 'Recent Accounting Pronouncements'
- [page 26] 'Internal-Use Software'
- [page 26] 'Disaggregation of Income Statement Expenses'
- [page 28] 'Income Taxes'
- [page 28] 'Critical Accounting Estimates'
- [page 28] 'Evaluation of Disclosure Controls and Procedures'
- [page 28] 'Changes in Internal Control over Financial Reporting'
- [page 29] 'Digital Markets Act Investigations'
- [page 29] 'Department of Justice Lawsuit'
- [page 29] 'Epic Games'
- [page 29] 'Other Legal Proceedings'
- [page 30] "Future operating results depend upon the Company's ability to obtain components and computing resources in sufficient quantities and on commercially reasonable terms."
- [page 30] "The Company's future performance depends in part on support from third-party software developers."
- [page 34] "The Company's business is subject to a variety of U.S. and international laws, rules, policies and other obligations regarding the collection, use, protection and transfer of personal data."
- [page 36] 'Purchases of Equity Securities by the Issuer and Affiliated Purchasers'
- [page 37] 'Insider Trading Arrangements'
- [page 38] 'SIGNATURE'