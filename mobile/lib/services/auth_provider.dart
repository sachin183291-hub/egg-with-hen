import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../models/user.dart';
import '../services/api_service.dart';

/// App-wide authentication state provider.
class AuthProvider extends ChangeNotifier {
  UserModel? _user;
  bool _loading = true;
  String? _error;

  UserModel? get user => _user;
  bool get loading => _loading;
  bool get isAuthenticated => _user != null;
  String? get error => _error;
  String get userRole => _user?.role ?? '';

  static const _storage = FlutterSecureStorage();

  AuthProvider() {
    _checkExistingSession();
  }

  Future<void> _checkExistingSession() async {
    try {
      final token = await _storage.read(key: 'access_token');
      if (token != null) {
        _user = await ApiService.getMe();
      }
    } catch (_) {
      await ApiService.clearTokens();
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  Future<bool> login(String email, String password) async {
    _loading = true;
    _error = null;
    notifyListeners();

    try {
      final data = await ApiService.login(email, password);
      _user = UserModel.fromJson(data['user'] as Map<String, dynamic>);
      _loading = false;
      notifyListeners();
      return true;
    } catch (e) {
      _error = e.toString().replaceAll('Exception: ', '');
      _loading = false;
      notifyListeners();
      return false;
    }
  }

  Future<void> logout() async {
    await ApiService.logout();
    _user = null;
    notifyListeners();
  }
}
