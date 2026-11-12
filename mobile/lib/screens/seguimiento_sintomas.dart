import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:uuid/uuid.dart';

import '../api/api_client.dart';
import '../local_db/database_helper.dart';
import '../services/reminder_service.dart';

class SeguimientoSintomas extends StatefulWidget {
  const SeguimientoSintomas(
      {required this.api, required this.database, super.key});

  final ApiClient api;
  final DatabaseHelper database;

  @override
  State<SeguimientoSintomas> createState() => _SeguimientoSintomasState();
}

class _SeguimientoSintomasState extends State<SeguimientoSintomas> {
  final uuid = const Uuid();
  final temperature = TextEditingController();
  bool fiebre = false;
  bool cefalea = false;
  bool dolorMuscular = false;
  bool dolorArticular = false;
  bool dolorRetroocular = false;
  bool tos = false;
  bool dificultadRespiratoria = false;
  int diasConSintomas = 1;
  final otrosSintomas = TextEditingController();
  bool loading = false;
  bool remindersEnabled = false;

  @override
  void dispose() {
    temperature.dispose();
    otrosSintomas.dispose();
    super.dispose();
  }

  Future<void> save() async {
    setState(() => loading = true);
    final idLocal = uuid.v4();
    final payload = {
      'id_local': idLocal,
      'fiebre': fiebre,
      'cefalea': cefalea,
      'dolor_muscular': dolorMuscular,
      'dolor_articular': dolorArticular,
      'dolor_retroocular': dolorRetroocular,
      'tos': tos,
      'dificultad_respiratoria': dificultadRespiratoria,
      'otros_sintomas':
          otrosSintomas.text.trim().isEmpty ? null : otrosSintomas.text.trim(),
      'dias_con_sintomas': diasConSintomas,
      'temperatura': double.tryParse(temperature.text.replaceAll(',', '.')),
      'ts_registro': DateTime.now().toIso8601String(),
    };
    try {
      final response = await widget.api.postSymptoms(payload);
      await widget.database.saveSyncedSymptom(payload, response);
      if (mounted) {
        await showDialog<void>(
          context: context,
          builder: (context) => AlertDialog(
            title: const Text('Seguimiento registrado'),
            content: Text(
              '${response['recomendacion'] ?? 'Registro enviado correctamente.'}\n\n'
              '${response['disclaimer_medico'] ?? 'Esta aplicación no sustituye el diagnóstico médico.'}',
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('Entendido'),
              ),
            ],
          ),
        );
      }
    } on ApiException {
      await widget.database.enqueueSymptoms(idLocal, jsonEncode(payload));
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
              content: Text(
                  'Guardado en el dispositivo. Se enviará al recuperar conexión.')),
        );
      }
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  @override
  Widget build(BuildContext context) => ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            color: Theme.of(context).colorScheme.errorContainer,
            child: const Padding(
              padding: EdgeInsets.all(12),
              child: Text(
                'Esta aplicación no sustituye diagnóstico médico. Si tienes síntomas graves, busca atención profesional.',
              ),
            ),
          ),
          const SizedBox(height: 12),
          Card(
            child: SwitchListTile(
              title: const Text('Recordatorio diario'),
              subtitle: const Text('Recibir un aviso para registrar síntomas'),
              value: remindersEnabled,
              onChanged: (value) async {
                if (value) {
                  await ReminderService.instance.scheduleDaily();
                } else {
                  await ReminderService.instance.cancel();
                }
                if (mounted) setState(() => remindersEnabled = value);
              },
            ),
          ),
          SwitchListTile(
              title: const Text('Fiebre'),
              value: fiebre,
              onChanged: (v) => setState(() => fiebre = v)),
          SwitchListTile(
              title: const Text('Dolor de cabeza'),
              value: cefalea,
              onChanged: (v) => setState(() => cefalea = v)),
          SwitchListTile(
              title: const Text('Dolor muscular'),
              value: dolorMuscular,
              onChanged: (v) => setState(() => dolorMuscular = v)),
          SwitchListTile(
              title: const Text('Dolor articular'),
              value: dolorArticular,
              onChanged: (v) => setState(() => dolorArticular = v)),
          SwitchListTile(
              title: const Text('Dolor retroocular'),
              value: dolorRetroocular,
              onChanged: (v) => setState(() => dolorRetroocular = v)),
          SwitchListTile(
              title: const Text('Tos'),
              value: tos,
              onChanged: (v) => setState(() => tos = v)),
          SwitchListTile(
              title: const Text('Dificultad respiratoria'),
              value: dificultadRespiratoria,
              onChanged: (v) => setState(() => dificultadRespiratoria = v)),
          DropdownButtonFormField<int>(
            initialValue: diasConSintomas,
            decoration: const InputDecoration(
              labelText: 'Días con síntomas',
              border: OutlineInputBorder(),
            ),
            items: List.generate(
              14,
              (index) => DropdownMenuItem(
                value: index + 1,
                child: Text('${index + 1}'),
              ),
            ),
            onChanged: (value) {
              if (value != null) setState(() => diasConSintomas = value);
            },
          ),
          const SizedBox(height: 12),
          TextField(
            controller: temperature,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(
                labelText: 'Temperatura (°C)', border: OutlineInputBorder()),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: otrosSintomas,
            maxLines: 3,
            decoration: const InputDecoration(
              labelText: 'Otros síntomas (opcional)',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 16),
          FilledButton.icon(
            onPressed: loading ? null : save,
            icon: const Icon(Icons.save_outlined),
            label: Text(loading ? 'Guardando...' : 'Guardar seguimiento'),
          ),
        ],
      );
}
