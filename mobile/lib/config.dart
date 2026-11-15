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

  static const municipiosCentro = <String, String>{
    '14039': 'Guadalajara',
    '14120': 'Zapopan',
    '14098': 'San Pedro Tlaquepaque',
    '14101': 'Tonalá',
    '14097': 'Tlajomulco de Zúñiga',
    '14070': 'El Salto',
    '14124': 'Zapotlanejo',
    '14044': 'Ixtlahuacán de los Membrillos',
    '14045': 'Ixtlahuacán del Río',
    '14051': 'Juanacatlán',
    '14029': 'Cuquío',
    '14071': 'San Cristóbal de la Barranca',
  };
}
