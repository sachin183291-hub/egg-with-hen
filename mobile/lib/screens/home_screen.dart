import 'dart:io';
import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
import 'package:geolocator/geolocator.dart';
import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:provider/provider.dart';
import '../services/auth_provider.dart';
import '../services/evidence_service.dart';
import '../services/local_database.dart';
import '../services/api_service.dart';
import '../models/evidence.dart';

class HomeScreen extends StatefulWidget {
  final List<CameraDescription> cameras;
  const HomeScreen({super.key, required this.cameras});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> with SingleTickerProviderStateMixin {
  int _selectedTab = 0;
  int _pendingCount = 0;
  Map<String, dynamic> _stats = {};
  bool _syncing = false;

  @override
  void initState() {
    super.initState();
    _loadStats();
    _listenConnectivity();
  }

  Future<void> _loadStats() async {
    final pending = await LocalDatabase.countPending();
    final total = await LocalDatabase.countTotal();
    setState(() { _pendingCount = pending; });

    try {
      final s = await ApiService.getDashboardStats();
      setState(() { _stats = s; });
    } catch (_) {}
  }

  void _listenConnectivity() {
    Connectivity().onConnectivityChanged.listen((results) async {
      final connected = results.any((r) => r != ConnectivityResult.none);
      if (connected && _pendingCount > 0) {
        _syncPending();
      }
    });
  }

  Future<void> _syncPending() async {
    if (_syncing) return;
    setState(() => _syncing = true);

    final result = await EvidenceService.syncAllPending();
    await _loadStats();
    setState(() => _syncing = false);

    if (mounted && (result.successCount + result.failedCount) > 0) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text('Synced ${result.successCount} / ${result.successCount + result.failedCount} items'),
        backgroundColor: result.failedCount == 0 ? const Color(0xFF10B981) : const Color(0xFFF59E0B),
      ));
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();
    final user = auth.user;

    final tabs = [
      _HomeTab(cameras: widget.cameras, onCapture: _loadStats),
      _EvidenceListTab(),
      _ProfileTab(stats: _stats, pendingCount: _pendingCount, onSync: _syncPending, syncing: _syncing),
    ];

    return Scaffold(
      backgroundColor: const Color(0xFF0A0E1A),
      body: tabs[_selectedTab],
      bottomNavigationBar: Container(
        decoration: const BoxDecoration(
          color: Color(0xFF111827),
          border: Border(top: BorderSide(color: Color(0xFF1E2C42), width: 1)),
        ),
        child: BottomNavigationBar(
          currentIndex: _selectedTab,
          onTap: (i) => setState(() => _selectedTab = i),
          backgroundColor: Colors.transparent,
          selectedItemColor: const Color(0xFF818CF8),
          unselectedItemColor: const Color(0xFF64748B),
          elevation: 0,
          items: [
            const BottomNavigationBarItem(icon: Icon(Icons.camera_alt), label: 'Capture'),
            BottomNavigationBarItem(
              icon: Stack(children: [
                const Icon(Icons.photo_library),
                if (_pendingCount > 0) Positioned(
                  right: 0, top: 0,
                  child: Container(
                    width: 14, height: 14,
                    decoration: const BoxDecoration(color: Color(0xFFEF4444), shape: BoxShape.circle),
                    child: Center(child: Text('$_pendingCount', style: const TextStyle(fontSize: 8, color: Colors.white, fontWeight: FontWeight.bold))),
                  ),
                ),
              ]),
              label: 'Evidence',
            ),
            const BottomNavigationBarItem(icon: Icon(Icons.person), label: 'Profile'),
          ],
        ),
      ),
    );
  }
}

// ─── Camera Capture Tab ────────────────────────────────────────────────────────

class _HomeTab extends StatefulWidget {
  final List<CameraDescription> cameras;
  final VoidCallback onCapture;
  const _HomeTab({required this.cameras, required this.onCapture});

  @override
  State<_HomeTab> createState() => _HomeTabState();
}

class _HomeTabState extends State<_HomeTab> {
  CameraController? _controller;
  bool _isInitialized = false;
  bool _capturing = false;
  Position? _position;
  String _gpsStatus = 'Getting GPS...';
  String? _statusMessage;
  bool _success = false;

