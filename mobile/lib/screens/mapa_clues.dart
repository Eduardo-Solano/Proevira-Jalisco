import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:geolocator/geolocator.dart';
import 'package:http/http.dart' as http;
import 'package:latlong2/latlong.dart';
import 'dart:convert';

import '../api/api_client.dart';
import '../local_db/database_helper.dart';
import '../models/clue.dart';

class MapaClues extends StatefulWidget {
  const MapaClues({required this.api, required this.database, super.key});

  final ApiClient api;
  final DatabaseHelper database;

  @override
  State<MapaClues> createState() => _MapaCluesState();
}

class _MapaCluesState extends State<MapaClues> {
  static const locations = <String, LatLng>{
    'Guadalajara': LatLng(20.6736, -103.344),
    'Zapopan': LatLng(20.7214, -103.3918),
    'Tlaquepaque': LatLng(20.6404, -103.2933),
    'Tonalá': LatLng(20.624, -103.2346),
    'Tlajomulco': LatLng(20.4737, -103.445),
    'El Salto': LatLng(20.5195, -103.181),
    'Zapotlanejo': LatLng(20.622, -103.067),
    'Ixtlahuacán de los Membrillos': LatLng(20.349, -103.192),
    'Juanacatlán': LatLng(20.509, -103.17),
    'Acatlán de Juárez': LatLng(20.423, -103.59),
  };

  List<Clue> clues = [];
  LatLng center = const LatLng(20.67, -103.35);
  String? selectedLocation = 'Guadalajara';
  bool usingSimulatedLocation = true;
  String? message;
  bool loading = true;
  List<LatLng> routePoints = [];

  @override
  void initState() {
    super.initState();
    load();
  }

  Future<void> load() async {
    await loadAt(center, 'Guadalajara');
  }

