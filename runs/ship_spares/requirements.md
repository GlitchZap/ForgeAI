# Requirements: Structured Requirements Document for Document-Grounded Assistant

**Scope:** This document outlines the requirements for a document-grounded assistant to support the fleet procurement team in managing their spare parts procurement process. The assistant will handle specific tasks related to the catalogue, supplier terms, order totals, and warranty claim processes.

**Audience:** Fleet Procurement Team

**Tone:** Professional and informative, providing clear and concise instructions for the assistant's functionality.

## Must answer
- **spares_catalogue_lookup** - Look up part numbers, vessel classes, unit prices, stock quantities, and suppliers in the spares_catalogue.csv file. _(source: documents)_
- **supplier_terms_lookup** - Retrieve supplier terms such as lead times, minimum order quantities, and delivery charges from the supplier_terms.md document. _(source: documents)_
- **discount_policy_lookup** - Determine the discount policy and thresholds for orders from the purchase_approval_matrix.md document. _(source: documents)_

## Must refuse
- Requests for personal or confidential data.
- Requests for advice or recommendations on how to handle specific situations.
- Requests for information on delivery requirements or preferences for certain parts or suppliers.
- Requests for information on exceptions or special conditions for specific vessel classes or part numbers.
- Requests for information on specific discount policies or thresholds.
- Requests for information on warranty claim processes for parts that fail.
- warranty_claim_process (requested, but not covered by the documents)

## Groundability check
| Topic | Status | Evidence | Note |
|---|---|---|---|
| spares_catalogue_lookup | supported | spares_catalogue.csv | contains all required information |
| supplier_terms_lookup | supported | supplier_terms.md | Quote directly states the fact needed: lead time for Nordline Supply (Singapore) |
| discount_policy_lookup | supported | purchase_approval_matrix.md | Directly states the discount policy and thresholds for orders |
| warranty_claim_process | unsupported | - | none of ['claim', 'warra'] appear in any document |

## Flags
- NOT GROUNDABLE: the brief asks for 'warranty_claim_process' but the documents do not cover it. The agent will refuse these questions instead of guessing.

## Clarifications
- **Q:** Are there any specific vessel classes or part numbers that require special attention or additional information in the catalogue?  
  **A:** No specific vessel classes or part numbers require special attention or additional information in the catalogue. _(assumed - no human answer)_
- **Q:** Does the supplier terms document include any exceptions or special conditions that we should be aware of for certain suppliers or parts?  
  **A:** The supplier terms document does not include any exceptions or special conditions that require specific awareness. _(assumed - no human answer)_
- **Q:** Is there a specific discount policy or threshold for discounts that we should consider when placing orders?  
  **A:** Use the most conservative default. _(assumed - no human answer)_
- **Q:** Should the assistant be able to handle warranty claim processes for parts that fail, or is this a separate process that the fleet procurement team should handle independently?  
  **A:** Use the most conservative default. _(assumed - no human answer)_
- **Q:** Are there any specific delivery requirements or preferences for certain parts or suppliers that we should incorporate into the assistant's functionality?  
  **A:** Use the most conservative default. _(assumed - no human answer)_
