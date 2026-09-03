import 'dart:io';

import 'dart:ui' as ui;
import 'package:flutter/material.dart';
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
        'device_name': androidInfo.device,
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

  // ─── Geo-Stamp Overlay on Image ──────────────────────────────────────────

  /// Draws location + timestamp watermark on the bottom of the captured image.
  /// Returns path to the stamped image file.
  static Future<String> applyGeoStamp({
    required String imagePath,
    required double latitude,
    required double longitude,
    required DateTime captureTime,
  }) async {
    try {
      final originalBytes = await File(imagePath).readAsBytes();
      final codec = await ui.instantiateImageCodec(originalBytes);
      final frame = await codec.getNextFrame();
      final srcImage = frame.image;

      final width = srcImage.width.toDouble();
      final height = srcImage.height.toDouble();
      final barHeight = (height * 0.10).clamp(70.0, 120.0);
      final fontSize = (barHeight * 0.22).clamp(14.0, 26.0);

      final recorder = ui.PictureRecorder();
      final canvas = Canvas(recorder);

      // Draw original image
      canvas.drawImage(srcImage, Offset.zero, Paint());

      // Dark overlay bar at bottom
      canvas.drawRect(
        Rect.fromLTWH(0, height - barHeight, width, barHeight),
        Paint()..color = const Color(0xCC000000),
      );

      // Green left accent line
      canvas.drawRect(
        Rect.fromLTWH(0, height - barHeight, 5, barHeight),
        Paint()..color = const Color(0xFF10B981),
      );

      final textPainter = TextPainter(textDirection: TextDirection.ltr);
      final double textX = 18;

      // Capture time line
      final istTime = captureTime.toLocal();
      final timeStr =
          '📅 ${istTime.year}-${istTime.month.toString().padLeft(2, '0')}-${istTime.day.toString().padLeft(2, '0')}  '
          '${istTime.hour.toString().padLeft(2, '0')}:${istTime.minute.toString().padLeft(2, '0')}:${istTime.second.toString().padLeft(2, '0')} IST';

      textPainter.text = TextSpan(
        text: timeStr,
        style: TextStyle(color: const Color(0xFFFFFFFF), fontSize: fontSize, fontWeight: FontWeight.bold),
      );
      textPainter.layout();
      textPainter.paint(canvas, Offset(textX, height - barHeight + barHeight * 0.12));

      // GPS line
      final gpsStr =
          '📍 Lat: ${latitude.toStringAsFixed(6)}  Lng: ${longitude.toStringAsFixed(6)}';
      textPainter.text = TextSpan(
        text: gpsStr,
        style: TextStyle(color: const Color(0xFF86EFAC), fontSize: fontSize * 0.88),
      );
      textPainter.layout();
      textPainter.paint(canvas, Offset(textX, height - barHeight + barHeight * 0.52));

      // Render and save
      final picture = recorder.endRecording();
      final img = await picture.toImage(srcImage.width, srcImage.height);
      final byteData = await img.toByteData(format: ui.ImageByteFormat.png);
      if (byteData == null) return imagePath;

      final stampedPath = imagePath.replaceAll('.jpg', '_stamped.jpg');
      await File(stampedPath).writeAsBytes(byteData.buffer.asUint8List());
      return stampedPath;
    } catch (e) {
      // If stamping fails, return original path — don't block upload
      return imagePath;
    }
  }

  // ─── Create Evidence ──────────────────────────────────────────────────────

  static Future<Evidence> createLocalEvidence({
    required String imagePath,
    required Position position,
    required String userId,
    required Map<String, String> deviceInfo,
  }) async {
    // ✅ FIX: Use UTC time so backend comparison is correct
    // Backend upload_time = UTC, capture_time must also be UTC
    final nowUtc = DateTime.now().toUtc();

    // Apply geo-stamp watermark on image
    final stampedPath = await applyGeoStamp(
      imagePath: imagePath,
      latitude: position.latitude,
      longitude: position.longitude,
      captureTime: nowUtc.toLocal(), // Show local time on stamp visually
    );

    final imageFile = File(stampedPath);
    final imageBytes = await imageFile.readAsBytes();
    final hash = computeSha256(imageBytes);
    final id = _uuid.v4();
    final count = await LocalDatabase.countTotal();
    final evidenceNumber = 'EV-${nowUtc.year}-${(count + 1).toString().padLeft(5, '0')}';

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
      captureTimestamp: nowUtc, // ✅ UTC timestamp
      timezone: 'Asia/Kolkata',
      deviceIdentifier: deviceInfo['device_identifier'],
      deviceModel: deviceInfo['device_model'],
      osType: deviceInfo['os_type'],
      osVersion: deviceInfo['os_version'],
      appVersion: deviceInfo['app_version'],
      isSynced: false,
      createdAt: nowUtc,
    );

    await LocalDatabase.insertEvidence(evidence, localImagePath: stampedPath);
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
      // ✅ FIX: Always send UTC ISO8601 with 'Z' suffix so backend parses correctly
      'capture_timestamp': evidence.captureTimestamp.toUtc().toIso8601String(),
      'timezone': evidence.timezone ?? 'Asia/Kolkata',
      'device_identifier': evidence.deviceIdentifier ?? '',
      'device_model': evidence.deviceModel ?? 'Unknown',
      'os_type': evidence.osType ?? 'Android',
      'os_version': evidence.osVersion ?? '',
      'app_version': evidence.appVersion ?? '1.0.0',
      'client_hash': evidence.imageSha256Hash,
    };

    try {
      final response = await ApiService.uploadEvidence(imagePath: imagePath, metadata: metadata);
      await LocalDatabase.markSynced(evidence.id);
      // Extract verification status from backend response
      final serverStatus = response['status'] as String? ?? 'UPLOADED';
      return SyncResult(success: true, serverStatus: serverStatus);
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
  final String? serverStatus; // 'VERIFIED', 'SUSPICIOUS', 'UPLOADED' from backend
  const SyncResult({required this.success, this.error, this.serverStatus});
}

class BatchSyncResult {
  final int successCount;
  final int failedCount;
  const BatchSyncResult({required this.successCount, required this.failedCount});
}
