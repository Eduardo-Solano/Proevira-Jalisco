import 'dart:convert';

import 'package:path/path.dart' as path;
import 'package:sqflite/sqflite.dart';

import '../models/alerta.dart';
import '../models/clue.dart';
import '../models/registro_sintomas.dart';

class DatabaseHelper {
  DatabaseHelper._();
  static final instance = DatabaseHelper._();

  Database? _database;

  Future<Database> get database async {
    if (_database != null) return _database!;
    final directory = await getDatabasesPath();
    _database = await openDatabase(
      path.join(directory, 'proevira.db'),
      version: 2,
      onCreate: (db, version) async {
        await db.execute('''
          CREATE TABLE alerts (
            id INTEGER PRIMARY KEY,
            municipio TEXT NOT NULL,
            nivel TEXT NOT NULL,
            mensaje TEXT NOT NULL,
            ts TEXT NOT NULL,
            activa INTEGER NOT NULL
          )
        ''');
        await db.execute('''
          CREATE TABLE clues (
            clues TEXT PRIMARY KEY,
            nombre TEXT NOT NULL,
            direccion TEXT NOT NULL,
            nivel_atencion TEXT NOT NULL,
            distancia_km REAL NOT NULL,
            lat REAL NOT NULL,
            lon REAL NOT NULL,
            telefono TEXT,
            horario TEXT
          )
        ''');
        await db.execute('''
          CREATE TABLE pending_symptoms (
            id_local TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL
          )
        ''');
        await db.execute('''
          CREATE TABLE symptom_records (
            id_local TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            synced INTEGER NOT NULL
          )
        ''');
      },
      onUpgrade: (db, oldVersion, newVersion) async {
        if (oldVersion < 2) {
          await db.execute('''
            CREATE TABLE symptom_records (
              id_local TEXT PRIMARY KEY,
              payload TEXT NOT NULL,
              synced INTEGER NOT NULL
            )
          ''');
        }
      },
    );
    return _database!;
  }

  Future<void> replaceAlerts(List<Alerta> alerts) async {
    final db = await database;
    final batch = db.batch()..delete('alerts');
    for (final alert in alerts) {
      batch.insert('alerts', alert.toMap());
    }
    await batch.commit(noResult: true);
  }

  Future<List<Alerta>> getAlerts() async {
    final rows = await (await database).query('alerts', orderBy: 'ts DESC');
    return rows
        .map(
          (row) => Alerta(
            id: row['id']! as int,
            municipio: row['municipio']! as String,
            nivel: row['nivel']! as String,
            mensaje: row['mensaje']! as String,
            timestamp: DateTime.parse(row['ts']! as String),
            activa: row['activa'] == 1,
          ),
        )
        .toList();
  }

  Future<void> replaceClues(List<Clue> clues) async {
    final db = await database;
    final batch = db.batch()..delete('clues');
    for (final clue in clues) {
      batch.insert('clues', clue.toMap());
    }
    await batch.commit(noResult: true);
  }

  Future<List<Clue>> getClues() async {
    final rows = await (await database).query('clues', orderBy: 'distancia_km');
    return rows
        .map(
          (row) => Clue(
            clues: row['clues']! as String,
            nombre: row['nombre']! as String,
            direccion: row['direccion']! as String,
            nivelAtencion: row['nivel_atencion']! as String,
            distanciaKm: (row['distancia_km']! as num).toDouble(),
            lat: (row['lat']! as num).toDouble(),
            lon: (row['lon']! as num).toDouble(),
            telefono: row['telefono'] as String?,
            horario: row['horario'] as String?,
          ),
        )
        .toList();
  }

  Future<void> enqueueSymptoms(String idLocal, String payload) async {
    final db = await database;
    await db.insert(
      'pending_symptoms',
      {
        'id_local': idLocal,
        'payload': payload,
        'created_at': DateTime.now().toIso8601String(),
      },
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
    await db.insert(
      'symptom_records',
      {'id_local': idLocal, 'payload': payload, 'synced': 0},
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  Future<List<Map<String, Object?>>> pendingSymptoms() async =>
      (await database).query('pending_symptoms', orderBy: 'created_at');

  Future<void> removePendingSymptom(String idLocal) async {
    final db = await database;
    await db.delete(
      'pending_symptoms',
      where: 'id_local = ?',
      whereArgs: [idLocal],
    );
    await db.update(
      'symptom_records',
      {'synced': 1},
      where: 'id_local = ?',
      whereArgs: [idLocal],
    );
  }

  Future<void> saveSyncedSymptom(
    Map<String, dynamic> payload,
    Map<String, dynamic> response,
  ) async {
    await (await database).insert(
      'symptom_records',
      {
        'id_local': payload['id_local'],
        'payload': jsonEncode({
          ...payload,
          'sospecha_enfermedad': response['sospecha_sugerida'],
          'recomendacion': response['recomendacion'],
        }),
        'synced': 1,
      },
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  Future<List<RegistroSintomas>> getLocalSymptoms() async {
    final rows = await (await database).query(
      'symptom_records',
      orderBy: 'rowid DESC',
    );
    return rows.map((row) {
      final payload =
          jsonDecode(row['payload']! as String) as Map<String, dynamic>;
      return RegistroSintomas.fromPayload(
        payload,
        sincronizado: row['synced'] == 1,
      );
    }).toList();
  }
}
