import 'package:flutter/material.dart';

import '../api/api_client.dart';
import '../auth/auth_service.dart';
import '../config.dart';

class PerfilScreen extends StatefulWidget {
  const PerfilScreen({
    required this.api,
    required this.auth,
    required this.municipioId,
    required this.onMunicipioChanged,
    required this.darkMode,
    required this.onDarkModeChanged,
    super.key,
  });

  final ApiClient api;
  final AuthService auth;
  final String? municipioId;
  final ValueChanged<String?> onMunicipioChanged;
  final bool darkMode;
  final ValueChanged<bool> onDarkModeChanged;

  @override
  State<PerfilScreen> createState() => _PerfilScreenState();
}

class _PerfilScreenState extends State<PerfilScreen> {
  late String? selectedMunicipio = AppConfig.municipiosCentro.containsKey(widget.municipioId)
      ? widget.municipioId
      : null;
  bool saving = false;

  @override
  void didUpdateWidget(covariant PerfilScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!saving && oldWidget.municipioId != widget.municipioId) {
      setState(() => selectedMunicipio =
          AppConfig.municipiosCentro.containsKey(widget.municipioId)
              ? widget.municipioId
              : null);
    }
  }

  Future<void> save() async {
    setState(() => saving = true);
    try {
      final session = await widget.auth.updateMunicipio(selectedMunicipio);
      widget.onMunicipioChanged(session.municipioId);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Perfil actualizado.')),
        );
      }
    } on ApiException catch (exception) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(exception.message)));
      }
    } finally {
      if (mounted) setState(() => saving = false);
    }
  }

  @override
  Widget build(BuildContext context) => ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text('Mi perfil', style: Theme.of(context).textTheme.headlineSmall),
          const SizedBox(height: 8),
          const Text(
            'Configura el municipio que se usará para mostrar tus alertas locales.',
          ),
          const SizedBox(height: 16),
          Card(
            child: Column(
              children: [
                ListTile(
                  leading: const Icon(Icons.person_outline),
                  title: Text(widget.auth.session?.email ?? 'Paciente'),
                  subtitle: const Text('Cuenta de paciente'),
                ),
                Padding(
                  padding: const EdgeInsets.all(16),
                  child: DropdownButtonFormField<String?>(
                    initialValue: selectedMunicipio,
                    isExpanded: true,
                    decoration: const InputDecoration(
                      labelText: 'Municipio para alertas',
                      prefixIcon: Icon(Icons.location_on_outlined),
                    ),
                    items: [
                      const DropdownMenuItem<String?>(
                        value: null,
                        child: Text('Todo Jalisco'),
                      ),
                      ...AppConfig.municipiosCentro.entries.map(
                        (entry) => DropdownMenuItem<String?>(
                          value: entry.key,
                          child: Text(entry.value),
                        ),
                      ),
                    ],
                    onChanged: (value) =>
                        setState(() => selectedMunicipio = value),
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                  child: FilledButton.icon(
                    onPressed: saving ? null : save,
                    icon: const Icon(Icons.save_outlined),
                    label: Text(saving ? 'Guardando...' : 'Guardar municipio'),
                  ),
                ),
              ],
            ),
          ),
          Card(
            child: SwitchListTile(
              title: const Text('Modo oscuro'),
              subtitle:
                  const Text('Reduce el brillo y mejora la lectura nocturna'),
              value: widget.darkMode,
              onChanged: widget.onDarkModeChanged,
            ),
          ),
          const Card(
            child: ListTile(
              leading: Icon(Icons.accessibility_new),
              title: Text('Contraste mejorado'),
              subtitle:
                  Text('La aplicación usa colores y textos de alto contraste.'),
            ),
          ),
        ],
      );
}
