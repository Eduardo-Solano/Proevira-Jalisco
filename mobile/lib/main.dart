import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';

import 'api/api_client.dart';
import 'api/ws_client.dart';
import 'auth/auth_service.dart';
import 'local_db/database_helper.dart';
import 'local_db/sync_service.dart';
import 'services/reminder_service.dart';
import 'screens/home_paciente.dart';
import 'screens/login_screen.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() => runApp(const ViralesApp());

class ViralesApp extends StatefulWidget {
  const ViralesApp({super.key});

  @override
  State<ViralesApp> createState() => _ViralesAppState();
}

class _ViralesAppState extends State<ViralesApp> with WidgetsBindingObserver {
  final api = ApiClient();
  final database = DatabaseHelper.instance;
  late final AuthService auth;
  late final SyncService sync;
  late final AlertsSocket socket;
  AuthSession? session;
  bool loading = true;
  ThemeMode themeMode = ThemeMode.light;
  bool locationOutsideCoverage = false;
  bool locationChecked = false;
  bool locationValid = false;
  bool _coverageNoticeShown = false;
  bool manualMunicipioSelected = false;
  String? detectedMunicipioId;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
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
      manualMunicipioSelected = await auth.hasManualMunicipioSelection();
    }
    if (restored != null) {
      await sync.start();
      socket.connect(restored.token);
    }
    if (mounted) {
      setState(() {
        session = restored;
        loading = false;
      });
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _initializeStartupServices();
      });
    }
  }

  Future<void> _initializeStartupServices() async {
    await ReminderService.instance.initialize();
    await _checkInitialLocation();
    _showCoverageNoticeIfNeeded();
  }

  Future<void> _checkInitialLocation() async {
    try {
      if (!await Geolocator.isLocationServiceEnabled()) return;

      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.denied ||
          permission == LocationPermission.deniedForever) {
        return;
      }

      final position = await Geolocator.getCurrentPosition().timeout(
        const Duration(seconds: 10),
      );
      if (mounted) {
        final inRegion = _isInRegionCentro(
          position.latitude,
          position.longitude,
        );
        setState(() {
          locationValid = true;
          locationOutsideCoverage = !inRegion && !manualMunicipioSelected;
          detectedMunicipioId = inRegion
              ? _nearestMunicipio(position.latitude, position.longitude)
              : null;
          locationChecked = true;
        });
      }
    } catch (_) {
      // Location is optional; the profile selector remains available.
    } finally {
      if (mounted && !locationChecked) {
        setState(() => locationChecked = true);
      }
    }
  }

  bool _isInRegionCentro(double latitude, double longitude) {
    return latitude >= 20.25 &&
        latitude <= 21.15 &&
        longitude >= -103.80 &&
        longitude <= -102.90;
  }

  String _nearestMunicipio(double latitude, double longitude) {
    const municipalities = <String, List<double>>{
      '14039': [20.676470, -103.347811],
      '14120': [20.716405, -103.416947],
      '14098': [20.610214, -103.320670],
      '14101': [20.630600, -103.251448],
      '14097': [20.521658, -103.432591],
      '14070': [20.542290, -103.282728],
      '14124': [20.622212, -103.068761],
      '14044': [20.385805, -103.191998],
      '14045': [20.863757, -103.210450],
      '14051': [20.507934, -103.167543],
      '14029': [20.930300, -103.028588],
      '14071': [21.046300, -103.427390],
    };
    var closest = municipalities.keys.first;
    var distance = double.infinity;
    for (final entry in municipalities.entries) {
      final latDistance = latitude - entry.value[0];
      final lonDistance = longitude - entry.value[1];
      final squaredDistance =
          latDistance * latDistance + lonDistance * lonDistance;
      if (squaredDistance < distance) {
        distance = squaredDistance;
        closest = entry.key;
      }
    }
    return closest;
  }

  void _showCoverageNoticeIfNeeded() {
    if (!locationChecked ||
        !locationOutsideCoverage ||
        _coverageNoticeShown ||
        !mounted) {
      return;
    }
    _coverageNoticeShown = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      showDialog<void>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('Ubicación fuera de cobertura'),
          content: const Text(
            'Por el momento, las funciones basadas en tu ubicación actual '
            'están fuera del alcance de la Región Centro de Jalisco. '
            'En el apartado Mi perfil puedes seleccionar manualmente un '
            'municipio para consultar sus alertas y unidades médicas.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Entendido'),
            ),
          ],
        ),
      );
    });
  }

  Future<void> _login(String email, String password) async {
    final current = await auth.login(email, password);
    await sync.start();
    socket.connect(current.token);
    if (mounted) setState(() => session = current);
  }

  Future<void> _register(
      String email, String password, String? municipioId) async {
    final current = await auth.registerPaciente(
      email: email,
      password: password,
      municipioId: municipioId,
    );
    manualMunicipioSelected = municipioId != null && municipioId.isNotEmpty;
    await sync.start();
    socket.connect(current.token);
    if (mounted) {
      setState(() {
        session = current;
        if (manualMunicipioSelected) {
          locationOutsideCoverage = false;
          detectedMunicipioId = null;
        }
      });
    }
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
    if (mounted) {
      setState(() => themeMode = enabled ? ThemeMode.dark : ThemeMode.light);
    }
  }

  void _setMunicipio(String? municipioId) {
    if (mounted) {
      setState(() {
        session = auth.session;
        manualMunicipioSelected = municipioId != null;
        if (municipioId != null) {
          locationOutsideCoverage = false;
          detectedMunicipioId = null;
        }
      });
    }
  }

  String? get activeMunicipioId {
    if (manualMunicipioSelected) return session?.municipioId;
    if (!locationValid || locationOutsideCoverage) return null;
    return detectedMunicipioId ?? session?.municipioId;
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    socket.dispose();
    sync.dispose();
    api.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && session != null) {
      socket.connect(session!.token);
    }
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'VIRALES App',
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
                ? LoginScreen(onLogin: _login, onRegister: _register)
                : HomePaciente(
                    api: api,
                    database: database,
                    socket: socket,
                    onLogout: _logout,
                    municipioId: activeMunicipioId,
                    auth: auth,
                    onMunicipioChanged: _setMunicipio,
                    locationOutsideCoverage: locationOutsideCoverage,
                    darkMode: themeMode == ThemeMode.dark,
                    onDarkModeChanged: _setDarkMode,
                    sync: sync,
                  ),
      );
}
