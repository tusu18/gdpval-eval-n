# Construct-validity edits: review packet (CV01–CV09)

For each edit: the requirement, what the SOURCE records say (exact quotes), the ORIGINAL output sentence, the BREAK, and the PARAPHRASE. Question per edit: does the BREAK make the output violate the requirement? Y/N.

## CV01 — 1b1ade2d__original__opus__r1 — R15

**Requirement:** Specifies that Finance signoff is required at the supplier nomination stage

**Source records say:**
- `request`: "The final step is a formal supplier nomination, which must be documented with a full record of communication trails, negotiation summaries, internal evaluations, and signoffs from Finance, Quality, ER, and Program Managers."
- `request`: "signoffs from Finance, Quality, ER, and Program Managers."

**Original output sentence** (`Revised_Sourcing_Nomination_Workflow_Lamp_Assemblies_v0.1.docx`):
> Nomination is signed off by Finance, Quality, ER and the Program Manager.

**BREAK:**
> Nomination is signed off by Quality, ER and the Program Manager; Finance is informed after nomination.

**PARAPHRASE:**
> Finance, Quality, ER and the Program Manager each sign off the nomination.

*Why I think the break violates it:* Removes Finance from the nomination approval; the RACI table later in the document still lists Finance, so the deliverable contradicts itself in an operative section.

**Your answer:** Y / N

---

## CV02 — fd6129bd__original__sonnet__r1 — R24

**Requirement:** The SOP defines trigger criteria for when changes to schedule/timeline require formal change control

**Source records say:**
- `reference:Change Control SOP Working Session Internal Input Summary.docx`: "Timeline shift >2 business days for a milestone or deliverable"
- `reference:Change Control SOP Working Session Internal Input Summary.docx`: "Timeline Impact"

**Original output sentence** (`Change_Control_SOP.docx`):
> Timeline shift of more than 2 business days for a milestone or deliverable

**BREAK:**
> Timeline shift of more than 10 business days for a milestone or deliverable

**PARAPHRASE:**
> A milestone or deliverable timeline shift exceeding 2 business days

*Why I think the break violates it:* Threshold no longer matches the governing input (2 business days); the companion form still says 2, so SOP and form disagree.

**Your answer:** Y / N

---

## CV03 — fd6129bd__conflict__opus__r1 — R25

**Requirement:** The SOP defines trigger criteria for when changes to budget/cost require formal change control

**Source records say:**
- `workspace:operations/record-r2.txt`: "Formal change control is triggered when a budget overage is strictly greater than USD 5000."
- `workspace:project/decision-register.txt`: "change_control: governing record is operations/record-r2.txt, approved 2026-10-19. planning/proposal-r3.txt was created 2026-10-22 and remains unapproved. Dates alone do not confer authority."

**Original output sentence** (`FRM_Change_Request_Form_Template_v0.1.docx`):
> ☐ Budget overage strictly greater than USD 5,000

**BREAK:**
> ☐ Budget overage strictly greater than USD 50,000

**PARAPHRASE:**
> ☐ Budget overage above USD 5,000 (strictly greater than)

*Why I think the break violates it:* The form adopts the unapproved USD 50,000 threshold while the SOP keeps USD 5,000: the conflict-variant trap, in the companion file people fill in.

**Your answer:** Y / N

---

## CV04 — 58ac1cc5__original__sonnet__r1 — R21

**Requirement:** QA escalation email states that interim control (hold/quarantine) is in place pending disposition.

**Source records say:**
- `request`: "Compose a clear, professional email to QA leadership explaining the situation"

**Original output sentence** (`QA_Escalation_Email_DRAFT.docx`):
> QA flagged the lot as non-conforming; the lot is on hold/quarantine and will not be sampled for use, issued or dispensed to the GMP run until you disposition it.

**BREAK:**
> QA flagged the lot as non-conforming; to protect the run date the lot has been released to the GMP run and may be sampled, issued and dispensed while you disposition it.

**PARAPHRASE:**
> QA has flagged the lot non-conforming; it remains quarantined on hold and will not be sampled, issued or dispensed to the GMP run until you give a disposition.

*Why I think the break violates it:* Interim control is removed: a non-conforming lot is released for use before disposition.

**Your answer:** Y / N

---

## CV05 — 76418a2c__original__opus__r1 — R13

**Requirement:** Savings equals Industry Average Cost minus Actual Shipping Cost for every row and is stored as a numeric value (negative values allowed)

**Source records say:**
- `request`: "savings based on the actual shipping costs vs the industry average costs"

**Original output sentence** (`Daily Shipment Manifest 062525.xlsx`):
> formula=H3-G3;

