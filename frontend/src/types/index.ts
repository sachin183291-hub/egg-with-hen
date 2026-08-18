/**
 * TypeScript types matching backend Pydantic schemas.
 */

export type RoleEnum = 'SUPER_ADMIN' | 'DEPT_ADMIN' | 'FIELD_OFFICER' | 'VIEWER'
export type DeviceStatus = 'PENDING' | 'AUTHORIZED' | 'REVOKED'
export type EvidenceStatus = 'PENDING_SYNC' | 'UPLOADED' | 'VERIFIED' | 'SUSPICIOUS' | 'REVIEW_REQUIRED' | 'REJECTED' | 'INTEGRITY_MISMATCH'
export type AIStatus = 'PENDING' | 'VERIFIED' | 'SUSPICIOUS' | 'REVIEW_REQUIRED' | 'FAILED'
export type BlockchainStatus = 'NOT_REGISTERED' | 'REGISTERED' | 'VERIFIED' | 'MISMATCH' | 'FAILED'
export type AuditAction = string

export interface Department {
  id: string
  name: string
  code: string
}

export interface User {
  id: string
  email: string
  username: string
  full_name: string
  phone?: string
  role: RoleEnum
  department_id?: string
  department?: Department
  is_active: boolean
  is_verified: boolean
  last_login?: string
  created_at: string
}

export interface Device {
  id: string
  user_id: string
  device_identifier: string
  device_name?: string
  device_model?: string
  os_type?: string
  os_version?: string
  app_version?: string
  status: DeviceStatus
  authorized_at?: string
  last_seen?: string
  created_at: string
}

export interface EvidenceMetadata {
  id: string
  latitude: number
  longitude: number
  gps_accuracy_meters?: number
  altitude_meters?: number
  capture_timestamp: string
  timezone?: string
  device_identifier?: string
  device_model?: string
  os_type?: string
  os_version?: string
  image_width?: number
  image_height?: number
}

export interface AIVerification {
  id: string
  status: AIStatus
  tamper_probability?: number
  confidence_score?: number
  verification_message?: string
  ela_score?: number
  noise_score?: number
  metadata_consistent?: boolean
  model_version?: string
  verified_at?: string
}

export interface BlockchainRecord {
  id: string
  image_hash: string
  transaction_id?: string
  block_number?: number
  block_hash?: string
  chain_id?: string
  provider: string
  status: BlockchainStatus
  registered_at?: string
  last_verified_at?: string
}

export interface Evidence {
  id: string
  evidence_number: string
  user_id: string
  device_id: string
  image_filename: string
  image_mime_type: string
  image_size_bytes: number
  image_sha256_hash: string
  storage_url?: string
  thumbnail_url?: string
  status: EvidenceStatus
  rejection_reason?: string
  notes?: string
  created_at: string
  updated_at: string
  metadata_?: EvidenceMetadata
  ai_verification?: AIVerification
  blockchain_record?: BlockchainRecord
  user?: User
}

export interface GISMarker {
  evidence_id: string
  evidence_number: string
  latitude: number
  longitude: number
  status: EvidenceStatus
  capture_timestamp: string
  officer_name: string
  ai_status?: AIStatus
  ai_confidence?: number
  blockchain_status?: BlockchainStatus
  thumbnail_url?: string
}

export interface AuditLog {
  id: string
  user_id?: string
  action: AuditAction
  resource_type?: string
  resource_id?: string
  description?: string
  ip_address?: string
  device_id?: string
  result?: string
  created_at: string
  user?: User
}

export interface DashboardStats {
  total_evidence: number
  verified_evidence: number
  suspicious_evidence: number
  pending_sync: number
  active_users: number
  registered_devices: number
  authorized_devices: number
  blockchain_records: number
  evidence_today: number
  evidence_this_week: number
}

export interface PaginatedResponse<T> {
  total: number
  page: number
  page_size: number
  pages: number
  items: T[]
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
  user: User
}

export interface AIVerifyResult {
  status: AIStatus
  tamper_probability: number
  confidence: number
  message: string
  details?: Record<string, unknown>
}

export interface BlockchainVerifyResult {
  is_valid: boolean
  evidence_id: string
  registered_hash: string
  current_hash: string
  transaction_id?: string
  block_number?: number
  provider: string
  verified_at: string
}
