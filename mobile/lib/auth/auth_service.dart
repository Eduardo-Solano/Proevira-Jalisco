import 'package:shared_preferences/shared_preferences.dart';

import '../api/api_client.dart';

class AuthSession {
  const AuthSession({
    required this.token,
    required this.role,
    required this.uid,
    this.municipioId,
    this.email,
  });

  final String token;
  final String role;
  final String uid;
  final String? municipioId;
  final String? email;
}

class AuthService {
  AuthService(this.api);

  final ApiClient api;
  AuthSession? session;

  Future<AuthSession?> restore() async {
    final preferences = await SharedPreferences.getInstance();
    final token = preferences.getString('auth_token');
    final role = preferences.getString('auth_role');
    final uid = preferences.getString('auth_uid');
    if (token == null || role == null || uid == null) return null;
    api.token = token;
    session = AuthSession(
      token: token,
      role: role,
      uid: uid,
      municipioId: preferences.getString('auth_municipio'),
      email: preferences.getString('auth_email'),
    );
    return session;
  }

  Future<AuthSession> login(String email, String password) async {
    final data = await api.login(email, password);
    final token = '${data['token'] ?? ''}';
    final role = '${data['role'] ?? 'paciente'}';
    final uid = '${data['uid'] ?? ''}';
    if (token.isEmpty || uid.isEmpty) {
      throw const ApiException(
          'La respuesta de autenticación está incompleta.', null);
    }
    if (role != 'paciente') {
      throw const ApiException(
        'Esta aplicación está disponible únicamente para pacientes.',
        null,
      );
    }
    api.token = token;
    session = AuthSession(
      token: token,
      role: role,
      uid: uid,
      municipioId: data['municipio_id']?.toString(),
      email: data['email']?.toString() ?? email,
    );
    final preferences = await SharedPreferences.getInstance();
    await preferences.setString('auth_token', token);
    await preferences.setString('auth_role', role);
    await preferences.setString('auth_uid', uid);
    await preferences.setString('auth_email', session!.email ?? email);
    if (session!.municipioId != null) {
      await preferences.setString('auth_municipio', session!.municipioId!);
    }
    return session!;
  }

  Future<void> logout() async {
    api.token = null;
    session = null;
    final preferences = await SharedPreferences.getInstance();
    await preferences.remove('auth_token');
    await preferences.remove('auth_role');
    await preferences.remove('auth_uid');
    await preferences.remove('auth_email');
    await preferences.remove('auth_municipio');
  }

  Future<AuthSession> updateMunicipio(String? municipioId) async {
    final data = await api.updatePatientProfile(municipioId);
    final current = session;
    if (current == null) {
      throw const ApiException('La sesión no está disponible.', null);
    }
    session = AuthSession(
      token: current.token,
      role: current.role,
      uid: current.uid,
      municipioId: data['municipio_id']?.toString(),
      email: current.email,
    );
    final preferences = await SharedPreferences.getInstance();
    if (municipioId == null) {
      await preferences.remove('auth_municipio');
    } else {
      await preferences.setString('auth_municipio', municipioId);
    }
    return session!;
  }
}
