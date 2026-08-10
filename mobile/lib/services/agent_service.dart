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
}
