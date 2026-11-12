class RegistroSintomas {
  const RegistroSintomas({
    required this.idLocal,
    required this.fecha,
    required this.sintomas,
    required this.dias,
    required this.sincronizado,
    this.temperatura,
    this.sospecha,
    this.recomendacion,
  });

  final String idLocal;
  final DateTime fecha;
  final List<String> sintomas;
  final int dias;
  final bool sincronizado;
  final double? temperatura;
  final String? sospecha;
  final String? recomendacion;

  factory RegistroSintomas.fromPayload(
    Map<String, dynamic> payload, {
    bool sincronizado = false,
    String? recomendacion,
  }) {
    final symptoms = <String>[
      if (payload['fiebre'] == true) 'Fiebre',
      if (payload['cefalea'] == true) 'Dolor de cabeza',
      if (payload['dolor_muscular'] == true) 'Dolor muscular',
      if (payload['dolor_articular'] == true) 'Dolor articular',
      if (payload['dolor_retroocular'] == true) 'Dolor retroocular',
      if (payload['tos'] == true) 'Tos',
      if (payload['dificultad_respiratoria'] == true) 'Dificultad respiratoria',
      if ('${payload['otros_sintomas'] ?? ''}'.trim().isNotEmpty)
        '${payload['otros_sintomas']}',
    ];
    return RegistroSintomas(
      idLocal: '${payload['id_local']}',
      fecha: DateTime.tryParse('${payload['ts_registro']}') ?? DateTime.now(),
      sintomas: symptoms,
      dias: int.tryParse('${payload['dias_con_sintomas'] ?? 1}') ?? 1,
      sincronizado: sincronizado,
      temperatura: _asDouble(payload['temperatura']),
      sospecha: payload['sospecha_enfermedad']?.toString(),
      recomendacion: recomendacion ?? payload['recomendacion']?.toString(),
    );
  }

  factory RegistroSintomas.fromServer(Map<String, dynamic> json) =>
      RegistroSintomas.fromPayload(json, sincronizado: true);

  static double? _asDouble(Object? value) =>
      value == null ? null : double.tryParse('$value');
}
