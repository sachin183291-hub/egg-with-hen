// Evidence model matching backend schema
class Evidence {
  final String id;
  final String evidenceNumber;
  final String userId;
  final String deviceId;
  final String imageFilename;
  final String imageMimeType;
  final int imageSizeBytes;
  final String imageSha256Hash;
  final String? storageUrl;
  final String status;
  final double latitude;
  final double longitude;
  final double? gpsAccuracyMeters;
  final DateTime captureTimestamp;
  final String? timezone;
  final String? deviceIdentifier;
  final String? deviceModel;
  final String? osType;
  final String? osVersion;
  final String? appVersion;
  final String? aiStatus;
  final double? aiTamperProbability;
  final double? aiConfidenceScore;
  final String? blockchainStatus;
  final String? blockchainTxId;
  final bool isSynced;
  final String? syncError;
  final DateTime createdAt;

  const Evidence({
    required this.id,
    required this.evidenceNumber,
    required this.userId,
    required this.deviceId,
    required this.imageFilename,
    required this.imageMimeType,
    required this.imageSizeBytes,
    required this.imageSha256Hash,
    this.storageUrl,
    required this.status,
    required this.latitude,
    required this.longitude,
    this.gpsAccuracyMeters,
    required this.captureTimestamp,
    this.timezone,
    this.deviceIdentifier,
    this.deviceModel,
    this.osType,
    this.osVersion,
    this.appVersion,
    this.aiStatus,
    this.aiTamperProbability,
    this.aiConfidenceScore,
    this.blockchainStatus,
    this.blockchainTxId,
    required this.isSynced,
    this.syncError,
    required this.createdAt,
  });

  factory Evidence.fromJson(Map<String, dynamic> json) {
    final meta = json['metadata_'] as Map<String, dynamic>?;
    final ai = json['ai_verification'] as Map<String, dynamic>?;
    final bc = json['blockchain_record'] as Map<String, dynamic>?;

    return Evidence(
      id: json['id'] as String,
      evidenceNumber: json['evidence_number'] as String,
      userId: json['user_id'] as String,
      deviceId: json['device_id'] as String,
      imageFilename: json['image_filename'] as String,
      imageMimeType: json['image_mime_type'] as String,
      imageSizeBytes: json['image_size_bytes'] as int,
      imageSha256Hash: json['image_sha256_hash'] as String,
      storageUrl: json['storage_url'] as String?,
      status: json['status'] as String,
      latitude: (meta?['latitude'] as num?)?.toDouble() ?? 0.0,
      longitude: (meta?['longitude'] as num?)?.toDouble() ?? 0.0,
      gpsAccuracyMeters: (meta?['gps_accuracy_meters'] as num?)?.toDouble(),
      captureTimestamp: DateTime.parse(
        meta?['capture_timestamp'] as String? ?? json['created_at'] as String
      ),
      timezone: meta?['timezone'] as String?,
      deviceIdentifier: meta?['device_identifier'] as String?,
      deviceModel: meta?['device_model'] as String?,
      osType: meta?['os_type'] as String?,
      osVersion: meta?['os_version'] as String?,
      appVersion: meta?['app_version'] as String?,
      aiStatus: ai?['status'] as String?,
      aiTamperProbability: (ai?['tamper_probability'] as num?)?.toDouble(),
      aiConfidenceScore: (ai?['confidence_score'] as num?)?.toDouble(),
      blockchainStatus: bc?['status'] as String?,
      blockchainTxId: bc?['transaction_id'] as String?,
      isSynced: json['status'] != 'PENDING_SYNC',
      createdAt: DateTime.parse(json['created_at'] as String),
    );
  }

  Map<String, dynamic> toLocalDb() => {
    'id': id,
    'evidence_number': evidenceNumber,
    'user_id': userId,
    'device_id': deviceId,
    'image_filename': imageFilename,
    'image_mime_type': imageMimeType,
    'image_size_bytes': imageSizeBytes,
    'image_sha256_hash': imageSha256Hash,
    'storage_url': storageUrl,
    'status': status,
    'latitude': latitude,
    'longitude': longitude,
    'gps_accuracy_meters': gpsAccuracyMeters,
    'capture_timestamp': captureTimestamp.toIso8601String(),
    'timezone': timezone,
    'device_identifier': deviceIdentifier,
    'device_model': deviceModel,
    'os_type': osType,
    'os_version': osVersion,
    'app_version': appVersion,
    'ai_status': aiStatus,
    'blockchain_status': blockchainStatus,
    'is_synced': isSynced ? 1 : 0,
    'sync_error': syncError,
    'created_at': createdAt.toIso8601String(),
  };

  factory Evidence.fromLocalDb(Map<String, dynamic> row) => Evidence(
    id: row['id'] as String,
    evidenceNumber: row['evidence_number'] as String,
    userId: row['user_id'] as String,
    deviceId: row['device_id'] as String? ?? '',
    imageFilename: row['image_filename'] as String,
    imageMimeType: row['image_mime_type'] as String,
    imageSizeBytes: row['image_size_bytes'] as int,
    imageSha256Hash: row['image_sha256_hash'] as String,
    storageUrl: row['storage_url'] as String?,
    status: row['status'] as String,
    latitude: (row['latitude'] as num).toDouble(),
    longitude: (row['longitude'] as num).toDouble(),
    gpsAccuracyMeters: (row['gps_accuracy_meters'] as num?)?.toDouble(),
    captureTimestamp: DateTime.parse(row['capture_timestamp'] as String),
    timezone: row['timezone'] as String?,
    deviceIdentifier: row['device_identifier'] as String?,
    deviceModel: row['device_model'] as String?,
    osType: row['os_type'] as String?,
    osVersion: row['os_version'] as String?,
    appVersion: row['app_version'] as String?,
    aiStatus: row['ai_status'] as String?,
    blockchainStatus: row['blockchain_status'] as String?,
    isSynced: (row['is_synced'] as int? ?? 0) == 1,
    syncError: row['sync_error'] as String?,
    createdAt: DateTime.parse(row['created_at'] as String),
  );

  Evidence copyWith({ String? status, bool? isSynced, String? syncError }) => Evidence(
    id: id, evidenceNumber: evidenceNumber, userId: userId, deviceId: deviceId,
    imageFilename: imageFilename, imageMimeType: imageMimeType,
    imageSizeBytes: imageSizeBytes, imageSha256Hash: imageSha256Hash,
    storageUrl: storageUrl, status: status ?? this.status,
    latitude: latitude, longitude: longitude,
    gpsAccuracyMeters: gpsAccuracyMeters, captureTimestamp: captureTimestamp,
    timezone: timezone, deviceIdentifier: deviceIdentifier,
    deviceModel: deviceModel, osType: osType, osVersion: osVersion,
    appVersion: appVersion, aiStatus: aiStatus,
    aiTamperProbability: aiTamperProbability, aiConfidenceScore: aiConfidenceScore,
    blockchainStatus: blockchainStatus, blockchainTxId: blockchainTxId,
    isSynced: isSynced ?? this.isSynced,
    syncError: syncError ?? this.syncError, createdAt: createdAt,
  );
}
