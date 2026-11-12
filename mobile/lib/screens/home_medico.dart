import 'package:flutter/material.dart';

import '../api/api_client.dart';
import '../api/ws_client.dart';
import '../local_db/database_helper.dart';
import '../models/prediccion.dart';
import 'alertas_screen.dart';
import 'mapa_clues.dart';

class HomeMedico extends StatefulWidget {
  const HomeMedico({
    required this.api,
    required this.database,
    required this.socket,
    required this.onLogout,
    super.key,
  });

  final ApiClient api;
  final DatabaseHelper database;
  final AlertsSocket socket;
  final Future<void> Function() onLogout;

  @override
  State<HomeMedico> createState() => _HomeMedicoState();
}

class _HomeMedicoState extends State<HomeMedico> {
  int index = 0;
  final municipio = TextEditingController(text: '14039');
  Prediccion? prediction;
  String? error;

  @override
  void dispose() {
    municipio.dispose();
    super.dispose();
  }

  Future<void> consult() async {
    setState(() => error = null);
    final now = DateTime.now();
    final week =
        '${now.year}-W${((now.difference(DateTime(now.year, 1, 1)).inDays) ~/ 7 + 1).toString().padLeft(2, '0')}';
    try {
      final result = await widget.api.getPrediction(
        municipio: municipio.text.trim(),
        semana: week,
      );
      if (mounted) setState(() => prediction = result);
    } catch (exception) {
      if (mounted) setState(() => error = exception.toString());
    }
  }

  Widget dashboard() => ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text('Consulta de riesgo municipal',
              style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 12),
          TextField(
            controller: municipio,
            keyboardType: TextInputType.number,
            decoration: const InputDecoration(
              labelText: 'ID del municipio',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          FilledButton.icon(
            onPressed: consult,
            icon: const Icon(Icons.analytics_outlined),
            label: const Text('Consultar predicción'),
          ),
          if (error != null) ...[
            const SizedBox(height: 12),
            Text(error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error)),
          ],
          if (prediction != null) ...[
            const SizedBox(height: 20),
            Card(
              child: ListTile(
                title: Text('Riesgo ${prediction!.nivelRiesgo.toUpperCase()}'),
                subtitle: Text(
                  '${prediction!.municipio} · ${prediction!.enfermedad}\n'
                  'Casos esperados: ${prediction!.casosEsperados.toStringAsFixed(1)}',
                ),
                isThreeLine: true,
                leading: const Icon(Icons.insights),
              ),
            ),
          ],
        ],
      );

  @override
  Widget build(BuildContext context) {
    final pages = [
      dashboard(),
      AlertasScreen(
          api: widget.api, database: widget.database, socket: widget.socket),
      MapaClues(api: widget.api, database: widget.database),
    ];
    const titles = ['Panel médico', 'Alertas', 'CLUES'];
    return Scaffold(
      appBar: AppBar(
        title: Text(titles[index]),
        actions: [
          IconButton(onPressed: widget.onLogout, icon: const Icon(Icons.logout))
        ],
      ),
      body: IndexedStack(index: index, children: pages),
      bottomNavigationBar: NavigationBar(
        selectedIndex: index,
        onDestinationSelected: (value) => setState(() => index = value),
        destinations: const [
          NavigationDestination(
              icon: Icon(Icons.dashboard_outlined), label: 'Panel'),
          NavigationDestination(
              icon: Icon(Icons.warning_amber), label: 'Alertas'),
          NavigationDestination(icon: Icon(Icons.map_outlined), label: 'CLUES'),
        ],
      ),
    );
  }
}
