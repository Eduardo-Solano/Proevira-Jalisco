import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

import '../config.dart';

class AlertsSocket {
  WebSocketChannel? _channel;
  StreamSubscription<dynamic>? _subscription;
  final _events = StreamController<Map<String, dynamic>>.broadcast();

  Stream<Map<String, dynamic>> get events => _events.stream;

  void connect(String token) {
    disconnect();
    final uri = Uri.parse(AppConfig.wsBaseUrl).replace(
      queryParameters: {'token': token},
    );
    _channel = WebSocketChannel.connect(uri);
    _subscription = _channel!.stream.listen(
      (event) {
        final decoded = jsonDecode('$event');
        if (decoded is Map) {
          _events.add(Map<String, dynamic>.from(decoded));
        }
      },
      onError: (_) {},
      onDone: () => _channel = null,
    );
  }

  void disconnect() {
    _subscription?.cancel();
    _subscription = null;
    _channel?.sink.close();
    _channel = null;
  }

  Future<void> dispose() async {
    disconnect();
    await _events.close();
  }
}
