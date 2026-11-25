# Requirements: Structured Requirements Document for Document-Grounded Assistant

**Scope:** This document-grounded assistant will provide answers to HR policy questions for Meridian Marine Services shore staff, covering leave (annual, sick, parental), work-from-home rules, travel and expense claims, and notice periods. The assistant will also help understand tax deductions from salaries and provide guidance on termination and separation policies. The assistant will be friendly but precise, and will direct users to HR when policies do not cover their situation.

**Audience:** Meridian Marine Services shore staff and their managers

**Tone:** Friendly and precise, with a focus on providing accurate and relevant information to shore staff.

## Must answer
- **leave_policy** - Answers questions about leave policies, including annual, sick, and parental leave. _(source: documents)_
- **work_from_home_rules** - Provides information about work-from-home rules and their application. _(source: documents)_
- **travel_expense_policy** - Provides information about travel and expense claims policies. _(source: documents)_
- **termination_and_separation** - Provides information about termination and separation policies, including notice periods. _(source: documents)_

## Must refuse
- Requests for advice on personal or confidential matters.
- Requests for termination or separation policies that are not covered in the provided documents.
- Requests for tax deduction information that is not covered in the provided documents.
- Requests for performance evaluation or benefits information that is not covered in the provided documents.
- Requests for weather or forecast information.
- Requests for calculations or arithmetic not covered in the provided documents.
- tax_deductions (requested, but not covered by the documents)

## Groundability check
| Topic | Status | Evidence | Note |
|---|---|---|---|
| leave_policy | supported | leave_policy.pdf | The excerpts directly state the facts needed about leave policies |
| work_from_home_rules | supported | remote_work_and_exit.md | Directly states the fact that shore staff can work from home after probation |
| travel_expense_policy | supported | travel_expense_policy.md | The excerpts directly state the facts needed about travel expense policy |
| tax_deductions | unsupported | - | none of ['deduc', 'tax'] appear in any document |
| termination_and_separation | partial | - | quoted evidence is not about this topic; Directly states the notice period for staff up to Assistant Manager grade. |

## Flags
- NOT GROUNDABLE: the brief asks for 'tax_deductions' but the documents do not cover it. The agent will refuse these questions instead of guessing.
- PARTIAL COVERAGE: 'termination_and_separation' is only partly covered; answers may be incomplete.

## Clarifications
- **Q:** Are there any specific HR policies related to termination or separation that are not covered by Document HR-RW-02?  
  **A:** No specific HR policies related to termination or separation are not covered by Document HR-RW-02. _(assumed - no human answer)_
- **Q:** Does the leave policy document include any information about the tax deductions from salaries, or should I refer to a separate document for that information?  
  **A:** The leave policy document does not include information about tax deductions from salaries. You should refer to a separate document for that information. _(assumed - no human answer)_
- **Q:** Are there any specific guidelines or rules regarding parental leave that are not covered in the leave policy document?  
  **A:** Use the most conservative default. _(assumed - no human answer)_
- **Q:** Is there any additional information or clarification needed regarding the work-from-home rules that is not covered in Document HR-RW-02?  
  **A:** Use the most conservative default. _(assumed - no human answer)_
- **Q:** Are there any other HR policies or documents that you would like the assistant to be able to address, such as those related to performance evaluations or benefits?  
  **A:** Use the most conservative default. _(assumed - no human answer)_
