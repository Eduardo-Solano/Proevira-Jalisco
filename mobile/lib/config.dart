class AppConfig {
  const AppConfig._();

  // Override with --dart-define=API_BASE_URL=https://... for a deployed backend.
  static const apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000/api/v1',
  );
  static const wsBaseUrl = String.fromEnvironment(
    'WS_BASE_URL',
    defaultValue: 'ws://10.0.2.2:8000/ws/alerts',
  );
  static const appName = 'Proevira Jalisco';
}
