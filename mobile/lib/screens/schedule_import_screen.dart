import 'package:flutter/material.dart';

import '../app_scope.dart';
import '../models/schedule_import_result.dart';
import '../widgets/app_snack_bar.dart';
import 'schedule_web_import_screen.dart';

class ScheduleImportScreen extends StatefulWidget {
  const ScheduleImportScreen({super.key});

  @override
  State<ScheduleImportScreen> createState() => _ScheduleImportScreenState();
}

class _ScheduleImportScreenState extends State<ScheduleImportScreen> {
  final _urlController = TextEditingController(
    text: 'https://jxfw.gdut.edu.cn/login!welcome.action',
  );
  ScheduleImportResult? _result;

  @override
  void dispose() {
    _urlController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = AppScope.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('导入课表')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(
            '课表来源',
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w800,
                ),
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _urlController,
            keyboardType: TextInputType.url,
            minLines: 2,
            maxLines: 3,
            decoration: const InputDecoration(
              labelText: '要采集的网址',
              hintText: 'https://jxfw.gdut.edu.cn/login!welcome.action',
              alignLabelWithHint: true,
            ),
          ),
          const SizedBox(height: 16),
          FilledButton(
            onPressed: state.busy ? null : _openWebImport,
            child: const Text('网页登录导入'),
          ),
          const SizedBox(height: 10),
          OutlinedButton(
            onPressed: state.busy ? null : _import,
            child: const Text('尝试直接导入'),
          ),
          if (_result != null) ...[
            const SizedBox(height: 24),
            _ImportResultCard(result: _result!),
          ],
        ],
      ),
    );
  }

  Future<void> _import() async {
    final url = _urlController.text.trim();
    final uri = Uri.tryParse(url);
    if (uri == null || !uri.hasScheme || !uri.hasAuthority) {
      showErrorSnackBar(context, '请输入完整的网址');
      return;
    }

    final state = AppScope.of(context);
    try {
      final result = await state.importScheduleFromUrl(url);
      if (!mounted) {
        return;
      }
      setState(() => _result = result);
      if (result.imported) {
        showSuccessSnackBar(context, '已导入 ${result.courseCount} 门课程');
      } else if (result.requiresLogin) {
        await Navigator.of(context).push(
          MaterialPageRoute<void>(
            builder: (_) => ScheduleWebImportScreen(
              initialUrl:
                  result.menuUrl?.isNotEmpty == true ? result.menuUrl! : url,
            ),
          ),
        );
      } else if (!result.requiresLogin) {
        showErrorSnackBar(context, result.message);
      }
    } catch (_) {
      if (mounted) {
        showErrorSnackBar(context, state.error ?? '课表采集失败');
        state.clearError();
      }
    }
  }

  Future<void> _openWebImport() async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => ScheduleWebImportScreen(
          initialUrl: _urlController.text.trim(),
        ),
      ),
    );
  }
}

class _ImportResultCard extends StatelessWidget {
  const _ImportResultCard({required this.result});

  final ScheduleImportResult result;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final isSuccess = result.imported;
    final isLogin = result.requiresLogin;
    final color = isSuccess
        ? scheme.primaryContainer
        : isLogin
            ? scheme.secondaryContainer
            : scheme.errorContainer;
    final foreground = isSuccess
        ? scheme.onPrimaryContainer
        : isLogin
            ? scheme.onSecondaryContainer
            : scheme.onErrorContainer;

    return Card(
      color: color,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              isSuccess
                  ? '成功'
                  : isLogin
                      ? '登录'
                      : '失败',
              style: TextStyle(color: foreground, fontWeight: FontWeight.w700),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(result.message, style: TextStyle(color: foreground)),
                  if (result.menuUrl != null && result.menuUrl!.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    Text(
                      result.menuUrl!,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: foreground,
                          ),
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
