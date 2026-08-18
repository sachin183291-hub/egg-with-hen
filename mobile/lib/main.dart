import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:camera/camera.dart';
import 'services/auth_provider.dart';
import 'screens/login_screen.dart';
import 'screens/home_screen.dart';

List<CameraDescription> _cameras = [];

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  try {
    _cameras = await availableCameras();
  } catch (_) {
    _cameras = [];
  }

  runApp(
    ChangeNotifierProvider(
      create: (_) => AuthProvider(),
      child: GioTagApp(cameras: _cameras),
    ),
  );
}

class GioTagApp extends StatelessWidget {
  final List<CameraDescription> cameras;
  const GioTagApp({super.key, required this.cameras});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'GioTag — Secure Evidence',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        brightness: Brightness.dark,
        scaffoldBackgroundColor: const Color(0xFF0A0E1A),
        colorScheme: const ColorScheme.dark(
          primary: Color(0xFF6366F1),
          secondary: Color(0xFF818CF8),
          surface: Color(0xFF1A2235),
          background: Color(0xFF0A0E1A),
        ),
        fontFamily: 'Inter',
        appBarTheme: const AppBarTheme(
          backgroundColor: Color(0xFF111827),
          elevation: 0,
          iconTheme: IconThemeData(color: Color(0xFF94A3B8)),
          titleTextStyle: TextStyle(color: Color(0xFFF1F5F9), fontSize: 18, fontWeight: FontWeight.w700),
        ),
      ),
      home: Consumer<AuthProvider>(
        builder: (ctx, auth, _) {
          if (auth.loading) {
            return const Scaffold(
              backgroundColor: Color(0xFF0A0E1A),
              body: Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text('🛡️', style: TextStyle(fontSize: 48)),
                    SizedBox(height: 16),
                    CircularProgressIndicator(color: Color(0xFF6366F1)),
                    SizedBox(height: 12),
                    Text('GioTag', style: TextStyle(color: Color(0xFFF1F5F9), fontSize: 18, fontWeight: FontWeight.bold)),
                  ],
                ),
              ),
            );
          }

          return auth.isAuthenticated
            ? HomeScreen(cameras: cameras)
            : const LoginScreen();
        },
      ),
    );
  }
}
