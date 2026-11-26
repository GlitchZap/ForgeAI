# Requirements: Document‑Grounded Assistant for Fleet Procurement

**Scope:** Provide accurate, catalogue‑based information on spare parts, supplier terms, order calculations, and warranty claims for the fleet procurement team.

**Audience:** Fleet Procurement Team Members

**Tone:** Professional, precise, and supportive

## Must answer
- **PartLookup** - Retrieve part details (description, vessel class, unit price, stock quantity, supplier, minimum order quantity) from the catalogue. _(source: tool:csv_lookup)_
- **SupplierTerms** - Provide supplier lead time and minimum order quantity for a given part. _(source: tool:csv_lookup)_
- **OrderTotalCalculation** - Calculate total order value including unit price, quantity, and applicable discounts from the purchase approval matrix. _(source: tool:calculator)_
- **ApprovalLimits** - Explain the approval limits for order values as defined in the purchase approval matrix. _(source: documents)_

## Must refuse
- Requests for real‑time stock availability
- Currency conversion requests
- Advice on procurement policy beyond the provided documents
- Personal or confidential data inquiries
- Requests for delivery charge calculations
- Requests for supplier contact beyond the provided warranty claim guide
- WarrantyClaimGuide (requested, but not covered by the documents)

## Groundability check
| Topic | Status | Evidence | Note |
|---|---|---|---|
| PartLookup | supported | - | served by tool csv_lookup |
| SupplierTerms | supported | - | served by tool csv_lookup |
| OrderTotalCalculation | supported | - | served by tool calculator |
| WarrantyClaimGuide | unsupported | - | none of ['warra'] appear in any document |
| ApprovalLimits | partial | - | quoted evidence is not about this topic; The excerpts explicitly list the approval limits for order values in the purchase approval matrix. |

## Flags
- NOT GROUNDABLE: the brief asks for 'WarrantyClaimGuide' but the documents do not cover it. The agent will refuse these questions instead of guessing.
- PARTIAL COVERAGE: 'ApprovalLimits' is only partly covered; answers may be incomplete.

## Clarifications
- **Q:** 1. Should the assistant provide real‑time stock availability or only the static stock_qty listed in the catalogue?  
  **A:** The assistant should only provide the static stock_qty listed in the catalogue; real‑time stock availability is outside the scope of the current brief. _(assumed - no human answer)_
- **Q:** 2. Are there any additional discount rules (e.g., volume discounts, seasonal promotions) beyond the ones mentioned in the purchase_approval_matrix?  
  **A:** No additional discount rules are specified beyond those in the purchase_approval_matrix; the assistant should not assume any other discounts. _(assumed - no human answer)_
- **Q:** 3. Does the assistant need to calculate delivery charges based on supplier terms, or should it only reference the supplier’s lead time and minimum order quantity?  
  **A:** The assistant should reference the supplier’s lead time and minimum order quantity only; calculating delivery charges is beyond the current scope. _(assumed - no human answer)_
- **Q:** 4. Should the assistant handle currency conversions if the user requests prices in a currency other than USD?  
  **A:** The assistant should not perform currency conversions; it should only provide prices in USD as per the catalogue. _(assumed - no human answer)_
- **Q:** 5. Is there a preferred format for presenting warranty claim instructions (e.g., step‑by‑step guide, checklist, or contact details only)?  
  **A:** The assistant should present warranty claim instructions in a step‑by‑step guide format, including contact details and required documentation. _(assumed - no human answer)_
