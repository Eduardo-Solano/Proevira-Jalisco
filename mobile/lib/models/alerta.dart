class Alerta {
  const Alerta({
    required this.id,
    required this.municipio,
    required this.nivel,
    required this.mensaje,
    required this.timestamp,
    this.activa = true,
  });

  final int id;
  final String municipio;
  final String nivel;
  final String mensaje;
  final DateTime timestamp;
  final bool activa;

  factory Alerta.fromJson(Map<String, dynamic> json) => Alerta(
        id: _asInt(json['id']),
        municipio: '${json['municipio'] ?? json['municipio_id'] ?? 'Jalisco'}',
        nivel: '${json['nivel'] ?? 'medio'}',
        mensaje: '${json['mensaje'] ?? ''}',
        timestamp: DateTime.tryParse(
              '${json['ts'] ?? json['timestamp'] ?? ''}',
            ) ??
            DateTime.now(),
        activa: json['activa'] as bool? ?? true,
      );

  Map<String, Object?> toMap() => {
        'id': id,
        'municipio': municipio,
        'nivel': nivel,
        'mensaje': mensaje,
        'ts': timestamp.toIso8601String(),
        'activa': activa ? 1 : 0,
      };

  static int _asInt(Object? value) =>
      value is int ? value : int.tryParse('$value') ?? 0;
}
