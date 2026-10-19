# Just One More: feasibility assessment

> Context: Historical assessment of the superseded video/freelancer idea. This is not the current workshop product or shipped AI functionality. See [branch map](BRANCHES.md) and [current Slice 1 review](SLICE1_REVIEW.md).

Assessment date: 4 October 2026. This is a scoped technical assessment, not a completed video-analysis benchmark.

## Verdict

A reliable human-reviewed hackathon prototype is feasible. A system that autonomously certifies creative quality or decides payment entitlement is not a credible first implementation. Keep ScopeBridge's original scope/approval/payment workflow and add video evidence as a review aid.

## What was checked

- Current repo: working Python checkout implementation, seven automated tests passing again, and a previously reported successful Sandbox payment.
- Environment: Python 3.10 is available; FFmpeg and ffprobe were not found on PATH. No AI provider credential field is present in `.env` or `.env.example`; this does not establish whether the team has access elsewhere.
- Official Gemini documentation supports video/audio understanding with timestamp references and structured outputs. These capabilities make the proposed integration possible, not proven accurate on our tasks.
- No videos were uploaded to an AI service, no paid inference was performed, and no payment was initiated during this assessment.

## First-build boundaries

Proposed app limits: MP4 only, 15–60 seconds, at most 25 MB, English briefs, one seller, USD, one delivered video per scope version, and at most five explicit requirements. These are deliberately conservative product limits, not provider maximums.

| Capability | Feasibility | Implementation boundary |
| --- | --- | --- |
| Extract requirements from a brief | High for a reviewed draft | Source excerpts, explicit unknowns, seller/client confirmation before freezing scope |
| Check duration, dimensions, aspect ratio | High | ffprobe, account for rotation/display geometry, explicit tolerance, no model arithmetic |
| Find a specified visible object or end-card text | Feasible but unproven | Model findings with timestamps and click-through evidence; uncertain cases require review |
| Identify visible captions | Feasible for sampled evidence | Do not claim all speech is accurately captioned without transcription/OCR alignment evaluation |
| Verify an exact client logo | More difficult | Reference image and reviewed comparison; defer brand authenticity claims |
| Compare a later request with accepted scope | Feasible but unproven | Explicit change evidence; humans classify billable additions |
| Decide aesthetic quality, legal meaning, or payment entitlement | Outside scope | Never automatically approve/refuse payment based on model opinion |
| Versioned scope and receipts | High | SQLite, authoritative totals, stable request IDs, payment reconciliation |

## Architecture that fits the repo

Keep Python and the existing PayPal adapter. Separate brief/scope logic, AI adapter, media validation, storage, and routes. A maintained HTTP framework is appropriate for file uploads and any hosted build; the current standard-library server's tiny JSON limit and synchronous handlers are not ready for video jobs.

Use a single background worker initially, backed by SQLite job records and polling from the browser. Limit accepted jobs, timeouts, and retries. No distributed queue or agent framework is needed for the local prototype.

Store scopes and decisions independently from AI runs. Store an upload's hash and scope version with each result so a different upload cannot inherit an earlier report. Validate actual media format and decoded metadata rather than trusting an extension. Use generated storage names, file limits, and argument-array subprocess calls with timeouts for ffprobe. Keep uploaded media and databases ignored by Git.

The review UI should distinguish measured checks from model findings. Prefer “observed,” “not observed in inspected content,” and “needs review” to unsupported binary verdicts. A timestamp inside the video's duration is necessary but not sufficient evidence; provide the corresponding clip/frame for human inspection. Treat model confidence numbers as uncalibrated unless evaluated.

Price only seller-selected services from a rate card using integer minor units. Do not let extracted text or model output invoke payment operations. Link each order to an accepted immutable scope version. Preserve the existing explicit PayPal buyer approval.

## Main external-service risks

Gemini's default video processing samples frames at 1 FPS, which can miss brief appearances. Increase sampling or inspect focused clips when needed; do not promise frame-perfect coverage. Timestamp claims and negative findings need evaluation. [Video documentation](https://ai.google.dev/gemini-api/docs/video-understanding)

Structured output helps enforce the response shape, but application validation and evidence checks are still required. [Structured-output documentation](https://ai.google.dev/gemini-api/docs/structured-output)

Uploaded provider files are temporary; maintain application-owned source metadata and delete remote/local files according to an explicit retention policy. Do not use a temporary provider URI as the sole durable reference. [Files API](https://ai.google.dev/gemini-api/docs/files)

Model access, quotas, inference cost, and end-to-end latency remain unmeasured for this app. Use team-created demo media first, review the selected tier's data-use terms, and obtain permission before uploading private client work. Pricing and data treatment depend on the selected service tier. [Pricing](https://ai.google.dev/gemini-api/docs/pricing)

## Proof before expansion

Build the analysis spike before the full product UI. Use 8–12 short videos with labeled variants: matching brief, wrong duration/ratio, missing object, missing or brief end card, caption issues, ambiguous requirement, and instructions embedded in the media. Keep held-out cases beyond the clips used to tune prompts.

Measure per-requirement correctness, unsupported positive claims, missed requirements, evidence/timestamp usefulness, repeatability, upload/analysis latency, cost, and graceful quota/timeout handling. Abstentions are useful when evidence is inadequate; a model producing only abstentions is not a successful feature. Agree acceptance thresholds before examining results rather than tuning them to the demo.

Practical gate: deterministic checks pass all supported-format fixtures; AI reliably demonstrates at least two useful semantic checks on held-out cases; uncertain outcomes are visible and cannot trigger billing. If video analysis is weak, retain brief extraction and scope comparison as the AI core and narrow video checks to the categories that pass evaluation.

## Effort and next step

Planning estimate, assuming two developers familiar with Python/web development and immediate API access: roughly 1–2 focused days for the analysis spike, then 5–8 additional working days for a narrow complete prototype and testing. Deployment, authentication, debugging account eligibility, and unfamiliar tooling can add time. This is not a delivery commitment; team availability and deadline are unknown.

Next required inputs are an approved AI provider/API key stored privately and team-created sample videos/briefs. The next development milestone should be a measured analysis report, not a polished dashboard. Production readiness remains a separate effort involving authorization, storage controls, upload hardening, verified webhooks, reconciliation, and operational monitoring.
