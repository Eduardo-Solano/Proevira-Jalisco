import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:uuid/uuid.dart';

import '../api/api_client.dart';
import '../local_db/database_helper.dart';
import '../services/reminder_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

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
  TimeOfDay reminderTime = const TimeOfDay(hour: 19, minute: 0);

  @override
  void initState() {
    super.initState();
    _restoreReminderSettings();
  }

  Future<void> _restoreReminderSettings() async {
    final preferences = await SharedPreferences.getInstance();
    final hour = preferences.getInt('reminder_hour');
    final minute = preferences.getInt('reminder_minute');
    if (mounted) {
      setState(() {
        remindersEnabled = preferences.getBool('reminders_enabled') ?? false;
        if (hour != null && minute != null) {
          reminderTime = TimeOfDay(hour: hour, minute: minute);
        }
      });
    }
  }

  Future<void> configureReminder() async {
    final selected = await showTimePicker(
      context: context,
      initialTime: reminderTime,
    );
    if (selected == null) return;
    await ReminderService.instance.scheduleDailyAt(selected);
    final preferences = await SharedPreferences.getInstance();
    await preferences.setBool('reminders_enabled', true);
    await preferences.setInt('reminder_hour', selected.hour);
    await preferences.setInt('reminder_minute', selected.minute);
    if (mounted) {
      setState(() {
        reminderTime = selected;
        remindersEnabled = true;
      });
    }
  }

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
      _clearForm();
      if (mounted) {
        await showDialog<void>(
          context: context,
          builder: (context) => AlertDialog(
            title: const Text('Seguimiento registrado'),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  response['recomendacion'] ??
                      'Registro enviado correctamente.',
                ),
                const SizedBox(height: 12),
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: const Color(0xfffff1ef),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: const Color(0xfff3b4ad),
                    ),
                  ),
                  child: Text(
                    response['disclaimer_medico'] ??
                        'Esta aplicación es un asistente orientador y no sustituye el diagnóstico médico.',
                    style: const TextStyle(
                      color: Color(0xff6b7280),
                      fontSize: 12,
                      height: 1.35,
                      decoration: TextDecoration.none,
                    ),
                  ),
                ),
              ],
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
      _clearForm();
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

  void _clearForm() {
    temperature.clear();
    otrosSintomas.clear();
    fiebre = false;
    cefalea = false;
    dolorMuscular = false;
    dolorArticular = false;
    dolorRetroocular = false;
    tos = false;
    dificultadRespiratoria = false;
    diasConSintomas = 1;
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) => ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            color: const Color(0xfffff1ef),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(14),
              side: const BorderSide(color: Color(0xfff3b4ad)),
            ),
            child: const Padding(
              padding: EdgeInsets.all(12),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(Icons.info_outline, color: Color(0xffb42318), size: 20),
                  SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      'Esta aplicación no sustituye diagnóstico médico. Si tienes síntomas graves, busca atención profesional.',
                      style: TextStyle(
                        color: Color(0xffb42318),
                        fontSize: 12,
                        height: 1.35,
                        decoration: TextDecoration.none,
                      ),
                    ),
                  ),
                ],
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
                  await configureReminder();
                } else {
                  await ReminderService.instance.cancel();
                  final preferences =
                      await SharedPreferences.getInstance();
                  await preferences.setBool('reminders_enabled', false);
                  if (mounted) setState(() => remindersEnabled = false);
                }
              },
            ),
          ),
          if (remindersEnabled)
            Card(
              child: ListTile(
                leading: const Icon(Icons.schedule),
                title: const Text('Hora del recordatorio'),
                subtitle: Text(reminderTime.format(context)),
                trailing: const Icon(Icons.edit_outlined),
                onTap: configureReminder,
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
            spellCheckConfiguration: const SpellCheckConfiguration.disabled(),
            decoration: const InputDecoration(
                labelText: 'Temperatura (°C)', border: OutlineInputBorder()),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: otrosSintomas,
            maxLines: 3,
            spellCheckConfiguration: const SpellCheckConfiguration.disabled(),
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
