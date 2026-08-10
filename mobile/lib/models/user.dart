class User {
  const User({
    required this.id,
    required this.username,
    this.email,
    this.role = 'USER',
  });

  final int id;
  final String username;
  final String? email;
  final String role;

  factory User.fromJson(Map<String, dynamic> json) {
    return User(
      id: json['id'] as int,
      username: json['username']?.toString() ?? '',
      email: json['email']?.toString(),
      role: json['role']?.toString() ?? 'USER',
    );
  }
}
