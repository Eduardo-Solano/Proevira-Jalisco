import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../config.dart';
import '../models/alerta.dart';
import '../models/clue.dart';
import '../models/incidencia.dart';
import '../models/prediccion.dart';

class ApiException implements Exception {
  const ApiException(this.message, this.statusCode);
  final String message;
  final int? statusCode;
  @override
  String toString() => message;
}

class ApiClient {
  ApiClient({http.Client? client}) : _client = client ?? http.Client();
  final http.Client _client;
  String? token;

  void dispose() => _client.close();

  Map<String, String> get _headers {
    final headers = <String, String>{
      'Accept': 'application/json',
      'Content-Type': 'application/json',
    };
    if (token != null) {
      headers['Authorization'] = 'Bearer $token';
    }
    return headers;
  }

  Future<Map<String, dynamic>> login(String email, String password) async =>
      _asMap(await _request(
        'POST',
        '/auth/login',
        body: {'email': email, 'password': password},
        authenticated: false,
      ));

  Future<Map<String, dynamic>> me() async =>
      _asMap(await _request('GET', '/auth/me'));

  Future<Map<String, dynamic>> updatePatientProfile(String? municipioId) async =>
      _asMap(await _request(
        'PATCH',
        '/auth/me',
        body: {'municipio_id': municipioId},
      ));

  Future<List<Alerta>> getAlerts({String? municipio}) async {
    final query = <String, String>{'activa': 'true'};
    if (municipio != null && municipio.isNotEmpty) {
      query['municipio'] = municipio;
    }
    return _asList(await _request('GET', '/alerts', query: query))
        .map(Alerta.fromJson)
        .toList();
  }

  Future<List<Clue>> nearestClues(double lat, double lon) async =>
      _asList(await _request(
        'GET',
        '/clues/nearest',
        query: {'lat': '$lat', 'lon': '$lon', 'limit': '10'},
      ))
          .map(Clue.fromJson)
          .toList();

  Future<Clue> getClueDetail(String clues) async =>
      Clue.fromJson(_asMap(await _request('GET', '/clues/$clues')));

  Future<List<Incidencia>> getMobileIncidence({
    String enfermedad = 'dengue',
    int semanas = 8,
  }) async {
    final response = _asMap(await _request(
      'GET',
      '/dashboard/mobile-incidence',
      query: {'enfermedad': enfermedad, 'semanas': '$semanas'},
    ));
    final points = response['puntos'];
    if (points is! List) {
      throw const ApiException('Formato de incidencia inesperado.', null);
    }
    return points
        .whereType<Map>()
        .map((item) => Incidencia.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }

  Future<Map<String, dynamic>> postSymptoms(
    Map<String, dynamic> symptoms,
  ) async =>
      _asMap(await _request('POST', '/symptoms', body: symptoms));

  Future<List<Map<String, dynamic>>> getMySymptoms() async =>
      _asList(await _request('GET', '/symptoms/mine'));

  Future<Prediccion> getPrediction({
    required String municipio,
    String? semana,
    String enfermedad = 'dengue',
  }) async {
    final query = <String, String>{
      'municipio': municipio,
      'enfermedad': enfermedad,
      if (semana != null && semana.isNotEmpty) 'semana': semana,
    };
    return Prediccion.fromJson(
      _asMap(await _request('GET', '/predictions', query: query)),
    );
  }

  Future<dynamic> _request(
    String method,
    String path, {
    Map<String, String>? query,
    Map<String, dynamic>? body,
    bool authenticated = true,
  }) async {
    final uri = Uri.parse('${AppConfig.apiBaseUrl}$path').replace(
      queryParameters: query,
    );
    final request = http.Request(method, uri)
      ..headers.addAll(authenticated
          ? _headers
          : {
              'Accept': 'application/json',
              'Content-Type': 'application/json',
            })
      ..body = body == null ? '' : jsonEncode(body);
    late final http.StreamedResponse response;
    try {
      response =
          await _client.send(request).timeout(const Duration(seconds: 15));
    } on TimeoutException {
      throw const ApiException('El servidor tardó demasiado.', null);
    } on SocketException {
      throw const ApiException('No se pudo conectar con el backend.', null);
    } on http.ClientException {
      throw const ApiException('No se pudo conectar con el backend.', null);
    }
    final raw = await response.stream.bytesToString();
    dynamic decoded;
    if (raw.isNotEmpty) {
      try {
        decoded = jsonDecode(raw);
      } on FormatException {
        throw ApiException('El servidor devolvió una respuesta inválida.',
            response.statusCode);
      }
    }
    if (response.statusCode < 200 || response.statusCode >= 300) {
      final detail = decoded is Map ? decoded['detail'] : null;
      throw ApiException(
        detail?.toString() ?? 'La solicitud falló (${response.statusCode}).',
        response.statusCode,
      );
    }
    return decoded;
  }

  static Map<String, dynamic> _asMap(dynamic value) {
    if (value is Map<String, dynamic>) return value;
    if (value is Map) return Map<String, dynamic>.from(value);
    throw const ApiException('Formato de respuesta inesperado.', null);
  }

  static List<Map<String, dynamic>> _asList(dynamic value) {
    if (value is! List) {
      throw const ApiException('Formato de lista inesperado.', null);
    }
    return value.whereType<Map>().map(Map<String, dynamic>.from).toList();
  }
}
