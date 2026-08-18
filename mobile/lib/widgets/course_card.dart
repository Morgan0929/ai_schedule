import 'package:flutter/material.dart';

import '../models/course_item.dart';

class CourseCard extends StatelessWidget {
  const CourseCard({
    required this.course,
    this.mediaBaseUrl,
    this.onEdit,
    this.onUploadImage,
    this.onDelete,
    super.key,
  });

  final CourseItem course;
  final String? mediaBaseUrl;
  final VoidCallback? onEdit;
  final VoidCallback? onUploadImage;
  final VoidCallback? onDelete;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 4,
              height: 56,
              decoration: BoxDecoration(
                color: const Color(0xFFB45F35),
                borderRadius: BorderRadius.circular(4),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    course.courseName,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                  ),
                  const SizedBox(height: 6),
                  Wrap(
                    spacing: 10,
                    runSpacing: 6,
                    children: [
                      _Meta(icon: Icons.schedule, text: course.timeLabel),
                      if (course.location != null &&
                          course.location!.isNotEmpty)
                        _Meta(
                            icon: Icons.place_outlined, text: course.location!),
                      if (course.teacher != null && course.teacher!.isNotEmpty)
                        _Meta(
                            icon: Icons.person_outline, text: course.teacher!),
                    ],
                  ),
                ],
              ),
            ),
            if (course.attachments.isNotEmpty) ...[
              _AttachmentPreview(
                attachment: course.attachments.first,
                mediaBaseUrl: mediaBaseUrl,
              ),
              const SizedBox(width: 6),
            ],
            PopupMenuButton<_CourseAction>(
              tooltip: '课程操作',
              icon: const Icon(Icons.more_vert),
              onSelected: (value) {
                switch (value) {
                  case _CourseAction.edit:
                    onEdit?.call();
                    break;
                  case _CourseAction.upload:
                    onUploadImage?.call();
                    break;
                  case _CourseAction.delete:
                    onDelete?.call();
                    break;
                }
              },
              itemBuilder: (context) => const [
                PopupMenuItem(
                  value: _CourseAction.edit,
                  child: ListTile(
                    leading: Icon(Icons.edit_outlined),
                    title: Text('编辑'),
                  ),
                ),
                PopupMenuItem(
                  value: _CourseAction.upload,
                  child: ListTile(
                    leading: Icon(Icons.image_outlined),
                    title: Text('上传图片'),
                  ),
                ),
                PopupMenuItem(
                  value: _CourseAction.delete,
                  child: ListTile(
                    leading: Icon(Icons.delete_outline),
                    title: Text('删除'),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

enum _CourseAction { edit, upload, delete }

class _AttachmentPreview extends StatelessWidget {
  const _AttachmentPreview({required this.attachment, this.mediaBaseUrl});

  final CourseAttachment attachment;
  final String? mediaBaseUrl;

  @override
  Widget build(BuildContext context) {
    final url = _absoluteUrl(attachment.fileUrl);
    if (url == null) {
      return const Icon(Icons.image_outlined);
    }
    return ClipRRect(
      borderRadius: BorderRadius.circular(6),
      child: Image.network(
        url,
        width: 42,
        height: 42,
        fit: BoxFit.cover,
        errorBuilder: (_, __, ___) => const SizedBox(
          width: 42,
          height: 42,
          child: Icon(Icons.broken_image_outlined),
        ),
      ),
    );
  }

  String? _absoluteUrl(String value) {
    if (value.isEmpty) {
      return null;
    }
    if (value.startsWith('http://') || value.startsWith('https://')) {
      return value;
    }
    final base = mediaBaseUrl;
    if (base == null || base.isEmpty) {
      return value;
    }
    return '${base.replaceFirst(RegExp(r'/+$'), '')}$value';
  }
}

class _Meta extends StatelessWidget {
  const _Meta({required this.icon, required this.text});

  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 16, color: Theme.of(context).colorScheme.secondary),
        const SizedBox(width: 4),
        Text(text, style: Theme.of(context).textTheme.bodySmall),
      ],
    );
  }
}
