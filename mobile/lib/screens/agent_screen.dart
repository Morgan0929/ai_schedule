import 'package:flutter/material.dart';

import '../app_scope.dart';
import '../models/agent_chat.dart';
import '../state/app_state.dart';
import '../widgets/error_banner.dart';

class AgentScreen extends StatefulWidget {
  const AgentScreen({super.key});

  @override
  State<AgentScreen> createState() => _AgentScreenState();
}

class _AgentScreenState extends State<AgentScreen> {
  final _controller = TextEditingController();
  final _inputFocusNode = FocusNode();
  final _scrollController = ScrollController();

  @override
  void dispose() {
    _controller.dispose();
    _inputFocusNode.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = AppScope.of(context);
    WidgetsBinding.instance.addPostFrameCallback((_) => _scrollToBottom());

    return Column(
      children: [
        const ErrorBanner(),
        Expanded(
          child: ListView.builder(
            controller: _scrollController,
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
            itemCount: state.messages.length,
            itemBuilder: (context, index) {
              return _MessageBubble(message: state.messages[index]);
            },
          ),
        ),
        if (state.agentThinking)
          const Padding(
            padding: EdgeInsets.fromLTRB(16, 0, 16, 10),
            child: Align(
              alignment: Alignment.centerLeft,
              child: _ThinkingBubble(),
            ),
          ),
        SafeArea(
          top: false,
          child: Container(
            padding: const EdgeInsets.fromLTRB(12, 10, 12, 12),
            decoration: BoxDecoration(
              color: Theme.of(context).colorScheme.surface,
              border: const Border(top: BorderSide(color: Color(0xFFE1E5E8))),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Expanded(
                  child: TextField(
                    controller: _controller,
                    focusNode: _inputFocusNode,
                    minLines: 1,
                    maxLines: 4,
                    decoration: const InputDecoration(
                      hintText: '例如：明天下午三点提醒我开会',
                      prefixIcon: Icon(Icons.chat_bubble_outline),
                    ),
                    onSubmitted: (_) => _send(),
                  ),
                ),
                const SizedBox(width: 8),
                if (_showConfirmActions(state))
                  _ConfirmButtons(
                    busy: state.busy,
                    onAgree: _agree,
                    onCancel: () => _sendText('取消'),
                  )
                else
                  _SendButton(busy: state.busy, onSend: _send),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Future<void> _send() async {
    final text = _controller.text.trim();
    if (text.isEmpty) {
      return;
    }
    _controller.clear();
    _inputFocusNode.unfocus();
    await _sendText(text);
  }

  Future<void> _sendText(String text) async {
    try {
      await AppScope.of(context).sendAgentMessage(text);
    } catch (_) {
      // AppState exposes the error banner.
    }
  }

  Future<void> _agree() async {
    final override = _controller.text.trim();
    _controller.clear();
    _inputFocusNode.unfocus();
    await _sendText(override.isEmpty ? '确认' : override);
  }

  void _scrollToBottom() {
    if (!_scrollController.hasClients) {
      return;
    }
    _scrollController.animateTo(
      _scrollController.position.maxScrollExtent,
      duration: const Duration(milliseconds: 180),
      curve: Curves.easeOut,
    );
  }

  bool _showConfirmActions(AppState state) {
    if (state.busy || state.messages.isEmpty) {
      return false;
    }
    final last = state.messages.last;
    return !last.isUser &&
        state.agentNeedsConfirmation &&
        state.agentConfirmationStage == 'waiting_confirm';
  }
}

class _SendButton extends StatelessWidget {
  const _SendButton({
    required this.busy,
    required this.onSend,
  });

  final bool busy;
  final VoidCallback onSend;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final foreground = busy ? colors.onSurfaceVariant : colors.onPrimary;

    return SizedBox(
      height: 48,
      width: 84,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: busy ? colors.surfaceContainerHighest : colors.primary,
          borderRadius: BorderRadius.circular(10),
        ),
        child: InkWell(
          onTap: busy ? null : onSend,
          borderRadius: BorderRadius.circular(10),
          child: Center(
            child: busy
                ? SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: colors.onSurfaceVariant,
                    ),
                  )
                : Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.send_rounded, size: 17, color: foreground),
                      const SizedBox(width: 6),
                      Text(
                        '发送',
                        style: TextStyle(
                          color: foreground,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ],
                  ),
          ),
        ),
      ),
    );
  }
}

class _ConfirmButtons extends StatelessWidget {
  const _ConfirmButtons({
    required this.busy,
    required this.onAgree,
    required this.onCancel,
  });

