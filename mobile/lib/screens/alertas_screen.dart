import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';

import '../api/api_client.dart';
import '../api/ws_client.dart';
import '../local_db/database_helper.dart';
import '../models/alerta.dart';

class AlertasScreen extends StatefulWidget {
  const AlertasScreen({
    required this.api,
    required this.database,
    required this.socket,
    super.key,
  });

  final ApiClient api;
  final DatabaseHelper database;
  final AlertsSocket socket;

  @override
  State<AlertasScreen> createState() => _AlertasScreenState();
}

class _AlertasScreenState extends State<AlertasScreen> {
  List<Alerta> alerts = [];
  bool loading = true;
  String? error;
  String levelFilter = 'todas';
  String diseaseFilter = 'todas';
  bool online = true;
  StreamSubscription<List<ConnectivityResult>>? connectivity;

  @override
  void initState() {
    super.initState();
    connectivity = Connectivity().onConnectivityChanged.listen((result) {
      if (mounted) {
        setState(() =>
            online = result.any((item) => item != ConnectivityResult.none));
      }
    });
    widget.socket.events.listen((json) {
      if (mounted) setState(() => alerts = [Alerta.fromJson(json), ...alerts]);
    });
    load();
  }

  @override
  void dispose() {
    connectivity?.cancel();
    super.dispose();
  }

  Future<void> load() async {
    try {
      final remote = await widget.api.getAlerts();
      await widget.database.replaceAlerts(remote);
      if (mounted) setState(() => alerts = remote);
    } catch (exception) {
      final cached = await widget.database.getAlerts();
      if (mounted) {
        setState(() {
          alerts = cached;
          error = 'Mostrando datos guardados sin conexión.';
        });
      }
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Color levelColor(String level) {
    switch (level.toLowerCase()) {
      case 'crítico':
      case 'critico':
        return Colors.red.shade800;
      case 'alto':
        return Colors.deepOrange;
      case 'medio':
        return Colors.amber.shade800;
      default:
        return Colors.green.shade700;
    }
  }

  String levelDescription(String level) {
    switch (level.toLowerCase()) {
      case 'crítico':
      case 'critico':
        return 'Atención inmediata';
      case 'alto':
        return 'Refuerza las medidas de prevención';
      case 'medio':
        return 'Mantente informado y observa síntomas';
      default:
        return 'Continúa con las medidas de cuidado';
    }
  }

  String recommendation(String level) {
    switch (level.toLowerCase()) {
      case 'crítico':
      case 'critico':
        return 'Si presentas dificultad respiratoria, deshidratación o empeoramiento, acude a urgencias.';
      case 'alto':
        return 'Evita criaderos de mosquitos, usa repelente y consulta si presentas síntomas.';
      case 'medio':
        return 'Mantén hidratación, higiene de manos y atención a cambios en tu salud.';
      default:
        return 'Sigue las recomendaciones de salud y consulta fuentes oficiales.';
    }
  }

  bool matches(Alerta alert) {
    final levelOk =
        levelFilter == 'todas' || alert.nivel.toLowerCase() == levelFilter;
    final text = '${alert.mensaje} ${alert.municipio}'.toLowerCase();
    final diseaseOk = diseaseFilter == 'todas' || text.contains(diseaseFilter);
    return levelOk && diseaseOk;
  }

  @override
  Widget build(BuildContext context) => RefreshIndicator(
        onRefresh: load,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(16),
          children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              color: online
                  ? Colors.green.withValues(alpha: .1)
                  : Colors.orange.withValues(alpha: .15),
              child: Row(
                children: [
                  Icon(online ? Icons.wifi : Icons.wifi_off,
                      size: 18, color: online ? Colors.green : Colors.orange),
                  const SizedBox(width: 8),
                  Text(online
                      ? 'Conectado · alertas actualizadas'
                      : 'Sin conexión · mostrando datos guardados'),
                ],
              ),
            ),
            Card(
              color: Theme.of(context).colorScheme.primaryContainer,
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Row(
                  children: [
                    Icon(Icons.health_and_safety,
                        color: Theme.of(context).colorScheme.primary),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        alerts.isEmpty
                            ? 'Vigilancia epidemiológica de Jalisco'
                            : '${alerts.length} alerta${alerts.length == 1 ? '' : 's'} activa${alerts.length == 1 ? '' : 's'}',
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                    ),
                  ],
                ),
              ),
            ),
            if (error != null)
              Text(error!, style: const TextStyle(color: Colors.orange)),
            if (loading) const LinearProgressIndicator(),
            Row(
              children: [
                Expanded(
                  child: DropdownButtonFormField<String>(
                    initialValue: levelFilter,
                    decoration: const InputDecoration(labelText: 'Nivel'),
                    items: const [
                      DropdownMenuItem(value: 'todas', child: Text('Todos')),
                      DropdownMenuItem(value: 'bajo', child: Text('Bajo')),
                      DropdownMenuItem(value: 'medio', child: Text('Medio')),
                      DropdownMenuItem(value: 'alto', child: Text('Alto')),
                      DropdownMenuItem(
                          value: 'crítico', child: Text('Crítico')),
                    ],
                    onChanged: (value) =>
                        setState(() => levelFilter = value ?? 'todas'),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: DropdownButtonFormField<String>(
                    initialValue: diseaseFilter,
                    decoration: const InputDecoration(labelText: 'Tema'),
                    items: const [
                      DropdownMenuItem(value: 'todas', child: Text('Todos')),
                      DropdownMenuItem(value: 'dengue', child: Text('Dengue')),
                      DropdownMenuItem(
                          value: 'influenza', child: Text('Influenza')),
                      DropdownMenuItem(value: 'covid', child: Text('COVID-19')),
                    ],
                    onChanged: (value) =>
                        setState(() => diseaseFilter = value ?? 'todas'),
                  ),
                ),
              ],
            ),
            if (!loading && alerts.isEmpty)
              const Padding(
                padding: EdgeInsets.only(top: 80),
                child: Center(child: Text('No hay alertas activas.')),
              ),
            ...alerts.where(matches).map(
                  (alert) => Card(
                    clipBehavior: Clip.antiAlias,
                    child: ExpansionTile(
                      leading: CircleAvatar(
                        backgroundColor: levelColor(alert.nivel),
                        child: const Icon(Icons.warning_amber,
                            color: Colors.white),
                      ),
                      title: Text(alert.municipio),
                      subtitle: Text(
                        '${alert.nivel.toUpperCase()} · ${levelDescription(alert.nivel)}',
                      ),
                      childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                      children: [
                        Align(
                          alignment: Alignment.centerLeft,
                          child: Text(alert.mensaje,
                              style: Theme.of(context).textTheme.bodyLarge),
                        ),
                        const SizedBox(height: 12),
                        Container(
                          width: double.infinity,
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: Theme.of(context)
                                .colorScheme
                                .surfaceContainerHighest,
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Text(
                            '¿Qué puedes hacer?\n${recommendation(alert.nivel)}',
                          ),
                        ),
                        const SizedBox(height: 8),
                        Align(
                          alignment: Alignment.centerLeft,
                          child: Text(
                            'Actualizada: ${alert.timestamp.toLocal()}',
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
          ],
        ),
      );
}
