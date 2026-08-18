import 'package:sqflite/sqflite.dart';
import 'package:path/path.dart';
import '../models/evidence.dart';

/// Local SQLite database for offline evidence storage.
/// Evidence is NEVER deleted before successful synchronization.
class LocalDatabase {
  static Database? _db;
  static const String _dbName = 'giotag_offline.db';
  static const int _version = 1;

  static Future<Database> get database async {
    _db ??= await _openDatabase();
    return _db!;
  }

  static Future<Database> _openDatabase() async {
    final dbPath = await getDatabasesPath();
    final path = join(dbPath, _dbName);

    return openDatabase(
      path,
      version: _version,
      onCreate: (db, version) async {
        await db.execute('''
          CREATE TABLE evidence (
            id TEXT PRIMARY KEY,
            evidence_number TEXT NOT NULL,
            user_id TEXT NOT NULL,
            device_id TEXT NOT NULL,
            image_filename TEXT NOT NULL,
            image_mime_type TEXT NOT NULL,
            image_size_bytes INTEGER NOT NULL,
            image_sha256_hash TEXT NOT NULL,
            storage_url TEXT,
            status TEXT NOT NULL DEFAULT 'PENDING_SYNC',
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            gps_accuracy_meters REAL,
            capture_timestamp TEXT NOT NULL,
            timezone TEXT,
            device_identifier TEXT,
            device_model TEXT,
            os_type TEXT,
            os_version TEXT,
            app_version TEXT,
            ai_status TEXT,
            blockchain_status TEXT,
            is_synced INTEGER NOT NULL DEFAULT 0,
            sync_error TEXT,
            created_at TEXT NOT NULL,
            local_image_path TEXT
          )
        ''');

        await db.execute('''
          CREATE TABLE sync_queue (
            id TEXT PRIMARY KEY,
            evidence_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            attempt_count INTEGER NOT NULL DEFAULT 0,
            last_attempt_at TEXT,
            error_message TEXT,
            created_at TEXT NOT NULL
          )
        ''');
      },
    );
  }

  // ─── Evidence CRUD ────────────────────────────────────────────────────────

  static Future<void> insertEvidence(Evidence evidence, {String? localImagePath}) async {
    final db = await database;
    final map = evidence.toLocalDb();
    if (localImagePath != null) map['local_image_path'] = localImagePath;
    await db.insert('evidence', map, conflictAlgorithm: ConflictAlgorithm.replace);
  }

  static Future<List<Evidence>> getAllEvidence({String? statusFilter}) async {
    final db = await database;
    final where = statusFilter != null ? 'status = ?' : null;
    final args = statusFilter != null ? [statusFilter] : null;
    final rows = await db.query('evidence', where: where, whereArgs: args, orderBy: 'created_at DESC');
    return rows.map(Evidence.fromLocalDb).toList();
  }

  static Future<List<Evidence>> getPendingSync() async {
    final db = await database;
    final rows = await db.query('evidence', where: 'is_synced = 0', orderBy: 'created_at ASC');
    return rows.map(Evidence.fromLocalDb).toList();
  }

  static Future<String?> getLocalImagePath(String evidenceId) async {
    final db = await database;
    final rows = await db.query('evidence', columns: ['local_image_path'], where: 'id = ?', whereArgs: [evidenceId]);
    if (rows.isEmpty) return null;
    return rows.first['local_image_path'] as String?;
  }

  static Future<void> markSynced(String evidenceId) async {
    final db = await database;
    await db.update(
      'evidence',
      {'is_synced': 1, 'status': 'UPLOADED', 'sync_error': null},
      where: 'id = ?',
      whereArgs: [evidenceId],
    );
  }

  static Future<void> markSyncFailed(String evidenceId, String error) async {
    final db = await database;
    await db.update(
      'evidence',
      {'sync_error': error},
      where: 'id = ?',
      whereArgs: [evidenceId],
    );
  }

  static Future<int> countPending() async {
    final db = await database;
    final result = await db.rawQuery('SELECT COUNT(*) as c FROM evidence WHERE is_synced = 0');
    return result.first['c'] as int;
  }

  static Future<int> countTotal() async {
    final db = await database;
    final result = await db.rawQuery('SELECT COUNT(*) as c FROM evidence');
    return result.first['c'] as int;
  }
}
