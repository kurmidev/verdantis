import { z } from 'zod'

// Enums stay strings: unknown values from a newer API render as raw text (LLD 13 3.19, HLD 6.8).
export const Finding = z.object({
  finding_id: z.string(),
  batch_id: z.string(),
  record_key: z.string(),
  item_id: z.string().nullish(),
  issue_type: z.string(),
  severity: z.string(),
  confidence: z.number(),
  explanation: z.string(),
  evidence: z.record(z.string(), z.unknown()),
  suggested_action: z.string(),
  suggested_value: z.record(z.string(), z.unknown()).nullish(),
  source: z.string(),
  also_detected_by: z.array(z.string()).default([]),
  rule_id: z.string(),
  rule_version: z.string(),
  model_id: z.string().nullish(),
  prompt_version: z.string().nullish(),
  status: z.string(),
  created_at: z.string().nullish(),
})
export type Finding = z.infer<typeof Finding>

/** Client-only decoration on cached rows. */
export type ClientFinding = Finding & { awaiting_second_approval?: boolean; pending?: boolean }

export const FindingsPage = z.object({
  items: z.array(Finding),
  next_cursor: z.string().nullish(),
})
export type FindingsPage = z.infer<typeof FindingsPage>

export const Batch = z.object({
  batch_id: z.string(),
  status: z.string(),
  records: z.number().nullish(),
  findings_by_type: z.record(z.string(), z.number()).default({}),
  ai_status: z.string().nullish(),
  error_code: z.string().nullish(),
  created_at: z.string().nullish(),
  completed_at: z.string().nullish(),
  filename: z.string().nullish(),
})
export type Batch = z.infer<typeof Batch>

// GET /batches does not exist in LLD 04 yet (OQ-810): provisional shape.
export const BatchList = z.object({ items: z.array(Batch), next_cursor: z.string().nullish() })
export const BatchCreated = z.object({ batch_id: z.string(), status: z.string() })

export const DecisionResult = z.object({
  decision_id: z.string(),
  finding_status: z.string(),
  approval_level: z.number().nullish(),
  requires_second_approval: z.boolean().nullish(),
})
export type DecisionResult = z.infer<typeof DecisionResult>

export const BulkResult = z.object({
  results: z.array(
    z.object({
      finding_id: z.string(),
      status: z.number(),
      decision_id: z.string().nullish(),
      finding_status: z.string().nullish(),
      error: z.object({ code: z.string(), message: z.string().nullish() }).nullish(),
    }),
  ),
})
export type BulkResult = z.infer<typeof BulkResult>

export const ExportCreated = z.object({ export_id: z.string(), status: z.string().nullish() })
// GET /exports/{id} is provisional (OQ-132, OQ-237).
export const ExportStatus = z.object({
  status: z.string(),
  signed_url: z.string().nullish(),
  expires_at: z.string().nullish(),
  finding_count: z.number().nullish(),
})
export type ExportStatus = z.infer<typeof ExportStatus>

export const ReferenceData = z.object({
  type: z.string(),
  version: z.number().nullish(),
  values: z.array(z.string()),
})

export type DecisionAction = 'approve' | 'reject' | 'investigate'
export interface DecisionBody {
  action: DecisionAction
  reason_code?: string
  comment?: string
  edited_value?: Record<string, unknown>
}
export interface BulkItem {
  finding_id: string
  action: DecisionAction
  reason_code?: string
  comment?: string
}
