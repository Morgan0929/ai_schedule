import 'package:flutter/material.dart';

import '../app_scope.dart';
import '../widgets/error_banner.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _usernameController = TextEditingController(text: 'admin');
  final _passwordController = TextEditingController(text: '<CHANGE_ME>');
  final _emailController = TextEditingController();
  bool _registerMode = false;

  @override
  void dispose() {
    _usernameController.dispose();
    _passwordController.dispose();
    _emailController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = AppScope.of(context);
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 460),
            child: ListView(
              padding: const EdgeInsets.all(24),
              shrinkWrap: true,
              children: [
                const SizedBox(height: 28),
                Text(
                  '林',
                  style: Theme.of(context).textTheme.displayMedium?.copyWith(
                        fontWeight: FontWeight.w800,
                        color: Theme.of(context).colorScheme.primary,
                      ),
                ),
                const SizedBox(height: 8),
                Text(
                  '个人事务秘书',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                const SizedBox(height: 24),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(18),
                    child: Form(
                      key: _formKey,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          SegmentedButton<bool>(
                            segments: const [
                              ButtonSegment(
                                value: false,
                                icon: Icon(Icons.login),
                                label: Text('登录'),
                              ),
                              ButtonSegment(
                                value: true,
                                icon: Icon(Icons.person_add_alt_1),
                                label: Text('注册'),
                              ),
                            ],
                            selected: {_registerMode},
                            onSelectionChanged: state.busy
                                ? null
                                : (value) {
                                    setState(() => _registerMode = value.first);
                                  },
                          ),
                          const SizedBox(height: 16),
                          TextFormField(
                            controller: _usernameController,
                            decoration: const InputDecoration(
                              labelText: '用户名',
                              prefixIcon: Icon(Icons.person_outline),
                            ),
                            validator: (value) =>
                                value == null || value.trim().isEmpty ? '请输入用户名' : null,
                          ),
                          const SizedBox(height: 12),
                          TextFormField(
                            controller: _passwordController,
                            obscureText: true,
                            decoration: const InputDecoration(
                              labelText: '密码',
                              prefixIcon: Icon(Icons.lock_outline),
                            ),
                            validator: (value) =>
                                value == null || value.length < 6 ? '密码至少 6 位' : null,
                          ),
                          if (_registerMode) ...[
                            const SizedBox(height: 12),
                            TextFormField(
                              controller: _emailController,
                              keyboardType: TextInputType.emailAddress,
                              decoration: const InputDecoration(
                                labelText: '邮箱',
                                prefixIcon: Icon(Icons.mail_outline),
                              ),
                            ),
                          ],
                          const SizedBox(height: 18),
                          FilledButton.icon(
                            onPressed: state.busy ? null : _submit,
                            icon: state.busy
                                ? const SizedBox(
                                    width: 18,
                                    height: 18,
                                    child: CircularProgressIndicator(strokeWidth: 2),
                                  )
                                : Icon(_registerMode ? Icons.person_add_alt_1 : Icons.login),
                            label: Text(_registerMode ? '创建账号' : '进入'),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
                const ErrorBanner(),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) {
      return;
    }
    final state = AppScope.of(context);
    try {
      if (_registerMode) {
        await state.register(
          username: _usernameController.text.trim(),
          password: _passwordController.text,
          email: _emailController.text.trim(),
        );
      } else {
        await state.login(
          _usernameController.text.trim(),
          _passwordController.text,
        );
      }
    } catch (_) {
      // AppState exposes the error banner.
    }
  }
}
