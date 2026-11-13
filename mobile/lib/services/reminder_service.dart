import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:flutter/material.dart';
import 'package:timezone/data/latest.dart' as tz;
import 'package:timezone/timezone.dart' as tz;

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
    tz.initializeTimeZones();
    await plugin
        .resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin>()
        ?.requestNotificationsPermission();
    initialized = true;
  }

  Future<void> scheduleDaily() async {
    await scheduleDailyAt(const TimeOfDay(hour: 19, minute: 0));
  }

  Future<void> scheduleDailyAt(TimeOfDay time) async {
    await initialize();
    await plugin.zonedSchedule(
      42,
      'Seguimiento de síntomas',
      'Recuerda registrar cómo te sientes hoy.',
      _nextOccurrence(time),
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
      uiLocalNotificationDateInterpretation:
          UILocalNotificationDateInterpretation.wallClockTime,
      matchDateTimeComponents: DateTimeComponents.time,
    );
  }

  tz.TZDateTime _nextOccurrence(TimeOfDay time) {
    final now = tz.TZDateTime.now(tz.local);
    var scheduled = tz.TZDateTime(
      tz.local,
      now.year,
      now.month,
      now.day,
      time.hour,
      time.minute,
    );
    if (!scheduled.isAfter(now)) {
      scheduled = scheduled.add(const Duration(days: 1));
    }
    return scheduled;
  }

  Future<void> cancel() => plugin.cancel(42);

  Future<void> showAlertNotification({
    required String title,
    required String body,
  }) async {
    await initialize();
    await plugin.show(
      43,
      title,
      body,
      const NotificationDetails(
        android: AndroidNotificationDetails(
          'epidemiological_alerts',
          'Alertas epidemiológicas',
          channelDescription: 'Avisos de vigilancia epidemiológica',
          importance: Importance.high,
          priority: Priority.high,
        ),
        iOS: DarwinNotificationDetails(),
      ),
    );
  }
}
