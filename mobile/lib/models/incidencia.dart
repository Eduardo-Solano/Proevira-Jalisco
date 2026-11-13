class Incidencia {
  const Incidencia({
    required this.municipio,
    required this.nombre,
    required this.lat,
    required this.lon,
    required this.casos,
    required this.promedioSemanal,
    required this.ultimaSemana,
  });

  final String municipio;
  final String nombre;
  final double lat;
  final double lon;
  final int casos;
  final double promedioSemanal;
  final String ultimaSemana;

  factory Incidencia.fromJson(Map<String, dynamic> json) => Incidencia(
        municipio: '${json['municipio'] ?? ''}',
        nombre: '${json['nombre'] ?? json['municipio'] ?? ''}',
        lat: _double(json['lat']),
        lon: _double(json['lon']),
        casos: json['casos'] is num
            ? (json['casos'] as num).round()
            : int.tryParse('${json['casos']}') ?? 0,
        promedioSemanal: _double(json['promedio_semanal']),
        ultimaSemana: '${json['ultima_semana'] ?? ''}',
      );

  static double _double(Object? value) =>
      value is num ? value.toDouble() : double.tryParse('$value') ?? 0;
}
