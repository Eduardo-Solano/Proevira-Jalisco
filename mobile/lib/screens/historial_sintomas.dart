import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';

import '../api/api_client.dart';
import '../local_db/database_helper.dart';
import '../models/registro_sintomas.dart';

class HistorialSintomas extends StatefulWidget {
  const HistorialSintomas({
    required this.api,
    required this.database,
    super.key,
  });

  final ApiClient api;
  final DatabaseHelper database;

  @override
  State<HistorialSintomas> createState() => _HistorialSintomasState();
}

class _HistorialSintomasState extends State<HistorialSintomas> {
  List<RegistroSintomas> records = [];
  bool loading = true;
  String? message;

  @override
  void initState() {
    super.initState();
    load();
  }

  Future<void> load() async {
    try {
      final remote = (await widget.api.getMySymptoms())
          .map(RegistroSintomas.fromServer)
          .toList();
      final local = await widget.database.getLocalSymptoms();
      final byId = <String, RegistroSintomas>{
        for (final record in [...local, ...remote]) record.idLocal: record,
      };
      if (mounted) {
        setState(() {
          records = byId.values.toList();
          message = records.isEmpty ? 'Aún no tienes registros.' : null;
        });
      }
    } catch (_) {
      final local = await widget.database.getLocalSymptoms();
      if (mounted) {
        setState(() {
          records = local;
          message = local.isEmpty
              ? 'No se pudo cargar el historial. Intenta de nuevo con conexión.'
              : 'Sin conexión: mostrando registros guardados en este dispositivo.';
        });
      }
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  @override
  Widget build(BuildContext context) => RefreshIndicator(
        onRefresh: load,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(16),
          children: [
            Text('Mi historial',
                style: Theme.of(context).textTheme.headlineSmall),
            const SizedBox(height: 4),
            const Text(
              'Aquí puedes consultar los reportes que has enviado y los que esperan sincronización.',
            ),
            if (records.any((record) => record.temperatura != null)) ...[
              const SizedBox(height: 16),
              Card(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(12, 16, 20, 12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Evolución de temperatura',
                          style: Theme.of(context).textTheme.titleMedium),
                      const SizedBox(height: 16),
                      SizedBox(
                        height: 180,
                        child: LineChart(
                          LineChartData(
                            minY: 35,
                            maxY: 41,
                            gridData: const FlGridData(show: true),
                            titlesData: const FlTitlesData(
                              rightTitles: AxisTitles(
                                  sideTitles: SideTitles(showTitles: false)),
                              topTitles: AxisTitles(
                                  sideTitles: SideTitles(showTitles: false)),
                            ),
                            lineBarsData: [
                              LineChartBarData(
                                isCurved: true,
                                color: Theme.of(context).colorScheme.primary,
                                spots: [
                                  for (var i = 0; i < records.length; i++)
                                    if (records[i].temperatura != null)
                                      FlSpot(i.toDouble(),
                                          records[i].temperatura!),
                                ],
                              ),
                            ],
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
            const SizedBox(height: 16),
            if (loading) const LinearProgressIndicator(),
            if (message != null)
              Padding(
                padding: const EdgeInsets.only(top: 32),
                child: Center(child: Text(message!)),
              ),
            ...records.map(
              (record) => Card(
                child: ExpansionTile(
                  leading: CircleAvatar(
                    backgroundColor: record.sincronizado
                        ? Theme.of(context).colorScheme.primary
                        : Theme.of(context).colorScheme.secondary,
                    child: Icon(
                      record.sincronizado ? Icons.cloud_done : Icons.cloud_off,
                      color: Colors.white,
                    ),
                  ),
                  title: Text(
                    '${record.fecha.toLocal().day.toString().padLeft(2, '0')}/'
                    '${record.fecha.toLocal().month.toString().padLeft(2, '0')}/'
                    '${record.fecha.toLocal().year}',
                  ),
                  subtitle: Text(
                    '${record.dias} ${record.dias == 1 ? 'día' : 'días'} · '
                    '${record.sincronizado ? 'Sincronizado' : 'Pendiente de envío'}',
                  ),
                  childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                  children: [
                    Align(
                      alignment: Alignment.centerLeft,
                      child: Text(
                        record.sintomas.isEmpty
                            ? 'No marcaste síntomas.'
                            : record.sintomas.join(' · '),
                      ),
                    ),
                    if (record.sospecha != null) ...[
                      const SizedBox(height: 8),
                      Align(
                        alignment: Alignment.centerLeft,
                        child: Text('Orientación: ${record.sospecha}'),
                      ),
                    ],
                    if (record.temperatura != null) ...[
                      const SizedBox(height: 8),
                      Align(
                        alignment: Alignment.centerLeft,
                        child: Text(
                          'Temperatura: ${record.temperatura!.toStringAsFixed(1)} °C',
                        ),
                      ),
                    ],
                    if (record.recomendacion != null) ...[
                      const SizedBox(height: 8),
                      Align(
                        alignment: Alignment.centerLeft,
                        child: Text(record.recomendacion!),
                      ),
                    ],
                  ],
                ),
              ),
            ),
          ],
        ),
      );
}
