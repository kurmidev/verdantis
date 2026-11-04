import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useToast } from '../../components/ui/Toast'
import { api } from '../../lib/api/client'
import { ApiError, describeError } from '../../lib/api/errors'
import type { BulkItem, DecisionAction, DecisionBody, DecisionResult } from '../../lib/api/schemas'
import { patchFindings, restore, snapshot } from './cache'

const OPTIMISTIC: Record<DecisionAction, string> = { approve: 'approved', reject: 'rejected', investigate: 'investigating' }

export function useDecision(batchId: string) {
  const qc = useQueryClient()
  const toast = useToast()
  return useMutation({
    mutationFn: (v: { findingId: string; body: DecisionBody; key: string }) => api.decide(v.findingId, v.body, v.key),
    onMutate: async (v) => {
      await qc.cancelQueries({ queryKey: ['findings', batchId] })
      const snap = snapshot(qc, batchId)
      patchFindings(qc, batchId, new Map([[v.findingId, { status: OPTIMISTIC[v.body.action], pending: true }]]))
      return { snap }
    },
    onSuccess: (res: DecisionResult, v) => {
      patchFindings(qc, batchId, new Map([[v.findingId, { status: res.finding_status, pending: false, awaiting_second_approval: res.requires_second_approval ?? false }]]))
      void qc.invalidateQueries({ queryKey: ['batch', batchId] })
      toast(res.requires_second_approval ? 'Decision recorded; awaiting second approval.' : 'Decision recorded.')
    },
    onError: (err, v, ctx) => {
      if (ctx) restore(qc, ctx.snap)
      toast(describeError(err), 'error')
      if (err instanceof ApiError && err.status === 409) void qc.invalidateQueries({ queryKey: ['findings', batchId] })
      void v
    },
  })
}

export function useBulkDecision(batchId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { items: BulkItem[]; key: string }) => api.decideBulk(v.items, v.key),
    onSuccess: (res) => {
      const patches = new Map(
        res.results
          .filter((r) => r.status === 201 && r.finding_status)
          .map((r) => [r.finding_id, { status: r.finding_status as string, pending: false }] as const),
      )
      patchFindings(qc, batchId, patches)
      void qc.invalidateQueries({ queryKey: ['batch', batchId] })
    },
  })
}
