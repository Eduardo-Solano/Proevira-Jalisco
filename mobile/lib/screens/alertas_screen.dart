import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

import '../api/api_client.dart';
import '../api/ws_client.dart';
import '../local_db/database_helper.dart';
import '../models/alerta.dart';
import '../models/incidencia.dart';

class AlertasScreen extends StatefulWidget {
  const AlertasScreen({
    required this.api,
    required this.database,
    required this.socket,
    this.municipioId,
    super.key,
  });

  final ApiClient api;
  final DatabaseHelper database;
  final AlertsSocket socket;
  final String? municipioId;

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
  List<Incidencia> incidence = [];
  String incidenceDisease = 'dengue';
  int incidenceWeeks = 8;
  bool incidenceLoading = true;
  String? incidenceError;

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
      final alert = Alerta.fromJson(json);
      if (mounted && belongsToPatient(alert)) {
        setState(() => alerts = [alert, ...alerts]);
      }
    });
    load();
    loadIncidence();
  }

  @override
  void dispose() {
    connectivity?.cancel();
    super.dispose();
  }

  Future<void> load() async {
    try {
      final remote =
          await widget.api.getAlerts(municipio: widget.municipioId);
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

  Future<void> loadIncidence() async {
    if (mounted) setState(() => incidenceLoading = true);
    try {
      final points = await widget.api.getMobileIncidence(
        enfermedad: incidenceDisease,
        semanas: incidenceWeeks,
      );
      if (mounted) {
        setState(() {
          incidence = points;
          incidenceError = null;
        });
      }
    } on ApiException catch (exception) {
      if (mounted) {
        setState(() {
          incidence = [];
          incidenceError = exception.message;
        });
      }
    } finally {
      if (mounted) setState(() => incidenceLoading = false);
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

  bool belongsToPatient(Alerta alert) {
    final patientMunicipio = widget.municipioId;
    if (patientMunicipio == null || patientMunicipio.isEmpty) return true;
    final alertMunicipio = alert.municipio.trim().toLowerCase();
    if (alertMunicipio.isEmpty || alertMunicipio == 'jalisco') return true;
    final normalizedPatient = patientMunicipio.replaceFirst(
      RegExp(r'^14(?=\d{3}$)'),
      '',
    );
    return alertMunicipio == patientMunicipio.toLowerCase() ||
        alertMunicipio == normalizedPatient;
  }

  Color incidenceColor(Incidencia point, int maxCases) {
    final ratio = maxCases == 0 ? 0.0 : point.casos / maxCases;
    if (ratio >= .66) return Colors.red.shade700;
    if (ratio >= .33) return Colors.orange.shade700;
    return Colors.amber.shade700;
  }

  Widget incidenceMap(BuildContext context) {
    final maxCases = incidence.fold<int>(
      0,
      (max, point) => point.casos > max ? point.casos : max,
    );
    return Card(
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 16, 8, 4),
            child: Column(
              children: [
                Row(
                  children: [
                    Icon(Icons.layers,
                        color: Theme.of(context).colorScheme.primary),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text('Incidencia por municipio',
                          style: Theme.of(context).textTheme.titleMedium),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    Expanded(
                      child: DropdownButtonFormField<String>(
                        initialValue: incidenceDisease,
                        isDense: true,
                        isExpanded: true,
                        decoration:
                            const InputDecoration(labelText: 'Enfermedad'),
                        items: const [
                          DropdownMenuItem(
                              value: 'dengue', child: Text('Dengue')),
                          DropdownMenuItem(
                              value: 'influenza', child: Text('Influenza')),
                          DropdownMenuItem(
                              value: 'covid', child: Text('COVID')),
                        ],
                        onChanged: (value) {
                          if (value == null) return;
                          setState(() => incidenceDisease = value);
                          loadIncidence();
                        },
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: DropdownButtonFormField<int>(
                        initialValue: incidenceWeeks,
                        isDense: true,
                        isExpanded: true,
                        decoration:
                            const InputDecoration(labelText: 'Periodo'),
                        items: const [
                          DropdownMenuItem(
                              value: 4, child: Text('Último mes')),
                          DropdownMenuItem(
                              value: 8, child: Text('Últimos 2 meses')),
                        ],
                        onChanged: (value) {
                          if (value == null) return;
                          setState(() => incidenceWeeks = value);
                          loadIncidence();
                        },
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 16),
            child: Text('Casos acumulados en el periodo seleccionado'),
          ),
          const SizedBox(height: 8),
          SizedBox(
            height: 260,
            child: incidenceLoading
                ? const Center(child: CircularProgressIndicator())
                : incidence.isEmpty
                    ? Center(
                        child: Padding(
                          padding: const EdgeInsets.all(24),
                          child: Text(
                            incidenceError ??
                                'No hay datos históricos disponibles.',
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              color: incidenceError == null
                                  ? Colors.black54
                                  : Colors.red.shade700,
                            ),
                          ),
                        ),
                      )
                    : FlutterMap(
                        options: const MapOptions(
                          initialCenter: LatLng(20.65, -103.35),
                          initialZoom: 9,
                        ),
                        children: [
                          TileLayer(
                            urlTemplate:
                                'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                            userAgentPackageName: 'com.proevira.jalisco',
                          ),
                          MarkerLayer(
                            markers: incidence
                                .map(
                                  (point) => Marker(
                                    point: LatLng(point.lat, point.lon),
                                    width: 44,
                                    height: 44,
                                    child: Tooltip(
                                      message:
                                          '${point.nombre}\n${point.casos} casos',
                                      child: Container(
                                        decoration: BoxDecoration(
                                          color: incidenceColor(
                                                  point, maxCases)
                                              .withValues(alpha: .85),
                                          shape: BoxShape.circle,
                                          border: Border.all(
                                              color: Colors.white, width: 2),
                                        ),
                                        alignment: Alignment.center,
                                        child: Text(
                                          '${point.casos}',
                                          style: const TextStyle(
                                              color: Colors.white,
                                              fontWeight: FontWeight.bold,
                                              fontSize: 11),
                                        ),
                                      ),
                                    ),
                                  ),
                                )
                                .toList(),
                          ),
                        ],
                      ),
          ),
          const Padding(
            padding: EdgeInsets.fromLTRB(16, 8, 16, 16),
            child: Row(
              children: [
                _MapLegend(color: Colors.amber, label: 'Menor'),
                SizedBox(width: 12),
                _MapLegend(color: Colors.orange, label: 'Media'),
                SizedBox(width: 12),
                _MapLegend(color: Colors.red, label: 'Mayor'),
              ],
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) => RefreshIndicator(
        onRefresh: load,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(16),
          children: [
            Text(
              'Tus alertas',
              style: Theme.of(context).textTheme.headlineSmall,
            ),
            const SizedBox(height: 4),
            Text(
              widget.municipioId == null
                  ? 'Avisos activos para Jalisco'
                  : 'Avisos activos para tu municipio',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            const SizedBox(height: 12),
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
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.primaryContainer,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(
                  color: Theme.of(context)
                      .colorScheme
                      .primary
                      .withValues(alpha: .25),
                ),
              ),
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
            if (error != null)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(
                  error!,
                  style: TextStyle(
                    color: Colors.red.shade700,
                    fontSize: 12,
                    decoration: TextDecoration.none,
                  ),
                ),
              ),
            if (loading) ...[
              const SizedBox(height: 8),
              const LinearProgressIndicator(),
            ],
            const SizedBox(height: 12),
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
            const SizedBox(height: 16),
            if (!loading && alerts.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 24),
                child: Center(child: Text('No hay alertas activas.')),
              ),
            ...alerts.where((alert) => belongsToPatient(alert) && matches(alert)).map(
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
            const SizedBox(height: 24),
            Text(
              'Mapa de calor de la región',
              style: Theme.of(context).textTheme.headlineSmall,
            ),
            const SizedBox(height: 4),
            const Text(
              'Consulta la incidencia histórica agregada por municipio en Jalisco.',
            ),
            const SizedBox(height: 12),
            incidenceMap(context),
          ],
        ),
      );
}

class _MapLegend extends StatelessWidget {
  const _MapLegend({required this.color, required this.label});

  final Color color;
  final String label;

  @override
  Widget build(BuildContext context) => Expanded(
        child: Row(
          children: [
            CircleAvatar(radius: 6, backgroundColor: color),
            const SizedBox(width: 4),
            Flexible(child: Text(label, overflow: TextOverflow.ellipsis)),
          ],
        ),
      );
}
