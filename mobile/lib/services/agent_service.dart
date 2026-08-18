import 'dart:convert';

import '../core/api/api_client.dart';
import '../models/agent_chat.dart';

class AgentService {
  AgentService(this.client);

  final ApiClient client;

  Future<AgentChatResponse> sendMessage({
    required int userId,
    required String message,
    String? sessionId,
    List<ChatMessage> history = const [],
  }) async {
    final data = await client.post(
      '/api/v1/agent/chat',
      body: {
        'message': message,
        'session_id': sessionId,
        'user_id': userId,
        'history': history.map((item) => item.toHistoryJson()).toList(),
        'context': <String, dynamic>{},
      },
    ) as Map<String, dynamic>;
    return AgentChatResponse.fromJson(data);
  }

  Stream<AgentStreamEvent> sendMessageStream({
    required int userId,
    required String message,
    String? sessionId,
    List<ChatMessage> history = const [],
  }) async* {
    final chunks = client.postStream(
      '/api/v1/agent/chat/stream',
      body: {
        'message': message,
        'session_id': sessionId,
        'user_id': userId,
        'history': history.map((item) => item.toHistoryJson()).toList(),
        'context': <String, dynamic>{},
      },
    );

    final buffer = StringBuffer();
    await for (final chunk in chunks) {
      buffer.write(chunk.replaceAll('\r\n', '\n'));
      while (true) {
        final text = buffer.toString();
        final boundary = text.indexOf('\n\n');
        if (boundary < 0) {
          break;
        }
        final frame = text.substring(0, boundary);
        buffer
          ..clear()
          ..write(text.substring(boundary + 2));
        final event = _parseSseFrame(frame);
        if (event != null) {
          yield event;
        }
      }
    }
  }

  AgentStreamEvent? _parseSseFrame(String frame) {
    String? eventName;
    final data = StringBuffer();
    for (final line in frame.split('\n')) {
      if (line.startsWith('event:')) {
        eventName = line.substring(6).trim();
      } else if (line.startsWith('data:')) {
        data.writeln(line.substring(5).trimLeft());
      }
    }
    final rawData = data.toString().trimRight();
    if (rawData.isEmpty) {
      return null;
    }
    final payload = _decodeJson(rawData);
    if (payload is! Map<String, dynamic>) {
      return null;
    }
    final type = payload['type']?.toString() ?? eventName;
    if (type == 'token') {
      return AgentStreamEvent.token(payload['content']?.toString() ?? '');
    }
    if (type == 'done') {
      final response = payload['data'];
      if (response is Map<String, dynamic>) {
        return AgentStreamEvent.done(AgentChatResponse.fromJson(response));
      }
    }
    if (type == 'error') {
      return AgentStreamEvent.error(payload['message']?.toString() ?? '请求失败');
    }
    return null;
  }

  dynamic _decodeJson(String value) {
    return const JsonDecoder().convert(value);
  }

  Future<List<ChatMessage>> listHistory({
    required int userId,
    String? sessionId,
  }) async {
    final query = {'user_id': userId.toString()};
    if (sessionId != null && sessionId.isNotEmpty) {
      query['session_id'] = sessionId;
    }
    final data = await client.get(
      '/api/v1/agent/history',
      query: query,
    ) as List<dynamic>;
    return data
        .whereType<Map<String, dynamic>>()
        .map((item) => ChatMessage(
              role: item['role']?.toString() ?? 'assistant',
              content: item['content']?.toString() ?? '',
            ))
        .where((message) => message.content.isNotEmpty)
        .toList(growable: false);
  }

  Future<void> clearHistory({required int userId, String? sessionId}) async {
    final uri = StringBuffer('/api/v1/agent/history?user_id=$userId');
    if (sessionId != null && sessionId.isNotEmpty) {
      uri.write('&session_id=$sessionId');
    }
    await client.delete(uri.toString());
  }
}