  @override
  void initState() {
    super.initState();
    _initCamera();
    _getGPS();
  }

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  Future<void> _initCamera() async {
    if (widget.cameras.isEmpty) return;
    _controller = CameraController(widget.cameras[0], ResolutionPreset.high);
    try {
      await _controller!.initialize();
      if (mounted) setState(() => _isInitialized = true);
    } catch (e) {
      if (mounted) setState(() => _gpsStatus = 'Camera error: $e');
    }
  }

  Future<void> _getGPS() async {
    setState(() => _gpsStatus = 'Acquiring GPS...');
    try {
      final pos = await EvidenceService.getCurrentPosition();
      if (pos != null) {
        setState(() {
          _position = pos;
          _gpsStatus = '📍 ${pos.latitude.toStringAsFixed(5)}, ${pos.longitude.toStringAsFixed(5)} (±${pos.accuracy.toStringAsFixed(0)}m)';
        });
      } else {
        setState(() => _gpsStatus = '⚠️ GPS unavailable — check permissions');
      }
    } catch (e) {
      setState(() => _gpsStatus = '⚠️ GPS error: $e');
    }
  }

  Future<void> _capture() async {
    if (_controller == null || !_isInitialized || _capturing || _position == null) return;
    setState(() { _capturing = true; _statusMessage = null; _success = false; });

    try {
      final auth = context.read<AuthProvider>();
      final deviceInfo = await EvidenceService.getDeviceInfo();
      final xFile = await _controller!.takePicture();

      final evidence = await EvidenceService.createLocalEvidence(
        imagePath: xFile.path,
        position: _position!,
        userId: auth.user!.id,
        deviceInfo: deviceInfo,
      );

      setState(() {
        _statusMessage = '✅ Captured: ${evidence.evidenceNumber}\nHash: ${evidence.imageSha256Hash.substring(0, 16)}...';
        _success = true;
      });

      widget.onCapture();

      // Try immediate sync
      final result = await EvidenceService.syncEvidence(evidence);
      if (mounted) {
        setState(() {
          _statusMessage = result.success
            ? '✅ ${evidence.evidenceNumber} captured & uploaded!'
            : '✅ ${evidence.evidenceNumber} captured (offline — will sync later)';
        });
      }
    } catch (e) {
      setState(() {
        _statusMessage = '❌ Capture failed: $e';
        _success = false;
      });
    } finally {
      if (mounted) setState(() => _capturing = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Column(
        children: [
          // Header
          Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                const Text('🛡️ ', style: TextStyle(fontSize: 20)),
                const Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Secure Capture', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: Color(0xFFF1F5F9))),
                    Text('GioTag Evidence System', style: TextStyle(fontSize: 11, color: Color(0xFF64748B))),
                  ],
                ),
              ],
            ),
          ),

          // GPS Status
          Container(
            margin: const EdgeInsets.symmetric(horizontal: 16),
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            decoration: BoxDecoration(
              color: _position != null ? const Color(0xFF10B981).withOpacity(0.1) : const Color(0xFFF59E0B).withOpacity(0.1),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: _position != null ? const Color(0xFF10B981).withOpacity(0.3) : const Color(0xFFF59E0B).withOpacity(0.3)),
            ),
            child: Row(
              children: [
                Icon(Icons.location_on, size: 14, color: _position != null ? const Color(0xFF10B981) : const Color(0xFFF59E0B)),
                const SizedBox(width: 6),
                Expanded(child: Text(_gpsStatus, style: TextStyle(fontSize: 11, color: _position != null ? const Color(0xFF10B981) : const Color(0xFFF59E0B)))),
                GestureDetector(onTap: _getGPS, child: const Icon(Icons.refresh, size: 16, color: Color(0xFF64748B))),
              ],
            ),
          ),

          const SizedBox(height: 12),

          // Camera Preview
          Expanded(
            child: Container(
              margin: const EdgeInsets.symmetric(horizontal: 16),
              decoration: BoxDecoration(
                color: const Color(0xFF1A2235),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: const Color(0xFF1E2C42)),
              ),
              clipBehavior: Clip.hardEdge,
              child: _isInitialized && _controller != null
                ? ClipRRect(
                    borderRadius: BorderRadius.circular(16),
                    child: CameraPreview(_controller!),
                  )
                : const Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.camera_alt, size: 48, color: Color(0xFF475569)),
                        SizedBox(height: 8),
                        Text('Camera initializing...', style: TextStyle(color: Color(0xFF64748B))),
                      ],
                    ),
                  ),
            ),
          ),

          // Status Message
          if (_statusMessage != null)
            Container(
              margin: const EdgeInsets.fromLTRB(16, 12, 16, 0),
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: _success ? const Color(0xFF10B981).withOpacity(0.1) : const Color(0xFFEF4444).withOpacity(0.1),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: _success ? const Color(0xFF10B981).withOpacity(0.3) : const Color(0xFFEF4444).withOpacity(0.3)),
              ),
              child: Text(_statusMessage!, style: TextStyle(fontSize: 12, color: _success ? const Color(0xFF10B981) : const Color(0xFFEF4444))),
            ),

          // Capture Button
          Padding(
            padding: const EdgeInsets.all(20),
            child: GestureDetector(
              onTap: _capturing || !_isInitialized || _position == null ? null : _capture,
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                width: 72, height: 72,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  gradient: LinearGradient(
                    colors: _capturing || _position == null
                      ? [const Color(0xFF374151), const Color(0xFF4B5563)]
                      : [const Color(0xFF4F46E5), const Color(0xFF818CF8)],
                  ),
                  boxShadow: [BoxShadow(
                    color: const Color(0xFF6366F1).withOpacity(0.4),
                    blurRadius: 20, offset: const Offset(0, 4),
                  )],
                ),
                child: _capturing
                  ? const Padding(padding: EdgeInsets.all(20), child: CircularProgressIndicator(strokeWidth: 2.5, color: Colors.white))
                  : const Icon(Icons.camera_alt, color: Colors.white, size: 32),
              ),
            ),
          ),

          if (_position == null)
            const Padding(
              padding: EdgeInsets.only(bottom: 8),
              child: Text('Waiting for GPS fix...', style: TextStyle(fontSize: 11, color: Color(0xFF64748B))),
            ),
        ],
      ),
    );
  }
}

