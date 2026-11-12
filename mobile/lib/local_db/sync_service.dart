import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:http/http.dart' as http;

import '../api/api_client.dart';
import 'database_helper.dart';

class SyncService {
  SyncService(this.api, this.database);

  final ApiClient api;
  final DatabaseHelper database;
  StreamSubscription<List<ConnectivityResult>>? _subscription;

  Future<void> start() async {
    await syncPending();
    _subscription = Connectivity().onConnectivityChanged.listen((_) {
      syncPending();
    });
  }

  Future<void> syncPending() async {
    if (api.token == null) return;
    for (final item in await database.pendingSymptoms()) {
      final idLocal = item['id_local']! as String;
      try {
        final payload = jsonDecode(item['payload']! as String);
        final response =
            await api.postSymptoms(Map<String, dynamic>.from(payload));
        await database.saveSyncedSymptom(
          Map<String, dynamic>.from(payload),
          response,
        );
        await database.removePendingSymptom(idLocal);
      } on ApiException {
        // Keep the item queued; it can be retried after connectivity returns.
      } on http.ClientException {
        // Keep the item queued when the backend cannot be reached.
      } on SocketException {
        // Keep the item queued when the device is offline.
      } on FormatException {
        await database.removePendingSymptom(idLocal);
      }
    }
  }

  Future<void> dispose() async => _subscription?.cancel();
}
