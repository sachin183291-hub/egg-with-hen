/**
 * Utility helpers.
 */
import type { EvidenceStatus, AIStatus, BlockchainStatus, DeviceStatus } from '../types'

export function formatDate(iso: string): string {
  const utcIso = iso.endsWith('Z') || iso.includes('+') ? iso : `${iso}Z`;
  return new Date(utcIso).toLocaleDateString('en-IN', {
    year: 'numeric', month: 'short', day: 'numeric',
    timeZone: 'Asia/Kolkata',
  })
}

export function formatDateTime(iso: string): string {
  const utcIso = iso.endsWith('Z') || iso.includes('+') ? iso : `${iso}Z`;
  return new Date(utcIso).toLocaleString('en-IN', {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    timeZone: 'Asia/Kolkata',
    hour12: true,
  })
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function formatPercent(val?: number): string {
  if (val === undefined || val === null) return '—'
  return `${(val * 100).toFixed(1)}%`
}

export function truncateHash(hash?: string, len = 16): string {
  if (!hash) return '—'
  return `${hash.slice(0, len)}...`
}

export function evidenceStatusBadgeClass(status: EvidenceStatus): string {
  const map: Record<EvidenceStatus, string> = {
    VERIFIED: 'badge badge-verified',
    SUSPICIOUS: 'badge badge-suspicious',
    REVIEW_REQUIRED: 'badge badge-review',
    PENDING_SYNC: 'badge badge-pending',
    UPLOADED: 'badge badge-uploaded',
    REJECTED: 'badge badge-rejected',
    INTEGRITY_MISMATCH: 'badge badge-suspicious',
  }
  return map[status] ?? 'badge badge-pending'
}

export function aiStatusBadgeClass(status?: AIStatus): string {
  if (!status) return 'badge badge-pending'
  const map: Record<AIStatus, string> = {
    VERIFIED: 'badge badge-verified',
    SUSPICIOUS: 'badge badge-suspicious',
    REVIEW_REQUIRED: 'badge badge-review',
    PENDING: 'badge badge-pending',
    FAILED: 'badge badge-rejected',
  }
  return map[status] ?? 'badge badge-pending'
}

export function blockchainStatusBadgeClass(status?: BlockchainStatus): string {
  if (!status) return 'badge badge-pending'
  const map: Record<BlockchainStatus, string> = {
    REGISTERED: 'badge badge-verified',
    VERIFIED: 'badge badge-verified',
    NOT_REGISTERED: 'badge badge-pending',
    MISMATCH: 'badge badge-suspicious',
    FAILED: 'badge badge-rejected',
  }
  return map[status] ?? 'badge badge-pending'
}

export function deviceStatusBadgeClass(status: DeviceStatus): string {
  const map: Record<DeviceStatus, string> = {
    AUTHORIZED: 'badge badge-authorized',
    PENDING: 'badge badge-pending-dev',
    REVOKED: 'badge badge-revoked',
  }
  return map[status] ?? 'badge badge-pending'
}

export function markerColor(status: EvidenceStatus): string {
  const map: Record<EvidenceStatus, string> = {
    VERIFIED: '#10b981',
    SUSPICIOUS: '#ef4444',
    REVIEW_REQUIRED: '#f59e0b',
    PENDING_SYNC: '#6366f1',
    UPLOADED: '#3b82f6',
    REJECTED: '#6b7280',
    INTEGRITY_MISMATCH: '#ef4444',
  }
  return map[status] ?? '#6366f1'
}

export function makeMarkerIcon(color: string) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="36" viewBox="0 0 28 36">
    <path d="M14 0C6.268 0 0 6.268 0 14c0 9.857 14 22 14 22S28 23.857 28 14C28 6.268 21.732 0 14 0z" fill="${color}"/>
    <circle cx="14" cy="14" r="6" fill="white" opacity="0.9"/>
  </svg>`
}

export function getInitials(name: string): string {
  return name.split(' ').slice(0, 2).map(w => w[0]).join('').toUpperCase()
}
