import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../models/user.dart';
import '../models/evidence.dart';

/// REST API service — handles JWT auth headers, token refresh, and all API calls.
class ApiService {
  static const String _baseUrl = String.fromEnvironment(
    'API_URL',
    defaultValue: 'http://10.191.248.237:8000', // Local WiFi IP for physical mobile testing
  );

  static const FlutterSecureStorage _storage = FlutterSecureStorage();

  // ─── Auth tokens ──────────────────────────────────────────────────────────

  static Future<String?> getAccessToken() => _storage.read(key: 'access_token');
  static Future<String?> getRefreshToken() => _storage.read(key: 'refresh_token');

  static Future<void> _saveTokens(String access, String refresh) async {
    await _storage.write(key: 'access_token', value: access);
    await _storage.write(key: 'refresh_token', value: refresh);
  }

  static Future<void> clearTokens() async {
    await _storage.deleteAll();
  }

  static Future<Map<String, String>> _authHeaders() async {
    final token = await getAccessToken();
    return {
      'Content-Type': 'application/json',
      if (token != null) 'Authorization': 'Bearer $token',
    };
  }

  static Future<http.Response> _refreshAndRetry(
    Future<http.Response> Function() request,
  ) async {
    final refreshToken = await getRefreshToken();
    if (refreshToken == null) throw Exception('Not authenticated');

    final res = await http.post(
      Uri.parse('$_baseUrl/api/auth/refresh'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'refresh_token': refreshToken}),
    );

    if (res.statusCode == 200) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      await _saveTokens(data['access_token'], data['refresh_token']);
      return await request();
    } else {
      await clearTokens();
      throw Exception('Session expired. Please log in again.');
    }
  }

  static Future<http.Response> _get(String path) async {
    final headers = await _authHeaders();
    final res = await http.get(Uri.parse('$_baseUrl$path'), headers: headers);
    if (res.statusCode == 401) return _refreshAndRetry(() => _get(path));
    return res;
  }

  static Future<http.Response> _post(String path, Map<String, dynamic> body) async {
    final headers = await _authHeaders();
    final res = await http.post(
      Uri.parse('$_baseUrl$path'),
      headers: headers,
      body: jsonEncode(body),
    );
    if (res.statusCode == 401) return _refreshAndRetry(() => _post(path, body));
    return res;
  }

  // ─── Auth ─────────────────────────────────────────────────────────────────

  static Future<Map<String, dynamic>> login(String email, String password) async {
    final res = await http.post(
      Uri.parse('$_baseUrl/api/auth/login'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'email': email, 'password': password}),
    );

    if (res.statusCode == 200) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      await _saveTokens(data['access_token'], data['refresh_token']);
      return data;
    }

    final err = jsonDecode(res.body);
    throw Exception(err['detail'] ?? 'Login failed');
  }

  static Future<UserModel> getMe() async {
    final res = await _get('/api/auth/me');
    if (res.statusCode == 200) return UserModel.fromJson(jsonDecode(res.body));
    throw Exception('Failed to get user profile');
  }

  static Future<void> logout() async {
    try { await _post('/api/auth/logout', {}); } catch (_) {}
    await clearTokens();
  }

  // ─── Device Registration ──────────────────────────────────────────────────

  static Future<Map<String, dynamic>> registerDevice({
    required String deviceIdentifier,
    required String deviceName,
    required String deviceModel,
    required String osType,
    required String osVersion,
    String appVersion = '1.0.0',
  }) async {
    final res = await _post('/api/devices/register', {
      'device_identifier': deviceIdentifier,
      'device_name': deviceName,
      'device_model': deviceModel,
      'os_type': osType,
      'os_version': osVersion,
      'app_version': appVersion,
    });

    if (res.statusCode == 201 || res.statusCode == 200) {
      return jsonDecode(res.body) as Map<String, dynamic>;
    }
    throw Exception('Device registration failed: ${res.body}');
  }

  // ─── Evidence Upload ──────────────────────────────────────────────────────

  static Future<Map<String, dynamic>> uploadEvidence({
    required String imagePath,
    required Map<String, dynamic> metadata,
  }) async {
    final token = await getAccessToken();
    final uri = Uri.parse('$_baseUrl/api/sync/upload');
    final request = http.MultipartRequest('POST', uri);

    if (token != null) request.headers['Authorization'] = 'Bearer $token';
    request.files.add(await http.MultipartFile.fromPath('file', imagePath));
    request.fields['metadata_json'] = jsonEncode(metadata);

    final streamed = await request.send();
    final res = await http.Response.fromStream(streamed);

    if (res.statusCode == 201 || res.statusCode == 200) {
      return jsonDecode(res.body) as Map<String, dynamic>;
    }

    if (res.statusCode == 401) {
      // Try refresh
      final refreshToken = await getRefreshToken();
      if (refreshToken != null) {
        final refreshRes = await http.post(
          Uri.parse('$_baseUrl/api/auth/refresh'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({'refresh_token': refreshToken}),
        );
        if (refreshRes.statusCode == 200) {
          final data = jsonDecode(refreshRes.body) as Map<String, dynamic>;
          await _saveTokens(data['access_token'], data['refresh_token']);
          return uploadEvidence(imagePath: imagePath, metadata: metadata);
        }
      }
    }

    final err = jsonDecode(res.body);
    throw Exception(err['detail'] ?? 'Upload failed (${res.statusCode})');
  }

  // ─── Evidence List ────────────────────────────────────────────────────────

  static Future<List<Evidence>> getMyEvidence({int page = 1}) async {
    final res = await _get('/api/evidence?page=$page&page_size=50');
    if (res.statusCode == 200) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      final items = data['items'] as List;
      return items.map((e) => Evidence.fromJson(e as Map<String, dynamic>)).toList();
    }
    throw Exception('Failed to load evidence');
  }

  // ─── Dashboard Stats ──────────────────────────────────────────────────────

  static Future<Map<String, dynamic>> getDashboardStats() async {
    final res = await _get('/api/dashboard/statistics');
    if (res.statusCode == 200) return jsonDecode(res.body) as Map<String, dynamic>;
    return {};
  }
}
