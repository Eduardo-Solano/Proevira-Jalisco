class AppConfig {
  const AppConfig._();

  // Override with --dart-define=API_BASE_URL=https://... for another backend.
  static const apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'https://virales.onrender.com/api/v1',
  );
  static const wsBaseUrl = String.fromEnvironment(
    'WS_BASE_URL',
    defaultValue: 'wss://virales.onrender.com/ws/alerts',
  );
  static const appName = 'VIRALES App';
}
