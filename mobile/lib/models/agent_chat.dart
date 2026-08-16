class ChatMessage {
  const ChatMessage({required this.role, required this.content});

  final String role;
  final String content;

  bool get isUser => role == 'user';

  Map<String, String> toHistoryJson() => {'role': role, 'content': content};
}

class AgentSuggestion {
  const AgentSuggestion({
    required this.planId,
    required this.title,
    required this.description,
    this.impact = '',
    this.isRecommended = false,
  });

  final String planId;
  final String title;
  final String description;
  final String impact;
  final bool isRecommended;

  factory AgentSuggestion.fromJson(Map<String, dynamic> json) {
    return AgentSuggestion(
      planId: json['plan_id']?.toString() ?? '',
      title: json['title']?.toString() ?? '',
      description: json['description']?.toString() ?? '',
      impact: json['impact']?.toString() ?? '',
      isRecommended: json['is_recommended'] == true,
    );
  }
}

class AgentChatResponse {
  const AgentChatResponse({
    required this.reply,
    required this.sessionId,
    this.needsConfirmation = false,
    this.confirmationStage = '',
    this.conflicts = const [],
    this.suggestions = const [],
    this.tasksCreated = const [],
    this.tasksUpdated = const [],
    this.actionsTaken = const [],
  });

  final String reply;
  final String sessionId;
  final bool needsConfirmation;
  final String confirmationStage;
  final List<Map<String, dynamic>> conflicts;
  final List<AgentSuggestion> suggestions;
  final List<int> tasksCreated;
  final List<Map<String, dynamic>> tasksUpdated;
  final List<String> actionsTaken;

  factory AgentChatResponse.fromJson(Map<String, dynamic> json) {
    return AgentChatResponse(
      reply: json['reply']?.toString() ?? '',
      sessionId: json['session_id']?.toString() ?? '',
      needsConfirmation: json['needs_confirmation'] == true,
      confirmationStage: json['confirmation_stage']?.toString() ?? '',
      conflicts: (json['conflicts'] as List<dynamic>? ?? const [])
          .whereType<Map<String, dynamic>>()
          .toList(),
      suggestions: (json['suggestions'] as List<dynamic>? ?? const [])
          .whereType<Map<String, dynamic>>()
          .map(AgentSuggestion.fromJson)
          .toList(),
      tasksCreated: (json['tasks_created'] as List<dynamic>? ?? const [])
          .whereType<int>()
          .toList(),
      tasksUpdated: (json['tasks_updated'] as List<dynamic>? ?? const [])
          .whereType<Map<String, dynamic>>()
          .toList(),
      actionsTaken: (json['actions_taken'] as List<dynamic>? ?? const [])
          .map((item) => item.toString())
          .toList(),
    );
  }
}
