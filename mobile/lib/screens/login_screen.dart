import 'package:flutter/material.dart';

import '../config.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({
    required this.onLogin,
    required this.onRegister,
    super.key,
  });

  final Future<void> Function(String email, String password) onLogin;
  final Future<void> Function(
      String email, String password, String? municipioId) onRegister;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final email = TextEditingController();
  final password = TextEditingController();
  final confirmPassword = TextEditingController();
  final formKey = GlobalKey<FormState>();

  bool isRegister = false;
  bool obscurePassword = true;
  bool obscureConfirmPassword = true;
  String? selectedMunicipio;
  bool loading = false;
  String? error;

  @override
  void dispose() {
    email.dispose();
    password.dispose();
    confirmPassword.dispose();
    super.dispose();
  }

  void _setMode(bool registerMode) {
    if (loading || isRegister == registerMode) return;
    setState(() {
      isRegister = registerMode;
      error = null;
      confirmPassword.clear();
      formKey.currentState?.reset();
    });
  }

  Future<void> submit() async {
    if (!formKey.currentState!.validate()) return;
    setState(() {
      loading = true;
      error = null;
    });
    try {
      final cleanEmail = email.text.trim();
      if (isRegister) {
        await widget.onRegister(cleanEmail, password.text, selectedMunicipio);
      } else {
        await widget.onLogin(cleanEmail, password.text);
      }
    } catch (exception) {
      if (mounted) setState(() => error = exception.toString());
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        body: SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(24),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 420),
                child: Form(
                  key: formKey,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const Icon(Icons.health_and_safety, size: 72),
                      const SizedBox(height: 12),
                      Text(AppConfig.appName,
                          textAlign: TextAlign.center,
                          style: Theme.of(context).textTheme.headlineMedium),
                      const SizedBox(height: 8),
                      Text(
                        isRegister
                            ? 'Crea tu cuenta de paciente para recibir alertas y registrar síntomas'
                            : 'Vigilancia epidemiológica y orientación ciudadana',
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: 24),
                      SegmentedButton<bool>(
                        segments: const [
                          ButtonSegment<bool>(
                            value: false,
                            label: Text('Iniciar sesión'),
                            icon: Icon(Icons.login),
                          ),
                          ButtonSegment<bool>(
                            value: true,
                            label: Text('Registrarse'),
                            icon: Icon(Icons.person_add_outlined),
                          ),
                        ],
                        selected: {isRegister},
                        onSelectionChanged: (selection) =>
                            _setMode(selection.first),
                      ),
                      const SizedBox(height: 24),
                      TextFormField(
                        controller: email,
                        keyboardType: TextInputType.emailAddress,
                        spellCheckConfiguration:
                            const SpellCheckConfiguration.disabled(),
                        decoration: const InputDecoration(
                          labelText: 'Correo electrónico',
                          prefixIcon: Icon(Icons.email_outlined),
                          border: OutlineInputBorder(),
                        ),
                        validator: (value) {
                          final trimmed = value?.trim() ?? '';
                          if (trimmed.isEmpty || !trimmed.contains('@')) {
                            return 'Ingresa un correo válido';
                          }
                          final parts = trimmed.split('@');
                          if (parts.length != 2 ||
                              parts[0].isEmpty ||
                              !parts[1].contains('.')) {
                            return 'Ingresa un correo válido';
                          }
                          return null;
                        },
                      ),
                      const SizedBox(height: 16),
                      TextFormField(
                        controller: password,
                        obscureText: obscurePassword,
                        spellCheckConfiguration:
                            const SpellCheckConfiguration.disabled(),
                        decoration: InputDecoration(
                          labelText: 'Contraseña',
                          prefixIcon: const Icon(Icons.lock_outline),
                          border: const OutlineInputBorder(),
                          suffixIcon: IconButton(
                            onPressed: () => setState(
                                () => obscurePassword = !obscurePassword),
                            icon: Icon(obscurePassword
                                ? Icons.visibility_outlined
                                : Icons.visibility_off_outlined),
                          ),
                        ),
                        validator: (value) => value == null || value.length < 6
                            ? 'Mínimo 6 caracteres'
                            : null,
                      ),
                      if (isRegister) ...[
                        const SizedBox(height: 16),
                        TextFormField(
                          controller: confirmPassword,
                          obscureText: obscureConfirmPassword,
                          spellCheckConfiguration:
                              const SpellCheckConfiguration.disabled(),
                          decoration: InputDecoration(
                            labelText: 'Confirmar contraseña',
                            prefixIcon: const Icon(Icons.lock_reset_outlined),
                            border: const OutlineInputBorder(),
                            suffixIcon: IconButton(
                              onPressed: () => setState(() =>
                                  obscureConfirmPassword =
                                      !obscureConfirmPassword),
                              icon: Icon(obscureConfirmPassword
                                  ? Icons.visibility_outlined
                                  : Icons.visibility_off_outlined),
                            ),
                          ),
                          validator: (value) {
                            if (!isRegister) return null;
                            if (value != password.text) {
                              return 'Las contraseñas no coinciden';
                            }
                            return null;
                          },
                        ),
                        const SizedBox(height: 16),
                        DropdownButtonFormField<String?>(
                          initialValue: selectedMunicipio,
                          isExpanded: true,
                          decoration: const InputDecoration(
                            labelText: 'Municipio (opcional)',
                            prefixIcon: Icon(Icons.location_on_outlined),
                            border: OutlineInputBorder(),
                          ),
                          items: [
                            const DropdownMenuItem<String?>(
                              value: null,
                              child: Text(
                                  'Detectar automáticamente / Todo Jalisco'),
                            ),
                            ...AppConfig.municipiosCentro.entries.map(
                              (entry) => DropdownMenuItem<String?>(
                                value: entry.key,
                                child: Text(entry.value),
                              ),
                            ),
                          ],
                          onChanged: loading
                              ? null
                              : (value) =>
                                  setState(() => selectedMunicipio = value),
                        ),
                      ],
                      if (error != null) ...[
                        const SizedBox(height: 12),
                        Text(error!,
                            style: TextStyle(
                                color: Theme.of(context).colorScheme.error)),
                      ],
                      const SizedBox(height: 24),
                      FilledButton(
                        onPressed: loading ? null : submit,
                        child: loading
                            ? const SizedBox.square(
                                dimension: 20,
                                child: CircularProgressIndicator())
                            : Text(
                                isRegister ? 'Crear cuenta' : 'Iniciar sesión'),
                      ),
                      const SizedBox(height: 12),
                      TextButton(
                        onPressed: loading ? null : () => _setMode(!isRegister),
                        child: Text(
                          isRegister
                              ? '¿Ya tienes cuenta? Inicia sesión'
                              : '¿No tienes cuenta? Regístrate',
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      );
}
