import 'user.dart';

class AuthSession {
  const AuthSession({
    required this.token,
    required this.user,
    this.tokenType = 'Bearer',
  });

  final String token;
  final String tokenType;
  final User user;

  factory AuthSession.fromJson(Map<String, dynamic> json) {
    return AuthSession(
      token: json['token']?.toString() ?? '',
      tokenType: json['token_type']?.toString() ?? 'Bearer',
      user: User.fromJson(json['user'] as Map<String, dynamic>),
    );
  }
}
