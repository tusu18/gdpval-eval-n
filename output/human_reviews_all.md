# Full-output human reviews, both studies

Built 2026-11-06T01:33:21+00:00. One reviewer. 8 reviews, 4 consequential errors. Not pooled.

| Study | Case | Model | Acceptable | Consequential | Task defect | Min | Primary judge |
|---|---|---|---|---|---|---|---|
| historical | C-2c0096b2 | gpt-6.1-sol | yes | no | no |  | accept |
| historical | C-4f3f9946 | claude-sonnet-5.5 | no | yes | no |  | reject |
| historical | C-5304f72e | claude-sonnet-5.5 | no | yes | no |  | reject |
| historical | C-7424ebd2 | gpt-6.1-sol | yes | no | no |  | accept |
| historical | C-9d21debd | claude-sonnet-5.5 | no | yes | no |  | reject |
| follow_up_v3 | 1b1ade2d__conflict__opus__r1 | claude-opus-5.5 | yes | no | no | 5 | pass |
| follow_up_v3 | 15ddd28d__original__opus__r1 | claude-opus-5.5 | no | yes | no | 7 | pass on all 10 |
| follow_up_v3 | 24d1e93f__original__sonnet__r1 | claude-sonnet-5.5 | yes | no | yes | 8 | pass on all 10 without reference files (sel); honored fail severity 4 on R20-R22 (per-headlamp vs per-set pricing) once reference files were in the packet (sel2) |
