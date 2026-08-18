import 'user.dart';

class AuthSession {
  const AuthSession({
    required this.token,
    required this.user,
    this.sessionId = '',
    this.tokenType = 'Bearer',
  });

  final String token;
  final String tokenType;
  final String sessionId;
  final User user;

  factory AuthSession.fromJson(Map<String, dynamic> json) {
    return AuthSession(
      token: json['token']?.toString() ?? '',
      tokenType: json['token_type']?.toString() ?? 'Bearer',
      sessionId: json['session_id']?.toString() ?? '',
      user: User.fromJson(json['user'] as Map<String, dynamic>),
    );
  }

  Map<String, dynamic> toJson() => {
        'token': token,
        'token_type': tokenType,
        'session_id': sessionId,
        'user': user.toJson(),
      };
}
