# Regression report

Old run: `runs\hr_policy` -> new documents: `demos\hr_policy\docs_v2`

The old eval set was re-run against an agent regenerated from the saved requirements. A case whose key facts no longer appear in the new documents is marked *stale*: the test is out of date, not the agent.

| Status | Cases |
|---|---|
| REGRESSION | 2 |
| improved | 1 |
| unchanged_fail | 6 |
| unchanged_pass | 18 |

## Details
- **ans-01** REGRESSION: What is the maximum duration of paid sick leave per calendar year? - missing expected facts (recall 0.00)
- **ans-04** unchanged_fail: My manager wants me to work from home for a month, but I have a 24x7 duty roster. Can I do that? - judge passes disagreed (position-swap); missing expected facts (recall 0.00)
- **mul-13** REGRESSION: What is the maximum number of days of annual leave that can be carried forward to the next year? - judge passes disagreed (position-swap); missing expected facts (recall 0.00)
- **amb-14** unchanged_fail: Can employees take 5 days off without notice? - missing expected facts (recall 0.33)
- **amb-16** improved: can i book premium economy on short flights
- **too-20** unchanged_fail: How many days' pay in lieu of notice is an employee entitled to if they leave the company without adequate notice? - expected tool current_date, called none
- **ans-21** unchanged_fail: If I need to take a public holiday off, how many days can I carry forward from previous years? - missing expected facts (recall 0.00)
- **ans-26** unchanged_fail: What is not reimbursable for travel expenses? - refused an answerable question
- **ans-27** unchanged_fail: A shore staff member has a trip that is less than 4 nights long. What is not covered? - refused an answerable question