// ─── Evidence List Tab ─────────────────────────────────────────────────────────

class _EvidenceListTab extends StatefulWidget {
  @override
  State<_EvidenceListTab> createState() => _EvidenceListTabState();
}

class _EvidenceListTabState extends State<_EvidenceListTab> {
  List<Evidence> _evidence = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final items = await LocalDatabase.getAllEvidence();
    setState(() { _evidence = items; _loading = false; });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0A0E1A),
      appBar: AppBar(
        backgroundColor: const Color(0xFF111827),
        title: const Text('Evidence', style: TextStyle(color: Color(0xFFF1F5F9))),
        actions: [IconButton(icon: const Icon(Icons.refresh, color: Color(0xFF94A3B8)), onPressed: _load)],
      ),
      body: _loading
        ? const Center(child: CircularProgressIndicator(color: Color(0xFF6366F1)))
        : _evidence.isEmpty
          ? const Center(child: Text('No evidence captured yet', style: TextStyle(color: Color(0xFF64748B))))
          : ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: _evidence.length,
              itemBuilder: (ctx, i) {
                final ev = _evidence[i];
                return Container(
                  margin: const EdgeInsets.only(bottom: 10),
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: const Color(0xFF1A2235),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: const Color(0xFF1E2C42)),
                  ),
                  child: Row(
                    children: [
                      Container(
                        width: 40, height: 40,
                        decoration: BoxDecoration(
                          color: ev.isSynced ? const Color(0xFF10B981).withOpacity(0.15) : const Color(0xFFF59E0B).withOpacity(0.15),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Icon(
                          ev.isSynced ? Icons.cloud_done : Icons.cloud_off,
                          color: ev.isSynced ? const Color(0xFF10B981) : const Color(0xFFF59E0B),
                          size: 20,
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(ev.evidenceNumber, style: const TextStyle(fontWeight: FontWeight.w700, color: Color(0xFFF1F5F9), fontSize: 14)),
                            Text('${ev.latitude.toStringAsFixed(4)}, ${ev.longitude.toStringAsFixed(4)}', style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 12)),
                            Text(ev.captureTimestamp.toString().substring(0, 16), style: const TextStyle(color: Color(0xFF64748B), fontSize: 11)),
                          ],
                        ),
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                        decoration: BoxDecoration(
                          color: ev.isSynced ? const Color(0xFF10B981).withOpacity(0.15) : const Color(0xFFF59E0B).withOpacity(0.15),
                          borderRadius: BorderRadius.circular(20),
                          border: Border.all(color: ev.isSynced ? const Color(0xFF10B981).withOpacity(0.3) : const Color(0xFFF59E0B).withOpacity(0.3)),
                        ),
                        child: Text(
                          ev.isSynced ? 'Synced' : 'Pending',
                          style: TextStyle(
                            fontSize: 10, fontWeight: FontWeight.w700,
                            color: ev.isSynced ? const Color(0xFF10B981) : const Color(0xFFF59E0B),
                          ),
                        ),
                      ),
                    ],
                  ),
                );
              },
            ),
    );
  }
}

