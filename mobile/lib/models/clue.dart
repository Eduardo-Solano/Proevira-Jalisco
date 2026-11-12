class Clue {
  const Clue({
    required this.clues,
    required this.nombre,
    required this.direccion,
    required this.nivelAtencion,
    required this.distanciaKm,
    required this.lat,
    required this.lon,
    this.telefono,
    this.horario,
    this.institucion,
  });

  final String clues;
  final String nombre;
  final String direccion;
  final String nivelAtencion;
  final double distanciaKm;
  final double lat;
  final double lon;
  final String? telefono;
  final String? horario;
  final String? institucion;

  factory Clue.fromJson(Map<String, dynamic> json) => Clue(
        clues: '${json['clues'] ?? ''}',
        nombre: '${json['nombre'] ?? 'Unidad médica'}',
        direccion: '${json['direccion'] ?? 'Sin dirección'}',
        nivelAtencion: '${json['nivel_atencion'] ?? 'No especificado'}',
        distanciaKm: _asDouble(json['distancia_km']),
        lat: _asDouble(json['lat']),
        lon: _asDouble(json['lon']),
        telefono: json['telefono'] as String?,
        horario: json['horario'] as String?,
        institucion: json['institucion'] as String?,
      );

  Map<String, Object?> toMap() => {
        'clues': clues,
        'nombre': nombre,
        'direccion': direccion,
        'nivel_atencion': nivelAtencion,
        'distancia_km': distanciaKm,
        'lat': lat,
        'lon': lon,
        'telefono': telefono,
        'horario': horario,
      };

  static double _asDouble(Object? value) =>
      value is num ? value.toDouble() : double.tryParse('$value') ?? 0;
}
