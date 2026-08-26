import '../core/api/api_client.dart';
import '../models/auth_session.dart';
import '../models/user.dart';

class AuthService {
  AuthService(this.client);

  final ApiClient client;

  Future<AuthSession> login({
    required String username,
    required String password,
  }) async {
    final data = await client.post(
      '/api/v1/auth/login',
      body: {'username': username, 'password': password},
    ) as Map<String, dynamic>;
    return AuthSession.fromJson(data);
  }

  Future<void> logout({required String token}) async {
    await ApiClient(baseUrl: client.baseUrl, token: token).post(
      '/api/v1/auth/logout',
      body: const {},
    );
  }

  Future<User> register({
    required String username,
    required String password,
    String? email,
  }) async {
    final data = await client.post(
      '/api/v1/auth/register',
      body: {
        'username': username,
        'password': password,
        'email': email?.isEmpty == true ? null : email,
        'role': 'USER',
      },
    ) as Map<String, dynamic>;
    return User.fromJson(data);
  }
}
