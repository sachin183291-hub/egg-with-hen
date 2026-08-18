import 'dart:io';
import 'dart:convert';
import 'package:crypto/crypto.dart';
import 'package:geolocator/geolocator.dart';
import 'package:device_info_plus/device_info_plus.dart';
import 'package:uuid/uuid.dart';
import '../models/evidence.dart';
import 'local_database.dart';
import 'api_service.dart';

/// Handles the complete secure photo capture workflow:
/// GPS → Capture → Hash → Metadata → Store → Queue/Upload
class EvidenceService {
  static const _uuid = Uuid();

  // ─── SHA-256 Hash ──────────────────────────────────────────────────────────

  static String computeSha256(List<int> bytes) {
    return sha256.convert(bytes).toString();
  }

  static Future<String> computeFileSha256(String filePath) async {
    final file = File(filePath);
    final bytes = await file.readAsBytes();
    return computeSha256(bytes);
  }

  // ─── GPS ──────────────────────────────────────────────────────────────────

  static Future<Position?> getCurrentPosition({double accuracyThreshold = 50.0}) async {
    bool serviceEnabled = await Geolocator.isLocationServiceEnabled();
    if (!serviceEnabled) return null;

    LocationPermission permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
      if (permission == LocationPermission.denied) return null;
    }
    if (permission == LocationPermission.deniedForever) return null;

    final position = await Geolocator.getCurrentPosition(
      desiredAccuracy: LocationAccuracy.best,
      timeLimit: const Duration(seconds: 30),
    );

    if (position.accuracy > accuracyThreshold) {
      // GPS accuracy below threshold — still capture but warn
    }

    return position;
  }

  // ─── Device Info ──────────────────────────────────────────────────────────

  static Future<Map<String, String>> getDeviceInfo() async {
    final deviceInfo = DeviceInfoPlugin();
    if (Platform.isAndroid) {
      final androidInfo = await deviceInfo.androidInfo;
      return {
        'device_identifier': androidInfo.id,
        'device_name': androidInfo.name,
        'device_model': '${androidInfo.manufacturer} ${androidInfo.model}',
        'os_type': 'Android',
        'os_version': androidInfo.version.release,
        'app_version': '1.0.0',
      };
    }
    // iOS fallback
    return {
      'device_identifier': _uuid.v4(),
      'device_name': 'iOS Device',
      'device_model': 'iOS',
      'os_type': 'iOS',
      'os_version': '17.0',
      'app_version': '1.0.0',
    };
  }

  // ─── Create Evidence ──────────────────────────────────────────────────────

  static Future<Evidence> createLocalEvidence({
    required String imagePath,
    required Position position,
    required String userId,
    required Map<String, String> deviceInfo,
  }) async {
    final imageFile = File(imagePath);
    final imageBytes = await imageFile.readAsBytes();
    final hash = computeSha256(imageBytes);
    final id = _uuid.v4();
    final count = await LocalDatabase.countTotal();
    final evidenceNumber = 'EV-${DateTime.now().year}-${(count + 1).toString().padLeft(5, '0')}';
    final now = DateTime.now();

    final evidence = Evidence(
      id: id,
      evidenceNumber: evidenceNumber,
      userId: userId,
      deviceId: deviceInfo['device_identifier'] ?? id,
      imageFilename: imageFile.uri.pathSegments.last,
      imageMimeType: 'image/jpeg',
      imageSizeBytes: imageBytes.length,
      imageSha256Hash: hash,
      status: 'PENDING_SYNC',
      latitude: position.latitude,
      longitude: position.longitude,
      gpsAccuracyMeters: position.accuracy,
      captureTimestamp: now,
      timezone: now.timeZoneName,
      deviceIdentifier: deviceInfo['device_identifier'],
      deviceModel: deviceInfo['device_model'],
      osType: deviceInfo['os_type'],
      osVersion: deviceInfo['os_version'],
      appVersion: deviceInfo['app_version'],
      isSynced: false,
      createdAt: now,
    );

    await LocalDatabase.insertEvidence(evidence, localImagePath: imagePath);
    return evidence;
  }

  // ─── Sync ─────────────────────────────────────────────────────────────────

  static Future<SyncResult> syncEvidence(Evidence evidence) async {
    final imagePath = await LocalDatabase.getLocalImagePath(evidence.id);
    if (imagePath == null || !File(imagePath).existsSync()) {
      return SyncResult(success: false, error: 'Local image file not found');
    }

    final metadata = {
      'latitude': evidence.latitude,
      'longitude': evidence.longitude,
      'gps_accuracy_meters': evidence.gpsAccuracyMeters,
      'capture_timestamp': evidence.captureTimestamp.toIso8601String(),
      'timezone': evidence.timezone ?? 'UTC',
      'device_identifier': evidence.deviceIdentifier ?? '',
      'device_model': evidence.deviceModel,
      'os_type': evidence.osType,
      'os_version': evidence.osVersion,
      'app_version': evidence.appVersion,
      'client_hash': evidence.imageSha256Hash,
    };

    try {
      await ApiService.uploadEvidence(imagePath: imagePath, metadata: metadata);
      await LocalDatabase.markSynced(evidence.id);
      return SyncResult(success: true);
    } catch (e) {
      final errMsg = e.toString();
      await LocalDatabase.markSyncFailed(evidence.id, errMsg);
      return SyncResult(success: false, error: errMsg);
    }
  }

  /// Sync all pending evidence (called when network is restored).
  static Future<BatchSyncResult> syncAllPending() async {
    final pending = await LocalDatabase.getPendingSync();
    int success = 0;
    int failed = 0;

    for (final ev in pending) {
      final result = await syncEvidence(ev);
      if (result.success) success++; else failed++;
    }

    return BatchSyncResult(successCount: success, failedCount: failed);
  }
}

class SyncResult {
  final bool success;
  final String? error;
  const SyncResult({required this.success, this.error});
}

class BatchSyncResult {
  final int successCount;
  final int failedCount;
  const BatchSyncResult({required this.successCount, required this.failedCount});
}
