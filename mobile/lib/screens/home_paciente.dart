import 'package:flutter/material.dart';

import '../api/api_client.dart';
import '../api/ws_client.dart';
import '../auth/auth_service.dart';
import '../local_db/sync_service.dart';
import '../local_db/database_helper.dart';
import 'alertas_screen.dart';
import 'mapa_clues.dart';
import 'seguimiento_sintomas.dart';
import 'informacion_screen.dart';
import 'historial_sintomas.dart';
import 'perfil_screen.dart';

class HomePaciente extends StatefulWidget {
  const HomePaciente({
    required this.api,
    required this.database,
    required this.socket,
    required this.onLogout,
    this.municipioId,
    required this.auth,
    required this.onMunicipioChanged,
    required this.darkMode,
    required this.onDarkModeChanged,
    required this.sync,
    super.key,
  });

  final ApiClient api;
  final DatabaseHelper database;
  final AlertsSocket socket;
  final Future<void> Function() onLogout;
  final String? municipioId;
  final AuthService auth;
  final ValueChanged<String?> onMunicipioChanged;
  final bool darkMode;
  final ValueChanged<bool> onDarkModeChanged;
  final SyncService sync;

  @override
  State<HomePaciente> createState() => _HomePacienteState();
}

class _HomePacienteState extends State<HomePaciente> {
  int index = 0;

  @override
  Widget build(BuildContext context) {
    final pages = [
      AlertasScreen(
          api: widget.api,
          database: widget.database,
          socket: widget.socket,
          municipioId: widget.municipioId),
      SeguimientoSintomas(api: widget.api, database: widget.database),
      MapaClues(api: widget.api, database: widget.database),
      const InformacionScreen(),
      HistorialSintomas(
        api: widget.api,
        database: widget.database,
        sync: widget.sync,
      ),
      PerfilScreen(
        api: widget.api,
        auth: widget.auth,
        municipioId: widget.municipioId,
        onMunicipioChanged: widget.onMunicipioChanged,
        darkMode: widget.darkMode,
        onDarkModeChanged: widget.onDarkModeChanged,
      ),
    ];
    const titles = [
      'Alertas activas',
      'Seguimiento de síntomas',
      'Unidades médicas',
      'Guía',
      'Historial',
      'Mi perfil',
    ];
    return Scaffold(
      appBar: AppBar(
        title: Text(titles[index]),
        actions: [
          IconButton(
            tooltip: 'Cerrar sesión',
            onPressed: widget.onLogout,
            icon: const Icon(Icons.logout),
          ),
        ],
      ),
      body: IndexedStack(index: index, children: pages),
      bottomNavigationBar: NavigationBar(
        selectedIndex: index,
        onDestinationSelected: (value) => setState(() => index = value),
        destinations: const [
          NavigationDestination(
              icon: Icon(Icons.warning_amber), label: 'Alertas'),
          NavigationDestination(
              icon: Icon(Icons.monitor_heart), label: 'Síntomas'),
          NavigationDestination(icon: Icon(Icons.map_outlined), label: 'CLUES'),
          NavigationDestination(icon: Icon(Icons.info_outline), label: 'Guía'),
          NavigationDestination(icon: Icon(Icons.history), label: 'Historial'),
          NavigationDestination(icon: Icon(Icons.person_outline), label: 'Perfil'),
        ],
      ),
    );
  }
}