  final bool busy;
  final VoidCallback onAgree;
  final VoidCallback onCancel;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        SizedBox(
          height: 48,
          child: FilledButton(
            onPressed: busy ? null : onAgree,
            child: const Text('同意'),
          ),
        ),
        const SizedBox(width: 8),
        SizedBox(
          height: 48,
          child: OutlinedButton(
            onPressed: busy ? null : onCancel,
            child: const Text('取消'),
          ),
        ),
      ],
    );
  }
}

class _ThinkingBubble extends StatelessWidget {
  const _ThinkingBubble();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(0xFFE1E5E8)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          SizedBox(
            width: 14,
            height: 14,
            child: CircularProgressIndicator(
              strokeWidth: 2,
              color: Theme.of(context).colorScheme.primary,
            ),
          ),
          const SizedBox(width: 8),
          const Text('林正在思考...'),
        ],
      ),
    );
  }
}

class _MessageBubble extends StatelessWidget {
  const _MessageBubble({required this.message});

  final ChatMessage message;

  @override
  Widget build(BuildContext context) {
    final isUser = message.isUser;
    final colors = Theme.of(context).colorScheme;
    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (!isUser) ...[
            Container(
              width: 30,
              height: 30,
              margin: const EdgeInsets.only(right: 8, top: 2),
              decoration: BoxDecoration(
                color: colors.primaryContainer,
                borderRadius: BorderRadius.circular(9),
              ),
              child: Icon(
                Icons.auto_awesome,
                size: 17,
                color: colors.onPrimaryContainer,
              ),
            ),
          ],
          Flexible(
            child: Container(
              constraints: BoxConstraints(
                maxWidth: MediaQuery.of(context).size.width * 0.78,
              ),
              margin: const EdgeInsets.only(bottom: 12),
              padding: const EdgeInsets.fromLTRB(15, 12, 15, 13),
              decoration: BoxDecoration(
                color: isUser ? colors.primary : colors.surface,
                borderRadius: BorderRadius.circular(12),
                border:
                    isUser ? null : Border.all(color: colors.outlineVariant),
                boxShadow: isUser
                    ? null
                    : const [
                        BoxShadow(
                          color: Color(0x08000000),
                          blurRadius: 8,
                          offset: Offset(0, 2),
                        ),
                      ],
              ),
              child: isUser
                  ? Text(
                      message.content,
                      style: TextStyle(
                        height: 1.45,
                        color: colors.onPrimary,
                        fontSize: 15,
                      ),
                    )
                  : _AssistantMessageContent(text: message.content),
            ),
          ),
        ],
      ),
    );
  }
}

class _AssistantMessageContent extends StatelessWidget {
  const _AssistantMessageContent({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    final lines = text.split('\n').map((line) => line.trim()).toList();
    final visibleLines = lines.where((line) => line.isNotEmpty).toList();
    if (visibleLines.isEmpty) {
      return const SizedBox.shrink();
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          visibleLines.first,
          style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                fontWeight: FontWeight.w700,
                height: 1.45,
              ),
        ),
        if (visibleLines.length > 1) const SizedBox(height: 8),
        for (final line in visibleLines.skip(1)) ...[
          _AssistantMessageLine(line: line),
          const SizedBox(height: 6),
        ],
      ],
    );
  }
}

class _AssistantMessageLine extends StatelessWidget {
  const _AssistantMessageLine({required this.line});

  final String line;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final optionMatch = RegExp(r'^\[([A-Z])\]\s*(.*)$').firstMatch(line);
    if (optionMatch != null) {
      return Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _Badge(text: optionMatch.group(1)!, color: colors.primary),
          const SizedBox(width: 8),
          Expanded(child: _BodyText(optionMatch.group(2) ?? '')),
        ],
      );
    }

    if (line.startsWith('已有：') || line.startsWith('新的：')) {
      final label = line.substring(0, 3);
      final content = line.substring(3).trim();
      return Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _Badge(
            text: label.substring(0, 2),
            color: label.startsWith('已有') ? colors.tertiary : colors.primary,
          ),
          const SizedBox(width: 8),
          Expanded(child: _BodyText(content)),
        ],
      );
    }

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Container(
            width: 4,
            height: 4,
            decoration: BoxDecoration(
              color: colors.outline,
              shape: BoxShape.circle,
            ),
          ),
        ),
        const SizedBox(width: 8),
        Expanded(child: _BodyText(line)),
      ],
    );
  }
}

class _Badge extends StatelessWidget {
  const _Badge({required this.text, required this.color});

  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: const BoxConstraints(minWidth: 26),
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(7),
      ),
      child: Text(
        text,
        textAlign: TextAlign.center,
        style: TextStyle(
          color: color,
          fontSize: 12,
          fontWeight: FontWeight.w700,
          height: 1.2,
        ),
      ),
    );
  }
}

class _BodyText extends StatelessWidget {
  const _BodyText(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: Theme.of(context).textTheme.bodyMedium?.copyWith(height: 1.45),
    );
  }
}
