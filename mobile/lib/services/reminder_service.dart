import 'package:flutter_local_notifications/flutter_local_notifications.dart';

class ReminderService {
  ReminderService._();
  static final instance = ReminderService._();

  final plugin = FlutterLocalNotificationsPlugin();
  bool initialized = false;

  Future<void> initialize() async {
    if (initialized) return;
    const android = AndroidInitializationSettings('@mipmap/ic_launcher');
    const ios = DarwinInitializationSettings();
    await plugin.initialize(
      const InitializationSettings(android: android, iOS: ios),
    );
    await plugin
        .resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin>()
        ?.requestNotificationsPermission();
    initialized = true;
  }

  Future<void> scheduleDaily() async {
    await initialize();
    await plugin.periodicallyShow(
      42,
      'Seguimiento de síntomas',
      'Recuerda registrar cómo te sientes hoy.',
      RepeatInterval.daily,
      const NotificationDetails(
        android: AndroidNotificationDetails(
          'symptoms_reminders',
          'Recordatorios de síntomas',
          channelDescription: 'Avisos diarios para registrar síntomas',
          importance: Importance.defaultImportance,
        ),
        iOS: DarwinNotificationDetails(),
      ),
      androidScheduleMode: AndroidScheduleMode.inexactAllowWhileIdle,
    );
  }

  Future<void> cancel() => plugin.cancel(42);
}
