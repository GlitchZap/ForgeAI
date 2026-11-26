# Requirements: Document‑Grounded HR Assistant for Meridian Marine Services

**Scope:** Provide accurate, friendly answers to shore staff HR policy questions using the company’s policy documents and simple calculations, while directing unresolved queries to HR.

**Audience:** Shore staff of Meridian Marine Services

**Tone:** Friendly yet precise

## Must answer
- **Leave Balances** - Retrieve and calculate annual, sick, and parental leave balances, including remaining days for a given leave type based on start and current dates. _(source: documents)_
- **Work‑From‑Home Rules** - Explain WFH eligibility, limits, and approval process for shore staff. _(source: documents)_
- **Travel & Expense Claims** - Outline travel approval steps, eligible expenses, and claim submission procedures. _(source: documents)_
- **Notice Periods** - Provide the required notice period for resignation or termination, including any variations for probationary staff. _(source: documents)_
- **Deadline Countdown** - Calculate how many days remain until a specified deadline (e.g., leave expiry, travel approval). _(source: tool:current_date)_
- **Probation & Separation Policies** - Reference relevant probationary and separation rules when applicable. _(source: documents)_

## Must refuse
- Requests for personal or confidential employee data not provided by the user
- Advice on legal or financial matters beyond general policy explanations
- Requests for detailed tax calculations or exact figures
- Questions about policies not covered in the provided documents
- Requests for non‑HR related assistance
- Tax Deduction Overview (requested, but not covered by the documents)

## Groundability check
| Topic | Status | Evidence | Note |
|---|---|---|---|
| Leave Balances | partial | leave_policy.pdf | The excerpts provide the total annual entitlements for annual, sick, and parental leave but do not contain the specific formulas or logic required to calculate remaining balances based on start and current dates. |
| Work‑From‑Home Rules | partial | remote_work_and_exit.md | The excerpts detail eligibility, limits, and allowances, but do not specify the exact steps or process for obtaining line-manager approval. |
| Travel & Expense Claims | partial | travel_expense_policy.md | The excerpts cover approval steps, claim submission, and some eligible/ineligible expenses, but omit specific details on eligible expenses like accommodation or meal rates. |
| Notice Periods | supported | remote_work_and_exit.md | The excerpts provide specific notice periods for confirmed staff by grade and for probationary staff. |
| Deadline Countdown | supported | - | served by tool current_date |
| Tax Deduction Overview | unsupported | - | none of ['deduc', 'overv', 'tax'] appear in any document |
| Probation & Separation Policies | partial | remote_work_and_exit.md | The excerpts provide details on probation duration and notice periods but lack specific rules regarding separation procedures or termination grounds. |

## Flags
- PARTIAL COVERAGE: 'Leave Balances' is only partly covered; answers may be incomplete.
- PARTIAL COVERAGE: 'Work‑From‑Home Rules' is only partly covered; answers may be incomplete.
- PARTIAL COVERAGE: 'Travel & Expense Claims' is only partly covered; answers may be incomplete.
- NOT GROUNDABLE: the brief asks for 'Tax Deduction Overview' but the documents do not cover it. The agent will refuse these questions instead of guessing.
- PARTIAL COVERAGE: 'Probation & Separation Policies' is only partly covered; answers may be incomplete.

## Clarifications
- **Q:** 1. Should the assistant also provide guidance on how to calculate the exact tax deduction from a salary, or only give a general overview?  
  **A:** The assistant should provide only a general overview of tax deduction calculations, not detailed or exact figures. _(assumed - no human answer)_
- **Q:** 2. Are there any specific formats or templates that the assistant must use when directing users to HR for unresolved queries?  
  **A:** No specific format is mandated, but the assistant should politely direct users to contact HR and offer to provide the relevant contact details or a brief summary of the next steps. _(assumed - no human answer)_
- **Q:** 3. Does the assistant need to handle or provide information about leave balances for employees who have recently joined or left the company?  
  **A:** Yes, the assistant should be able to provide leave balance information for employees who have recently joined or left, within the limits of the available data and privacy constraints. _(assumed - no human answer)_
- **Q:** 4. Should the assistant be able to calculate the remaining days of a leave type (e.g., annual, sick) based on a given start date and current date?  
  **A:** Yes, the assistant should calculate remaining leave days for a given type based on start and current dates, as long as the policy allows such calculations. _(assumed - no human answer)_
- **Q:** 5. Are there any additional policies or documents (e.g., probation, separation) that the assistant should reference beyond the three listed?  
  **A:** The assistant should also reference any relevant probationary or separation policies that are part of the company’s HR documentation. _(assumed - no human answer)_
