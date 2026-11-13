import 'package:flutter/material.dart';

import 'api/api_client.dart';
import 'api/ws_client.dart';
import 'auth/auth_service.dart';
import 'local_db/database_helper.dart';
import 'local_db/sync_service.dart';
import 'screens/home_paciente.dart';
import 'screens/login_screen.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() => runApp(const ProeviraApp());

class ProeviraApp extends StatefulWidget {
  const ProeviraApp({super.key});

  @override
  State<ProeviraApp> createState() => _ProeviraAppState();
}

class _ProeviraAppState extends State<ProeviraApp> {
  final api = ApiClient();
  final database = DatabaseHelper.instance;
  late final AuthService auth;
  late final SyncService sync;
  late final AlertsSocket socket;
  AuthSession? session;
  bool loading = true;
  ThemeMode themeMode = ThemeMode.light;

  @override
  void initState() {
    super.initState();
    auth = AuthService(api);
    sync = SyncService(api, database);
    socket = AlertsSocket();
    _restoreTheme();
    _restore();
  }

  Future<void> _restoreTheme() async {
    final preferences = await SharedPreferences.getInstance();
    if (mounted && preferences.getBool('dark_mode') == true) {
      setState(() => themeMode = ThemeMode.dark);
    }
  }

  Future<void> _restore() async {
    final restored = await auth.restore();
    if (restored != null) {
      await sync.start();
      socket.connect(restored.token);
    }
    if (mounted) {
      setState(() {
        session = restored;
        loading = false;
      });
    }
  }

  Future<void> _login(String email, String password) async {
    final current = await auth.login(email, password);
    await sync.start();
    socket.connect(current.token);
    if (mounted) setState(() => session = current);
  }

  Future<void> _logout() async {
    socket.disconnect();
    await sync.dispose();
    await auth.logout();
    if (mounted) setState(() => session = null);
  }

  Future<void> _setDarkMode(bool enabled) async {
    final preferences = await SharedPreferences.getInstance();
    await preferences.setBool('dark_mode', enabled);
    if (mounted) setState(() => themeMode = enabled ? ThemeMode.dark : ThemeMode.light);
  }

  void _setMunicipio(String? municipioId) {
    if (mounted) setState(() => session = auth.session);
  }

  @override
  void dispose() {
    socket.dispose();
    sync.dispose();
    api.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'Proevira Jalisco',
        debugShowCheckedModeBanner: false,
        themeMode: themeMode,
        theme: ThemeData(
          colorScheme: const ColorScheme.light(
            primary: Color(0xffed7d22),
            onPrimary: Colors.white,
            secondary: Color(0xff6b7280),
            onSecondary: Colors.white,
            surface: Colors.white,
            onSurface: Color(0xff1f2937),
            error: Color(0xffb42318),
          ),
          scaffoldBackgroundColor: Colors.white,
          appBarTheme: const AppBarTheme(
            backgroundColor: Colors.white,
            foregroundColor: Color(0xff1f2937),
            elevation: 0,
            centerTitle: false,
          ),
          cardTheme: CardThemeData(
            color: Colors.white,
            elevation: 1,
            margin: const EdgeInsets.symmetric(vertical: 6),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(16),
              side: const BorderSide(color: Color(0xffe5e7eb)),
            ),
          ),
          navigationBarTheme: const NavigationBarThemeData(
            backgroundColor: Colors.white,
            indicatorColor: Color(0xffffeadb),
            labelTextStyle: WidgetStatePropertyAll(
              TextStyle(fontWeight: FontWeight.w600),
            ),
          ),
          elevatedButtonTheme: ElevatedButtonThemeData(
            style: ElevatedButton.styleFrom(
              minimumSize: const Size.fromHeight(48),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
            ),
          ),
          inputDecorationTheme: const InputDecorationTheme(
            filled: true,
            fillColor: Color(0xfff3f4f6),
            errorStyle: TextStyle(
              color: Color(0xffb42318),
              fontSize: 12,
              decoration: TextDecoration.none,
            ),
            border: OutlineInputBorder(
              borderSide: BorderSide(color: Color(0xffd1d5db)),
            ),
          ),
          useMaterial3: true,
        ),
        darkTheme: ThemeData(
          brightness: Brightness.dark,
          colorScheme: ColorScheme.fromSeed(
            seedColor: const Color(0xffed7d22),
            brightness: Brightness.dark,
          ),
          useMaterial3: true,
        ),
        home: loading
            ? const Scaffold(body: Center(child: CircularProgressIndicator()))
            : session == null
                ? LoginScreen(onLogin: _login)
                : HomePaciente(
                    api: api,
                    database: database,
                    socket: socket,
                    onLogout: _logout,
                    municipioId: session?.municipioId,
                    auth: auth,
                    onMunicipioChanged: _setMunicipio,
                    darkMode: themeMode == ThemeMode.dark,
                    onDarkModeChanged: _setDarkMode,
                    sync: sync,
                  ),
      );
}