// ─── Profile Tab ───────────────────────────────────────────────────────────────

class _ProfileTab extends StatelessWidget {
  final Map<String, dynamic> stats;
  final int pendingCount;
  final VoidCallback onSync;
  final bool syncing;

  const _ProfileTab({required this.stats, required this.pendingCount, required this.onSync, required this.syncing});

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();
    final user = auth.user;

    return Scaffold(
      backgroundColor: const Color(0xFF0A0E1A),
      appBar: AppBar(
        backgroundColor: const Color(0xFF111827),
        title: const Text('Profile', style: TextStyle(color: Color(0xFFF1F5F9))),
        actions: [
          TextButton(
            onPressed: () => auth.logout(),
            child: const Text('Logout', style: TextStyle(color: Color(0xFFEF4444))),
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            // User Card
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                gradient: const LinearGradient(colors: [Color(0xFF1A2235), Color(0xFF1E2C42)]),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: const Color(0xFF1E2C42)),
              ),
              child: Row(
                children: [
                  Container(
                    width: 52, height: 52,
                    decoration: BoxDecoration(
                      gradient: const LinearGradient(colors: [Color(0xFF4F46E5), Color(0xFF818CF8)]),
                      borderRadius: BorderRadius.circular(26),
                    ),
                    child: Center(child: Text(user?.initials ?? '?', style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 18))),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(user?.fullName ?? '—', style: const TextStyle(fontWeight: FontWeight.w700, color: Color(0xFFF1F5F9), fontSize: 16)),
                        Text(user?.email ?? '', style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 12)),
                        const SizedBox(height: 4),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                          decoration: BoxDecoration(
                            color: const Color(0xFF6366F1).withOpacity(0.15),
                            borderRadius: BorderRadius.circular(20),
                          ),
                          child: Text(user?.role.replaceAll('_', ' ') ?? '', style: const TextStyle(color: Color(0xFF818CF8), fontSize: 10, fontWeight: FontWeight.w600)),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),

            const SizedBox(height: 16),

            // Sync Status
            if (pendingCount > 0) Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: const Color(0xFFF59E0B).withOpacity(0.1),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: const Color(0xFFF59E0B).withOpacity(0.3)),
              ),
              child: Row(
                children: [
                  const Icon(Icons.cloud_off, color: Color(0xFFF59E0B)),
                  const SizedBox(width: 10),
                  Expanded(child: Text('$pendingCount evidence item(s) pending sync', style: const TextStyle(color: Color(0xFFF59E0B), fontWeight: FontWeight.w600))),
                  ElevatedButton(
                    onPressed: syncing ? null : onSync,
                    style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFFF59E0B), foregroundColor: Colors.black),
                    child: syncing ? const SizedBox(width:16, height:16, child: CircularProgressIndicator(strokeWidth:2, color: Colors.black)) : const Text('Sync Now'),
                  ),
                ],
              ),
            ),

            // Stats
            if (stats.isNotEmpty) ...[
              const SizedBox(height: 16),
              GridView.count(
                shrinkWrap: true, physics: const NeverScrollableScrollPhysics(),
                crossAxisCount: 2, mainAxisSpacing: 10, crossAxisSpacing: 10, childAspectRatio: 2,
                children: [
                  _statTile('Total Evidence', '${stats['total_evidence'] ?? 0}', const Color(0xFF6366F1)),
                  _statTile('Verified', '${stats['verified_evidence'] ?? 0}', const Color(0xFF10B981)),
                  _statTile('Suspicious', '${stats['suspicious_evidence'] ?? 0}', const Color(0xFFEF4444)),
                  _statTile('Pending Sync', '${stats['pending_sync'] ?? 0}', const Color(0xFFF59E0B)),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _statTile(String label, String value, Color color) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withOpacity(0.1),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: color.withOpacity(0.2)),
      ),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(value, style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800, color: color)),
          Text(label, style: const TextStyle(fontSize: 11, color: Color(0xFF94A3B8))),
        ],
      ),
    );
  }
}