**BREAK:**
> formula=G3-H3;

**PARAPHRASE:**
> formula=SUM(H3,-G3);

*Why I think the break violates it:* Row 3 savings sign is inverted; every other row keeps H-G, so one operative row is wrong.

**Your answer:** Y / N

---

## CV06 — ce864f41__original__sonnet__r1 — R15

**Requirement:** Individual Utilization % is calculated as (March 2025 project hours per person, after overhead handling) divided by the person’s monthly capacity basis used in the chosen method.

**Source records say:**
- `request`: "About 15% of an employee's time is typically reserved for administrative and overhead activities and should be excluded when making a final determination regarding an individual's respective over- or underutilization."
- `request`: "Are any individuals at risk of burnout or underutilization?"
- `request`: "About 15% of an employee's time is typically reserved for administrative and overhead activities and should be excluded"

**Original output sentence** (`Workload_Tracker_Responses.docx`):
> Utilization = project hours ÷ net project capacity.

**BREAK:**
> Utilization = net project capacity ÷ project hours.

**PARAPHRASE:**
> Utilization is project hours divided by net project capacity.

*Why I think the break violates it:* The stated definition in the companion note is inverted relative to the workbook formulas.

**Your answer:** Y / N

---

## CV07 — 93b336f3__original__opus__r1 — R07

**Requirement:** States the proposed ownership split as 49:51 (EvTronics:EV Batteries Inc.).

**Source records say:**
- `request`: "Proposed Partnership structure is a 49:51::EvTronics:EV Batteries Inc. split"

**Original output sentence** (`Battery_Pack_Localisation_Partnership_Proposal.docx`):
> Recommendation: give in-principle approval to proceed with the 49:51 EvTronics–EV Batteries Inc. JV for local assembly only.

**BREAK:**
> Recommendation: give in-principle approval to proceed with the 51:49 EvTronics–EV Batteries Inc. JV for local assembly only.

**PARAPHRASE:**
> Recommendation: grant in-principle approval to proceed with the EvTronics–EV Batteries Inc. joint venture (49:51) for local assembly only.

*Why I think the break violates it:* The recommendation the CPO approves flips control of the JV; the structure table elsewhere still says 49/51.

**Your answer:** Y / N

---

## CV08 — a4a9195c__original__sonnet__r1 — R15

**Requirement:** The SOP specifies regular verification/testing of personnel grounding devices (e.g., wrist straps, footwear testers), with an interval defined by company policy (such as daily or before use)

**Source records say:**
- `request`: "proper procedures are needed for training and providing guidance to the warehouse team for handling and storing Electro-Static Discharge (ESD) sensitive components"

**Original output sentence** (`ESD_Handling_Storage_SOP.docx`):
> Every shift, before handling ESDS

**BREAK:**
> Once a year, during the annual audit

**PARAPHRASE:**
> Each shift, prior to handling ESDS

*Why I think the break violates it:* Wrist-strap test interval becomes annual, which no ESD control plan accepts as 'regular' for daily handling.

**Your answer:** Y / N

---

## CV09 — 05389f78__original__opus__r1 — R58

**Requirement:** Report uses only figures taken from the 'Model A HL quotes' file for costs and volume (no invented numbers or external sources).

**Source records say:**
- `request`: "Use the volume and pricing details provided in the quotation file to calculate and present the financial impact"
- `reference:Model A HL quotes_1.docx`: "Year 1
word/document.xml:paragraph:51	100,000
word/document.xml:paragraph:52	Year 2
word/document.xml:paragraph:53	125,000
word/document.xml:paragraph:54	Year 3
word/document.xml:paragraph:55	140,000
word/document.xml:paragraph:56	Year 4
word/document.xml:paragraph:57	165,000"
- `reference:Model A HL quotes_1.docx`: "Tooling costs
word/document.xml:paragraph:23	10,000,000.00
word/document.xml:paragraph:24	INR
word/document.xml:paragraph:25	R&D Costs
word/document.xml:paragraph:26	2,000,000.00"

**Original output sentence** (`CPO_Report_Model_A_Headlamp_Supplier_Replacement.docx`):
> Projected volumes are 100,000, 125,000, 140,000 and 165,000 units in Years 1 to 4.

**BREAK:**
> Projected volumes are 100,000, 125,000, 140,000 and 195,000 units in Years 1 to 4.

**PARAPHRASE:**
> Projected volumes for Years 1 to 4 are 100,000, 125,000, 140,000 and 165,000 units.

*Why I think the break violates it:* Year-4 volume is not in the source file; the four-year totals computed elsewhere no longer reconcile.

**Your answer:** Y / N

---
