class Prediccion {
  const Prediccion({
    required this.municipio,
    required this.semana,
    required this.enfermedad,
    required this.casosEsperados,
    required this.nivelRiesgo,
    this.shapTop3 = const [],
    this.lat,
    this.lon,
  });

  final String municipio;
  final String semana;
  final String enfermedad;
  final double casosEsperados;
  final String nivelRiesgo;
  final List<Map<String, dynamic>> shapTop3;
  final double? lat;
  final double? lon;

  factory Prediccion.fromJson(Map<String, dynamic> json) => Prediccion(
        municipio: '${json['municipio'] ?? json['municipio_id'] ?? ''}',
        semana: '${json['semana'] ?? ''}',
        enfermedad: '${json['enfermedad'] ?? 'dengue'}',
        casosEsperados: _asDouble(json['casos_esperados']),
        nivelRiesgo: '${json['nivel_riesgo'] ?? 'bajo'}',
        shapTop3: (json['shap_top3'] as List<dynamic>? ?? [])
            .whereType<Map<String, dynamic>>()
            .toList(),
        lat: _optionalDouble(json['lat']),
        lon: _optionalDouble(json['lon']),
      );

  static double _asDouble(Object? value) =>
      value is num ? value.toDouble() : double.tryParse('$value') ?? 0;

  static double? _optionalDouble(Object? value) =>
      value == null ? null : _asDouble(value);
}