  Future<void> loadAt(LatLng location, String label) async {
    if (mounted) {
      setState(() {
        loading = true;
        message = null;
        center = location;
        selectedLocation = locations.containsKey(label) ? label : null;
        routePoints = [];
      });
    }
    try {
      final remote =
          await widget.api.nearestClues(location.latitude, location.longitude);
      await widget.database.replaceClues(remote);
      clues = remote;
      message = 'Unidades cercanas a $label.';
    } catch (_) {
      final cached = await widget.database.getClues();
      clues = cached;
      message = cached.isEmpty
          ? 'No se pudieron cargar las unidades de Jalisco. Verifica que el backend esté activo.'
          : 'Sin conexión: mostrando unidades guardadas previamente.';
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> useDeviceLocation() async {
    try {
      if (!await Geolocator.isLocationServiceEnabled()) {
        throw Exception('GPS desactivado');
      }
      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.denied ||
          permission == LocationPermission.deniedForever) {
        throw Exception('Permiso de ubicación no disponible');
      }
      final position = await Geolocator.getCurrentPosition();
      final location = LatLng(position.latitude, position.longitude);
      if (location.latitude < 18 ||
          location.latitude > 24 ||
          location.longitude < -106 ||
          location.longitude > -100) {
        if (mounted) {
          setState(() {
            usingSimulatedLocation = true;
            message =
                'Tu ubicación está fuera de Jalisco. Selecciona un municipio para consultar unidades de la región.';
          });
        }
        return;
      }
      usingSimulatedLocation = false;
      await loadAt(location, 'tu ubicación');
    } catch (_) {
      if (mounted) {
        setState(() {
          message =
              'No se pudo usar la ubicación del dispositivo. Puedes elegir un municipio de Jalisco.';
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) => Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 12, 12, 4),
            child: Row(
              children: [
                Expanded(
                  child: DropdownButtonFormField<String>(
                    initialValue: selectedLocation,
                    decoration: const InputDecoration(
                      labelText: 'Zona de consulta',
                      prefixIcon: Icon(Icons.location_on_outlined),
                    ),
                    items: locations.keys
                        .map((name) => DropdownMenuItem(
                              value: name,
                              child: Text(name),
                            ))
                        .toList(),
                    onChanged: (value) {
                      if (value != null) {
                        usingSimulatedLocation = true;
                        loadAt(locations[value]!, value);
                      }
                    },
                  ),
                ),
                IconButton(
                  tooltip: 'Usar mi ubicación',
                  onPressed: useDeviceLocation,
                  icon: Icon(
                    Icons.my_location,
                    color: usingSimulatedLocation
                        ? Theme.of(context).colorScheme.primary
                        : Theme.of(context).colorScheme.secondary,
                  ),
                ),
              ],
            ),
          ),
          if (message != null)
            Padding(
              padding: const EdgeInsets.all(8),
              child: Text(message!, textAlign: TextAlign.center),
            ),
          Expanded(
            child: loading
                ? const Center(child: CircularProgressIndicator())
                : FlutterMap(
                    options: MapOptions(initialCenter: center, initialZoom: 12),
                    children: [
                      TileLayer(
                        urlTemplate:
                            'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                        userAgentPackageName: 'com.virales.app',
                      ),
                      MarkerLayer(
                        markers: [
                          Marker(
                            point: center,
                            width: 44,
                            height: 44,
                            child: Icon(
                              usingSimulatedLocation
                                  ? Icons.location_on
                                  : Icons.my_location,
                              color: Theme.of(context).colorScheme.primary,
                              size: 32,
                            ),
                          ),
                          ...clues.map(
                            (clue) => Marker(
                              point: LatLng(clue.lat, clue.lon),
                              width: 42,
                              height: 42,
                              child: Tooltip(
                                message: clue.nombre,
                                child: const Icon(Icons.local_hospital,
                                    color: Colors.red, size: 30),
                              ),
                            ),
                          ),
                        ],
                      ),
                      if (routePoints.length > 1)
                        PolylineLayer(
                          polylines: [
                            Polyline(
                              points: routePoints,
                              color: Theme.of(context).colorScheme.primary,
                              strokeWidth: 5,
                            ),
                          ],
                        ),
                    ],
                  ),
          ),
          SizedBox(
            height: 120,
            child: ListView.builder(
              itemCount: clues.length,
              itemBuilder: (_, index) {
                final clue = clues[index];
                return ListTile(
                  dense: true,
                  leading: const Icon(Icons.local_hospital),
                  title: Text(clue.nombre),
                  subtitle: Text(
                      '${clue.distanciaKm.toStringAsFixed(1)} km · ${clue.direccion}'),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: () => showClue(clue),
                );
              },
            ),
          ),
        ],
      );

  Future<void> showClue(Clue clue) async {
    final detail =
        await widget.api.getClueDetail(clue.clues).catchError((_) => clue);
    if (!mounted) return;
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (context) => Padding(
        padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
        child: Wrap(
          runSpacing: 8,
          children: [
            Text(detail.nombre, style: Theme.of(context).textTheme.titleLarge),
            Text(detail.institucion ?? 'Unidad médica'),
            Text(detail.direccion),
            if (detail.nivelAtencion != 'No especificado')
              Text('Nivel de atención: ${detail.nivelAtencion}'),
            if (detail.telefono != null) Text('Teléfono: ${detail.telefono}'),
            if (detail.horario != null) Text('Horario: ${detail.horario}'),
            FilledButton.icon(
              onPressed: () async {
                Navigator.pop(context);
                await drawRouteTo(detail);
              },
              icon: const Icon(Icons.route),
              label: const Text('Marcar ruta en el mapa'),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> drawRouteTo(Clue clue) async {
    final uri = Uri.parse(
      'https://router.project-osrm.org/route/v1/driving/'
      '${center.longitude},${center.latitude};'
      '${clue.lon},${clue.lat}?overview=full&geometries=geojson',
    );
    try {
      final response = await http
          .get(uri, headers: {'User-Agent': 'VIRALES-App/1.0'})
          .timeout(const Duration(seconds: 15));
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw Exception('El servicio de rutas no respondió correctamente.');
      }
      final body = jsonDecode(response.body);
      final routes = body is Map ? body['routes'] : null;
      final firstRoute = routes is List && routes.isNotEmpty ? routes.first : null;
      final geometry = firstRoute is Map ? firstRoute['geometry'] : null;
      final coordinates = geometry is Map ? geometry['coordinates'] : null;
      if (coordinates is! List || coordinates.isEmpty) {
        throw Exception('No se encontró una ruta para esta unidad.');
      }
      final points = coordinates
          .whereType<List>()
          .where((point) => point.length >= 2)
          .map((point) => LatLng(
                (point[1] as num).toDouble(),
                (point[0] as num).toDouble(),
              ))
          .toList();
      if (points.length < 2) {
        throw Exception('La ruta recibida está incompleta.');
      }
      if (mounted) {
        setState(() {
          routePoints = points;
          message = 'Ruta marcada hacia ${clue.nombre}.';
        });
      }
    } catch (error) {
      if (mounted) {
        setState(() {
          message = 'No se pudo marcar la ruta: $error';
          routePoints = [];
        });
      }
    }
  }
}
