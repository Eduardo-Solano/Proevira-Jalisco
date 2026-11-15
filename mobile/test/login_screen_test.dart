import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:proevira_mobile/screens/login_screen.dart';

void main() {
  testWidgets('permite alternar a registro y enviar los datos de paciente',
      (tester) async {
    String? regEmail;
    String? regPassword;
    String? regMunicipio;

    await tester.pumpWidget(
      MaterialApp(
        home: LoginScreen(
          onLogin: (_, __) async {},
          onRegister: (email, password, municipioId) async {
            regEmail = email;
            regPassword = password;
            regMunicipio = municipioId;
          },
        ),
      ),
    );

    expect(find.text('Iniciar sesión'), findsWidgets);
    expect(find.text('Confirmar contraseña'), findsNothing);

    await tester.tap(find.text('Registrarse'));
    await tester.pumpAndSettle();

    expect(find.text('Confirmar contraseña'), findsOneWidget);
    expect(find.text('Municipio (opcional)'), findsOneWidget);

    await tester.enterText(
      find.widgetWithText(TextFormField, 'Correo electrónico'),
      'paciente.nuevo@jalisco.mx',
    );
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Contraseña'),
      'secreto123',
    );
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Confirmar contraseña'),
      'secreto123',
    );

    await tester.ensureVisible(find.text('Crear cuenta'));
    await tester.tap(find.text('Crear cuenta'));
    await tester.pumpAndSettle();

    expect(regEmail, 'paciente.nuevo@jalisco.mx');
    expect(regPassword, 'secreto123');
    expect(regMunicipio, isNull);
  });

  testWidgets('valida que las contraseñas coincidan en registro',
      (tester) async {
    var called = false;

    await tester.pumpWidget(
      MaterialApp(
        home: LoginScreen(
          onLogin: (_, __) async {},
          onRegister: (_, __, ___) async {
            called = true;
          },
        ),
      ),
    );

    await tester.tap(find.text('Registrarse'));
    await tester.pumpAndSettle();

    await tester.enterText(
      find.widgetWithText(TextFormField, 'Correo electrónico'),
      'paciente.nuevo@jalisco.mx',
    );
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Contraseña'),
      'secreto123',
    );
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Confirmar contraseña'),
      'otra1234',
    );

    await tester.ensureVisible(find.text('Crear cuenta'));
    await tester.tap(find.text('Crear cuenta'));
    await tester.pumpAndSettle();

    expect(find.text('Las contraseñas no coinciden'), findsOneWidget);
    expect(called, isFalse);
  });
}
