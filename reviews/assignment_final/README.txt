HUMAN REVIEW IMPORTS FOR THE ASSIGNMENT

No human labels are supplied by the software. A review is complete only when the
reviewer marks the full sources/output reviewed and answers all three endpoints.
Uncertain is valid; it is retained and excluded from binary outcome denominators.

1. The fixed five-case plan in config/assignment_review_minimal_v1.json is complete.
   All five actual content reviews are imported: two accepted, three rejected for
   substantive correction; the three error findings have evidence, exact user
   categories and confirmed minimum corrections. Two tooling findings share one
   source family, and the Finance-approval finding belongs to the second family.
   No additional 20/35/78-case quota applies. This qualitative case audit does not
   validate the grader or estimate population failure rates.

2. Chat responses and current exports are already saved. For any future explicit
   correction or additional review, preserve the actual export and original response.
3. From the project root, import the export:

   python3 scripts/assignment_evidence.py --import-review /absolute/path/my-human-reviews.json

   Then rebuild the assignment website/report with its supplied build command.

The importer preserves the exact export under its SHA-256 filename and writes a
receipt with the reviewer metadata and hashes of the available case inputs,
transcript and artifacts. These hashes record what existed at import, not proof
of what the reviewer read earlier or of their identity/expertise/independence.
Do not edit imported exports or receipts in place. Source changes invalidate an
import instead of silently transferring the old judgment to a changed task.

To correct an earlier export, provide a new full snapshot with an explicit
"supersedes_export_sha256" containing the old export hash (or a list of hashes).
Only the same reviewer can supersede an export. Include all reviews to retain:
supersession replaces the entire export, not only the changed row. Both original
and successor remain saved. An ambiguous conflict is excluded rather than resolved
by file date, majority vote or automatic adjudication. Different reviewers'
disagreements remain visible; neither person's label is converted into gold.

For findings retained in the narrowed case analysis, include the primary category and source/consequence
and output evidence. A claimed consequential error always requires both evidence
fields. Document absence explicitly when no file was delivered. A usable draft is
not counted as a submitted deliverable. Review time is optional but must be actual
measured minutes; blank time remains unknown. Role/qualification is self-declared.

The two earlier issue-only judgments remain separate. The earlier uncertain
Case C-7424ebd2 responses remain in history; the user's subsequent explicit
content review supplies acceptable=yes, consequential_error=no and
evaluation_defect=no. Native-file inspection and page-length compliance remain
unverified. Only actual later answers may supersede an earlier endpoint. The user confirmed the last correction and explicitly requested review closure.
The selected content review and finding documentation are complete; external
submission and the live presentation have not been performed. The program does
not impose an arbitrary 20/35-label completion quota.

This importer and evidence rebuild use only Python's standard library and make
no API calls. Existing frozen studies, scores and source tasks are read-only.
